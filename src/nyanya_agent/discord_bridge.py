#!/usr/bin/env python3
"""Discord bridge for NyaNya.

Requires discord.py. Install with:
    python3 -m pip install -r requirements-bots.txt
"""

from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import re
import sys

from nyanya_agent import dashboard_store
from nyanya_agent.bridge_common import (
    CANCEL_ALL_COMMANDS,
    CANCEL_COMMANDS,
    CANCEL_USER_COMMANDS,
    GET_HOME_COMMANDS,
    HELP_COMMANDS,
    NyaNyaConversationStore,
    SET_HOME_COMMANDS,
    UNSET_HOME_COMMANDS,
    command_name,
    default_codex_workdir,
    discord_help_text,
    env_first,
    is_allowed_workspace_path,
    load_runtime_config,
    normalize_owner_key,
    parse_bool,
    parse_id_set,
    resolve_workspace_path,
    split_message,
)


DISCORD_LIMIT = 1900
ATTACHMENT_FILENAME_RE = re.compile(
    r"(?<!\S)[\w가-힣().-]+\.(?:zip|tar|tgz|gz|7z|html?|md|pdf|docx?|xlsx?|pptx?|csv|json|txt)",
    re.IGNORECASE,
)


def strip_bot_mention(text: str) -> str:
    return re.sub(r"<@!?\d+>", "", text).strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run NyaNya Discord bridge")
    parser.add_argument("--config", help="Path to NyaNya JSON config")
    parser.add_argument("--check-config", action="store_true", help="Validate bridge config and exit")
    return parser.parse_args()


def check_config(token: str, config: dict[str, object]) -> int:
    try:
        import discord  # noqa: F401

        discord_installed = True
    except ImportError:
        discord_installed = False
    print(f"discord_token_configured={bool(token)}")
    print(f"provider={config.get('provider')}")
    print(f"model={config.get('model')}")
    print(f"discord_py_installed={discord_installed}")
    print(f"allowed_channel_ids={bool(os.getenv('NYANYA_DISCORD_ALLOWED_CHANNEL_IDS'))}")
    print(f"allowed_user_ids={bool(os.getenv('NYANYA_DISCORD_ALLOWED_USER_IDS'))}")
    print(f"allow_unlisted={parse_bool(os.getenv('NYANYA_ALLOW_UNLISTED'), False)}")
    return 0 if token and discord_installed else 2


def main() -> int:
    args = parse_args()
    config = load_runtime_config(args.config)
    token = env_first("NYANYA_DISCORD_BOT_TOKEN", "DISCORD_BOT_TOKEN")
    if args.check_config:
        return check_config(token, config)
    if not token:
        print("Missing NYANYA_DISCORD_BOT_TOKEN in .env", file=sys.stderr)
        return 2

    try:
        import discord
    except ImportError:
        print("Missing discord.py. Run: python3 -m pip install -r requirements-bots.txt", file=sys.stderr)
        return 2

    prefix = os.getenv("NYANYA_DISCORD_PREFIX", "!nyanya")
    allow_unlisted = parse_bool(os.getenv("NYANYA_ALLOW_UNLISTED"), False)
    respond_in_allowed_channels = parse_bool(os.getenv("NYANYA_DISCORD_RESPOND_IN_ALLOWED_CHANNELS"), False)
    allowed_channel_ids = parse_id_set(os.getenv("NYANYA_DISCORD_ALLOWED_CHANNEL_IDS"))
    allowed_user_ids = parse_id_set(os.getenv("NYANYA_DISCORD_ALLOWED_USER_IDS"))
    file_share_channel_ids = parse_id_set(os.getenv("NYANYA_DISCORD_FILE_SHARE_CHANNEL_IDS"))
    file_share_channel_names = parse_id_set(os.getenv("NYANYA_DISCORD_FILE_SHARE_CHANNEL_NAMES"))
    store = NyaNyaConversationStore(config)

    intents = discord.Intents.default()
    intents.message_content = True
    intents.messages = True
    intents.dm_messages = True

    client = discord.Client(intents=intents)
    phase_check_task: asyncio.Task[None] | None = None

    def dashboard_recording_enabled() -> bool:
        return parse_bool(os.getenv("NYANYA_DASHBOARD_RECORDING_ENABLED"), True)

    def request_mode(command: str) -> str:
        if command in {"gemini", "/gemini"}:
            return "gemini"
        if command in {"codex", "/codex"}:
            return "codex"
        if command in {"codex-work", "/codex-work", "codex_work", "/codex_work"}:
            return "codex_write"
        if command in {"upload", "/upload", "파일업로드", "/파일업로드", "sendfile", "file"}:
            return "upload"
        if command in {
            "reset",
            "/reset",
            "save",
            "/save",
            "status",
            "/status",
            "config",
            "/config",
            "resources",
            "/resources",
            "resource",
            "/resource",
            "리소스",
            "/리소스",
            "취소",
            "/cancel",
            "cancel",
            "/취소",
        }:
            return "control"
        return "auto"

    def create_dashboard_request(message: discord.Message, text: str, trigger: str, *, status: str = "received") -> str | None:
        if not dashboard_recording_enabled():
            return None
        command = command_name(text)
        try:
            return dashboard_store.create_agent_request(
                source="discord",
                guild_id=str(getattr(getattr(message, "guild", None), "id", "") or ""),
                channel_id=str(message.channel.id),
                channel_name=str(getattr(message.channel, "name", "") or ""),
                user_id=str(message.author.id),
                trigger=trigger,
                command=command,
                mode=request_mode(command),
                provider=str(config.get("provider") or ""),
                model=str(config.get("model") or ""),
                prompt=text,
                status=status,
                metadata={
                    "message_id": str(message.id),
                    "author_name": str(getattr(message.author, "name", "") or ""),
                    "attachment_count": len(message.attachments),
                },
            )
        except Exception as exc:  # noqa: BLE001
            print(f"Dashboard request create failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            return None

    def mark_dashboard_request(request_id: str | None, status: str, **kwargs: object) -> None:
        if not request_id:
            return
        try:
            dashboard_store.mark_request_status(request_id, status, **kwargs)
        except Exception as exc:  # noqa: BLE001
            print(f"Dashboard request update failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)

    async def phase_check_loop() -> None:
        if not parse_bool(os.getenv("NYANYA_PHASE_CHECK_ENABLED"), False):
            return
        channel_id = os.getenv("NYANYA_DASHBOARD_CONFIRMATION_CHANNEL_ID", "").strip()
        if not channel_id:
            print("NyaNya phase checker disabled: NYANYA_DASHBOARD_CONFIRMATION_CHANNEL_ID is empty", flush=True)
            return
        interval = int(os.getenv("NYANYA_PHASE_CHECK_INTERVAL_SECONDS", "21600"))
        await client.wait_until_ready()
        while not client.is_closed():
            try:
                channel = client.get_channel(int(channel_id)) or await client.fetch_channel(int(channel_id))
                checks = dashboard_store.due_phase_checks(interval_seconds=interval)
                for check in checks:
                    message_text = check.get("discord_message", "")
                    if message_text:
                        await channel.send(message_text)
            except Exception as exc:  # noqa: BLE001
                print(f"NyaNya phase checker failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            await asyncio.sleep(max(60, interval))

    def attachment_download_root() -> pathlib.Path:
        raw = os.getenv("NYANYA_DISCORD_ATTACHMENT_DIR", "nyanya-agent/downloads/discord")
        return resolve_workspace_path(raw)

    def referenced_filenames(text: str) -> set[str]:
        names: set[str] = set()
        for match in ATTACHMENT_FILENAME_RE.finditer(text):
            name = pathlib.Path(match.group(0).strip("`'\".,;:，。")).name
            if name:
                names.add(name)
        return names

    async def save_attachment(attachment: discord.Attachment, message: discord.Message) -> pathlib.Path | None:
        max_mb = int(os.getenv("NYANYA_DISCORD_ATTACHMENT_MAX_MB", "50"))
        if attachment.size > max_mb * 1024 * 1024:
            return None
        filename = pathlib.Path(attachment.filename).name
        if not filename:
            return None
        target_dir = attachment_download_root() / str(message.channel.id) / str(message.id)
        target = (target_dir / filename).resolve(strict=False)
        if not is_allowed_workspace_path(target):
            return None
        target_dir.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.stat().st_size != attachment.size:
            await attachment.save(target)
        return target

    async def find_recent_attachments(message: discord.Message, filenames: set[str]) -> list[pathlib.Path]:
        if not filenames or not hasattr(message.channel, "history"):
            return []
        remaining = {name.lower() for name in filenames}
        found: list[pathlib.Path] = []
        limit = int(os.getenv("NYANYA_DISCORD_ATTACHMENT_SEARCH_LIMIT", "1000"))
        async for previous in message.channel.history(limit=limit):
            for attachment in previous.attachments:
                if attachment.filename.lower() not in remaining:
                    continue
                saved = await save_attachment(attachment, previous)
                if saved is not None:
                    found.append(saved)
                    remaining.discard(attachment.filename.lower())
            if not remaining:
                break
        return found

    async def attachment_context(message: discord.Message, text: str) -> str:
        saved_paths: list[pathlib.Path] = []
        for attachment in message.attachments:
            saved = await save_attachment(attachment, message)
            if saved is not None:
                saved_paths.append(saved)

        existing_names = {path.name.lower() for path in saved_paths}
        wanted = {name for name in referenced_filenames(text) if name.lower() not in existing_names}
        saved_paths.extend(await find_recent_attachments(message, wanted))
        if not saved_paths:
            return ""
        unique_paths = list(dict.fromkeys(saved_paths))
        lines = [
            "Discord attachment context:",
            "The following Discord attachment files were saved locally. Use these paths when the user refers to the files:",
        ]
        lines.extend(f"- {path.name}: {path}" for path in unique_paths)
        return "\n".join(lines)

    def is_allowed(message: discord.Message) -> bool:
        if allow_unlisted:
            return True
        channel_ids = {str(message.channel.id)}
        parent_id = getattr(message.channel, "parent_id", None)
        if parent_id is not None:
            channel_ids.add(str(parent_id))
        parent = getattr(message.channel, "parent", None)
        if parent is not None:
            channel_ids.add(str(parent.id))
        return bool(channel_ids & allowed_channel_ids) or str(message.author.id) in allowed_user_ids

    def should_respond(message: discord.Message) -> tuple[bool, str, str]:
        content = message.content.strip()
        if isinstance(message.channel, discord.DMChannel):
            return True, content, "dm"
        if content.startswith(prefix):
            return True, content[len(prefix) :].strip(), "prefix"
        if client.user and client.user in message.mentions:
            return True, strip_bot_mention(content), "mention"
        if respond_in_allowed_channels and is_allowed(message):
            return True, content, "allowed_channel"
        return False, "", ""

    async def reply(message: discord.Message, text: str) -> None:
        for chunk in split_message(text, DISCORD_LIMIT):
            await message.channel.send(chunk)

    def is_file_share_channel(message: discord.Message) -> bool:
        channel_name = str(getattr(message.channel, "name", ""))
        return str(message.channel.id) in file_share_channel_ids or channel_name in file_share_channel_names

    async def handle_command(message: discord.Message, text: str, attachment_note: str = "", request_id: str | None = None) -> str:
        owner_key = f"discord-user:{message.author.id}"
        conversation_key = f"discord:{message.channel.id}:user:{message.author.id}"
        command = command_name(text)
        loop = asyncio.get_running_loop()

        def finish(response: str, *, status: str = "completed", error: str | None = None, mode: str | None = None) -> str:
            mark_dashboard_request(
                request_id,
                status,
                event_type=f"command_{status}",
                message=response or status,
                result_summary=response,
                error=error,
                mode=mode or request_mode(command),
                provider=str(config.get("provider") or ""),
                model=str(config.get("model") or ""),
            )
            return response

        def prompt_with_attachments(prompt: str) -> str:
            if not attachment_note:
                return prompt
            return f"{prompt.rstrip()}\n\n{attachment_note}"

        def respond_later(response: str) -> None:
            for chunk in split_message(response, DISCORD_LIMIT):
                asyncio.run_coroutine_threadsafe(message.channel.send(chunk), loop)

        if not text and attachment_note:
            text = "첨부파일 내용을 확인해 주세요."
            command = command_name(text)

        if not text or command in HELP_COMMANDS:
            return finish(
                discord_help_text(
                    prefix=prefix,
                    channel_id=str(message.channel.id),
                    user_id=str(message.author.id),
                    is_admin=store.is_owner(str(message.author.id)),
                ),
                mode="control",
            )
        if command in CANCEL_ALL_COMMANDS:
            if not store.is_owner(str(message.author.id)):
                return finish("전체 취소는 관리자만 사용할 수 있습니다.", status="failed", error="owner required", mode="control")
            return finish(store.cancel_all(), mode="control")
        if command in CANCEL_USER_COMMANDS:
            if not store.is_owner(str(message.author.id)):
                return finish("사용자 취소는 관리자만 사용할 수 있습니다.", status="failed", error="owner required", mode="control")
            target = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
            if not target:
                return finish("사용법: 사용자취소 discord_user_id 또는 사용자취소 discord-user:discord_user_id", status="failed", error="missing target", mode="control")
            target_owner = target if ":" in target else f"discord-user:{target}"
            return finish(store.cancel_owner(target_owner), mode="control")
        if command in CANCEL_COMMANDS:
            return finish(store.cancel_owner(owner_key), mode="control")
        if command in SET_HOME_COMMANDS:
            if not store.is_owner(str(message.author.id)):
                return finish("홈워크스페이스 설정은 관리자만 사용할 수 있습니다.", status="failed", error="owner required", mode="control")
            parts = text.split(maxsplit=2)
            if len(parts) < 3:
                return finish("사용법: set_home discord_user_id HCS 또는 set_home discord-user:discord_user_id HCS", status="failed", error="missing arguments", mode="control")
            try:
                target_owner = normalize_owner_key(parts[1], "discord")
            except ValueError as exc:
                return finish(str(exc), status="failed", error=str(exc), mode="control")
            return finish(store.set_home(target_owner, parts[2], set_by=owner_key), mode="control")
        if command in UNSET_HOME_COMMANDS:
            if not store.is_owner(str(message.author.id)):
                return finish("홈워크스페이스 해제는 관리자만 사용할 수 있습니다.", status="failed", error="owner required", mode="control")
            target = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
            if not target:
                return finish("사용법: unset_home discord_user_id 또는 unset_home discord-user:discord_user_id", status="failed", error="missing target", mode="control")
            try:
                target_owner = normalize_owner_key(target, "discord")
            except ValueError as exc:
                return finish(str(exc), status="failed", error=str(exc), mode="control")
            return finish(store.unset_home(target_owner), mode="control")
        if command in GET_HOME_COMMANDS:
            target = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
            if target:
                if not store.is_owner(str(message.author.id)):
                    return finish("다른 사용자의 홈워크스페이스 조회는 관리자만 사용할 수 있습니다.", status="failed", error="owner required", mode="control")
                try:
                    target_owner = normalize_owner_key(target, "discord")
                except ValueError as exc:
                    return finish(str(exc), status="failed", error=str(exc), mode="control")
            else:
                target_owner = owner_key
            return finish(store.home_text(target_owner), mode="control")
        if command in {"reset", "/reset"}:
            store.reset(conversation_key)
            return finish("대화 컨텍스트를 초기화했습니다.", mode="control")
        if command in {"save", "/save"}:
            path = store.save(conversation_key)
            return finish(f"저장했습니다: {path}" if path else "세션 저장이 꺼져 있습니다.", mode="control")
        if command in {"status", "/status"}:
            return finish(
                (
                    "NyaNya Agent bridge is running.\n"
                    f"provider={store.config.get('provider')}\n"
                    f"model={store.config.get('model')}"
                ),
                mode="control",
            )
        if command in {"config", "/config"}:
            return finish(store.status_text(), mode="control")
        if command in {"gemini", "/gemini"}:
            prompt = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
            if not prompt:
                return finish("사용법: gemini Google CLI에 물어볼 내용을 적어주세요.", status="failed", error="missing prompt", mode="gemini")
            return store.submit(
                owner_key=owner_key,
                conversation_key=conversation_key,
                prompt=prompt_with_attachments(prompt),
                mode="gemini",
                responder=respond_later,
                request_id=request_id,
            )
        if command in {"codex", "/codex"}:
            prompt = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
            if not prompt:
                return finish("사용법: codex 검수하거나 조사할 내용을 적어주세요.", status="failed", error="missing prompt", mode="codex")
            return store.submit(
                owner_key=owner_key,
                conversation_key=conversation_key,
                prompt=prompt_with_attachments(prompt),
                mode="codex",
                responder=respond_later,
                request_id=request_id,
            )
        if command in {"codex-work", "/codex-work", "codex_work", "/codex_work"}:
            prompt = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) > 1 else ""
            if not prompt:
                return finish("사용법: codex-work Codex에 맡길 작업을 적어주세요.", status="failed", error="missing prompt", mode="codex_write")
            return store.submit(
                owner_key=owner_key,
                conversation_key=conversation_key,
                prompt=prompt_with_attachments(prompt),
                mode="codex_write",
                responder=respond_later,
                request_id=request_id,
            )
        if command in {"resources", "/resources", "resource", "/resource", "리소스", "/리소스"}:
            try:
                return finish(store.resources(), mode="control")
            except Exception as exc:  # noqa: BLE001
                return finish(f"리소스 조회 실패: {exc}", status="failed", error=str(exc), mode="control")
        if command in {"upload", "/upload", "파일업로드", "/파일업로드", "sendfile", "file"}:
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                return finish("사용법: upload <파일_경로>", status="failed", error="missing file path", mode="upload")
            file_path_str = parts[1].strip().strip("`\"'")

            owner_key = f"discord-user:{message.author.id}"
            user_workdir = store.workspace_for_owner(owner_key) or default_codex_workdir()
            resolved_path = None
            try:
                candidate = pathlib.Path(file_path_str).expanduser()
                if not candidate.is_absolute():
                    candidate = user_workdir / candidate
                candidate_resolved = candidate.resolve(strict=False)
                if is_allowed_workspace_path(candidate_resolved):
                    resolved_path = candidate_resolved
            except Exception:
                pass

            if not resolved_path:
                try:
                    resolved_path = resolve_workspace_path(file_path_str)
                except Exception as exc:
                    return finish(f"파일 경로 오류: {exc}", status="failed", error=str(exc), mode="upload")

            if not resolved_path.exists():
                return finish(f"파일을 찾을 수 없습니다: {resolved_path}", status="failed", error="file not found", mode="upload")
            if not resolved_path.is_file():
                return finish(f"지정한 경로는 파일이 아닙니다: {resolved_path}", status="failed", error="not a file", mode="upload")

            try:
                with open(resolved_path, "rb") as f:
                    discord_file = discord.File(f, filename=resolved_path.name)
                    content = None if is_file_share_channel(message) else f"요청하신 파일({resolved_path.name})을 업로드합니다."
                    await message.channel.send(content=content, file=discord_file)
                mark_dashboard_request(
                    request_id,
                    "completed",
                    event_type="file_uploaded",
                    message=f"uploaded={resolved_path.name}",
                    result_summary=f"uploaded={resolved_path.name}",
                    mode="upload",
                    provider=str(config.get("provider") or ""),
                    model=str(config.get("model") or ""),
                )
                return ""
            except Exception as e:
                return finish(f"파일 업로드 실패: {e}", status="failed", error=str(e), mode="upload")
        return store.submit(
            owner_key=owner_key,
            conversation_key=conversation_key,
            prompt=prompt_with_attachments(text),
            mode="auto",
            responder=respond_later,
            request_id=request_id,
        )

    @client.event
    async def on_ready() -> None:
        nonlocal phase_check_task
        print(f"NyaNya Agent Discord bridge started as {client.user}")
        if phase_check_task is None or phase_check_task.done():
            phase_check_task = asyncio.create_task(phase_check_loop())

    @client.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot:
            return
        respond, text, trigger = should_respond(message)
        print(
            "Discord message "
            f"channel_id={message.channel.id} user_id={message.author.id} "
            f"parent_id={getattr(message.channel, 'parent_id', None)} "
            f"allowed={is_allowed(message)} respond={respond} trigger={trigger} text_len={len(text)}",
            flush=True,
        )
        if not respond:
            return
        request_id = create_dashboard_request(message, text, trigger)
        if is_file_share_channel(message):
            cmd = command_name(text)
            if trigger == "allowed_channel" and cmd not in {"upload", "/upload", "파일업로드", "/파일업로드", "sendfile", "file"}:
                mark_dashboard_request(
                    request_id,
                    "ignored",
                    event_type="file_share_silent",
                    message="File-share channel ignored ordinary chatter",
                    mode="ignored",
                )
                return
        if not is_allowed(message):
            mark_dashboard_request(
                request_id,
                "ignored",
                event_type="not_allowed",
                message="Channel or user is not allowed",
                mode="access_control",
            )
            await reply(
                message,
                "이 채널/사용자는 아직 NyaNya 허용 목록에 없습니다.\n"
                f"NYANYA_DISCORD_ALLOWED_CHANNEL_IDS={message.channel.id}\n"
                f"NYANYA_DISCORD_PARENT_CHANNEL_ID={getattr(message.channel, 'parent_id', None)}\n"
                f"NYANYA_DISCORD_ALLOWED_USER_IDS={message.author.id}\n"
                "위 값 중 하나를 .env에 추가한 뒤 브리지를 다시 시작하세요.",
            )
            return
        note = ""
        try:
            note = await attachment_context(message, text)
        except Exception as exc:  # noqa: BLE001
            print(f"Discord attachment context failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            mark_dashboard_request(
                request_id,
                "running",
                event_type="attachment_context_failed",
                message=str(exc),
            )
        res = await handle_command(message, text, note, request_id)
        if res:
            await reply(message, res)

    client.run(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
