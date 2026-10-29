#!/usr/bin/env python3
"""Discord bridge for NyaNya.

Requires discord.py. Install with:
    python3 -m pip install -r requirements-bots.txt
"""

from __future__ import annotations

import argparse
from collections import OrderedDict
import asyncio
import os
import pathlib
import re
import signal
import sys
import threading

from nyanya_agent import dashboard_store, work_queue, execution_store, workflow_notifications, upload_approval
from nyanya_agent.control_intents import classify
from nyanya_agent.context_security import open_upload_file, MAX_UPLOAD_BYTES
from nyanya_agent.workspace_paths import scoped_path, new_task_directory
from nyanya_agent.task_outcomes import OutcomeSignal, TaskOutcome, SafeOperationError
from nyanya_agent.bridge_common import (
    CANCEL_ALL_COMMANDS,
    CANCEL_COMMANDS,
    CANCEL_USER_COMMANDS,
    GET_HOME_COMMANDS,
    HELP_COMMANDS,
    NyaNyaConversationStore,
    NyaNyaTask as NyaNyaTask,
    SET_HOME_COMMANDS,
    TASK_STATUS_COMMANDS,
    UNSET_HOME_COMMANDS,
    command_name,
    discord_help_text,
    env_first,
    load_runtime_config,
    normalize_owner_key,
    parse_bool,
    parse_id_set,
    split_message,
)


DISCORD_LIMIT = 1900
UPLOAD_CONFIRM_COMMANDS = {"upload-approve", "upload-reject", "upload-cancel"}


def upload_byte_limit(channel):
    """Min of SDK guild limit and 8 MiB app cap; missing SDK data fails closed."""
    limit = getattr(getattr(channel, "guild", None), "filesize_limit", None)
    if type(limit) is not int or limit < 1:
        raise SafeOperationError("Destination upload limit is unavailable; upload held")
    return min(limit, MAX_UPLOAD_BYTES)


def upload_destination_key(channel):
    guild = getattr(getattr(channel, "guild", None), "id", None)
    channel_id = getattr(channel, "id", None)
    if guild is None or channel_id is None:
        raise SafeOperationError("Destination identity is unavailable; upload held")
    return f"{guild}:{channel_id}"

ATTACHMENT_FILENAME_RE = re.compile(
    r"(?<!\S)[\w가-힣().-]+\.(?:zip|tar|tgz|gz|7z|html?|md|pdf|docx?|xlsx?|pptx?|csv|json|txt)",
    re.IGNORECASE,
)


class _UnrecordedMessageClaims:
    """Bounded process-local claims; recording opt-out creates no durable receipt."""

    def __init__(self, limit=4096):
        if limit < 1:
            raise ValueError("Claim bound must be positive")
        self.limit = limit
        self.claims = OrderedDict()
        self.lock = threading.Lock()

    def claim(self, identity):
        with self.lock:
            if identity in self.claims:
                return False
            self.claims[identity] = None
            if len(self.claims) > self.limit:
                self.claims.popitem(last=False)
            return True


def strip_bot_mention(text: str) -> str:
    return re.sub(r"<@!?\d+>", "", text).strip()


def format_saved_result(saved: dict, current: dict | None) -> str:
    delivery = saved['delivery_status']
    note = (' (전달 여부 확인 필요; 자동 재전송하지 않음)'
            if delivery in {'sending', 'uncertain'} else
            ' (알림만 종료; 전달 성공으로 확인한 것은 아님)' if delivery == 'acknowledged' else '')
    return (
        f"저장된 결과 ({saved['created_at']}, outcome={saved['outcome']}):\n{saved['response']}\n\n"
        f"현재 작업 상태: {current['status'] if current else '조회 불가'}\n"
        f"결과 전달 상태: {delivery}{note}\n"
        "저장된 응답 안의 미완료 목록은 결과 당시 기록입니다. 현재 목록은 작업목록으로 확인하세요."
    )


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


async def run_client(client, token, store):
    """Give SIGTERM the same orderly async teardown as asyncio's SIGINT path."""
    loop = asyncio.get_running_loop()
    runner = asyncio.current_task()
    terminating = False
    previous = None
    registered = False

    def terminate(*_):
        nonlocal terminating
        if not terminating:
            terminating = True
            loop.call_soon_threadsafe(runner.cancel)

    try:
        if threading.current_thread() is threading.main_thread():
            previous = signal.signal(signal.SIGTERM, terminate)
            registered = True
        try:
            async with client:
                await client.start(token)
        except asyncio.CancelledError:
            if not terminating:
                raise
    finally:
        # Repeated SIGTERM must not interrupt close/reap or cancel its thread.
        terminating = True
        try:
            await asyncio.to_thread(store.close)
        finally:
            if registered:
                signal.signal(signal.SIGTERM, previous)


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
    unrecorded_claims = _UnrecordedMessageClaims()

    intents = discord.Intents.default()
    intents.message_content = True
    intents.messages = True
    intents.dm_messages = True

    client = discord.Client(intents=intents, allowed_mentions=discord.AllowedMentions.none())
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
            *UPLOAD_CONFIRM_COMMANDS,
            *HELP_COMMANDS,
            *CANCEL_ALL_COMMANDS,
            *CANCEL_USER_COMMANDS,
            *CANCEL_COMMANDS,
            *SET_HOME_COMMANDS,
            *UNSET_HOME_COMMANDS,
            *GET_HOME_COMMANDS,
            "why", "plan", "plan-file", "approve", "revoke", "resume",
            "reconcile", "resolve", "result", "결과", "recovery", "복구",
            "open-draft", "draft-show", "draft-close", "draft-feedback",
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
            *TASK_STATUS_COMMANDS,
            "취소",
            "/cancel",
            "cancel",
            "/취소",
        }:
            return "control"
        return "auto"

    def create_dashboard_request(message: discord.Message, text: str, trigger: str, *, status: str = "received") -> tuple[str | None, bool]:
        identity = dict(source="discord", channel_id=str(message.channel.id),
                        user_id=str(message.author.id), message_id=str(message.id))
        if not dashboard_recording_enabled():
            if dashboard_store.find_agent_request_by_message(**identity, db_path=store.operations.path):
                return None, False
            return None, unrecorded_claims.claim(tuple(identity.values()))
        command = command_name(text)
        return dashboard_store.claim_agent_request(
            **identity,
            guild_id=str(getattr(getattr(message, "guild", None), "id", "") or ""),
            channel_name=str(getattr(message.channel, "name", "") or ""),
            trigger=trigger, command=command,
            mode="control" if classify(text).kind != "work_request" else request_mode(command),
            provider=str(config.get("provider") or ""), model=str(config.get("model") or ""),
            prompt=text, status=status,
            metadata={"author_name": str(getattr(message.author, "name", "") or ""),
                      "attachment_count": len(message.attachments)},
            db_path=store.operations.path,
        )

    def mark_dashboard_request(request_id: str | None, status: str, **kwargs: object) -> None:
        if not request_id:
            return
        try:
            dashboard_store.mark_request_status(request_id, status, db_path=store.operations.path, **kwargs)
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
        if not filename or filename in {".", ".."} or "\\" in filename:
            return None
        workspace = store.execution_workspace(f"discord-user:{message.author.id}")
        target_dir = new_task_directory(workspace, "attachments")
        target = scoped_path(workspace, target_dir / filename)
        # Exclusive creation: existing attachments and symlink targets are not overwritten.
        with target.open("xb") as output:
            await attachment.save(output)
        return target

    async def find_recent_attachments(message: discord.Message, filenames: set[str]) -> list[pathlib.Path]:
        if not filenames or not hasattr(message.channel, "history"):
            return []
        remaining = {name.lower() for name in filenames}
        found: list[pathlib.Path] = []
        limit = int(os.getenv("NYANYA_DISCORD_ATTACHMENT_SEARCH_LIMIT", "1000"))
        async for previous in message.channel.history(limit=limit):
            if previous.author.id != message.author.id:
                continue
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

    def is_file_share_target(channel: object) -> bool:
        channel_name = str(getattr(channel, "name", ""))
        return str(getattr(channel, "id", "")) in file_share_channel_ids or channel_name in file_share_channel_names

    async def upload_destination_channel(message: discord.Message):
        if is_file_share_channel(message) or not file_share_channel_ids:
            return message.channel
        for channel_id in file_share_channel_ids:
            try:
                return client.get_channel(int(channel_id)) or await client.fetch_channel(int(channel_id))
            except Exception as exc:  # noqa: BLE001 - try the next configured share channel.
                print(f"Discord file-share channel lookup failed: {type(exc).__name__}", file=sys.stderr, flush=True)
        raise SafeOperationError("Configured upload destination is unavailable; upload held")

    async def handle_command(message: discord.Message, text: str, attachment_note: str = "", request_id: str | None = None) -> str:
        owner_key = f"discord-user:{message.author.id}"
        conversation_key = f"discord:{message.channel.id}:user:{message.author.id}"
        command = command_name(text)
        loop = asyncio.get_running_loop()

        def finish(response: str, *, status: str = "completed", error: str | None = None, mode: str | None = None) -> str:
            actual_mode = mode or request_mode(command)
            if request_id and actual_mode == "control":
                dashboard_store.append_request_event(
                    request_id, "control.result", "Control response saved", {"response": response},
                    db_path=store.operations.path,
                )
            mark_dashboard_request(
                request_id,
                status,
                event_type=f"command_{status}",
                message=response or status,
                result_summary=response,
                error=error,
                mode=actual_mode,
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
                future = asyncio.run_coroutine_threadsafe(message.channel.send(chunk), loop)
                future.result(timeout=30)

        def queue_bound_upload(workspace, file_path, relative_path, expected_destination,
                               expected_sha, expected_identity, *, approval_id=None, supplied_hash=None):
            async def send_upload(cancel_event):
                channel = await upload_destination_channel(message)
                destination = upload_destination_key(channel)
                if destination != expected_destination:
                    if approval_id:
                        upload_approval.reject_upload(store.operations.path, approval_id, owner_key=owner_key, conversation_key=conversation_key)
                    raise SafeOperationError("Upload destination changed; request a new inspection")
                with open_upload_file(workspace, file_path, max_bytes=upload_byte_limit(channel)) as stream:
                    if stream.sha256 != expected_sha or stream.identity != expected_identity:
                        if approval_id:
                            upload_approval.reject_upload(store.operations.path, approval_id, owner_key=owner_key, conversation_key=conversation_key)
                        raise SafeOperationError("Upload file changed; request a new inspection")
                    if stream.privacy_counts and not approval_id:
                        raise SafeOperationError("Document requires privacy confirmation")
                    discord_file = discord.File(stream, filename=pathlib.Path(relative_path).name)
                    if cancel_event.is_set():
                        return TaskOutcome("cancelled", "문서 전송이 시작되기 전에 취소했습니다.")
                    if approval_id:
                        upload_approval.consume_upload(
                            store.operations.path, approval_id, owner_key=owner_key,
                            conversation_key=conversation_key, sha256=supplied_hash,
                            destination_id=destination, workspace=str(workspace),
                            relative_path=relative_path, file_identity=stream.identity,
                        )
                    # Consume immediately before one SDK call; never retry uncertain delivery.
                    await channel.send(content="문서 개인정보 패턴 검사를 수행했습니다. 무검출은 완전한 안전 보장이 아닙니다.", file=discord_file)
                return "문서 전송을 완료했습니다."

            def operation(task, cancel_event):
                if cancel_event.is_set():
                    return TaskOutcome("cancelled", "문서 전송이 시작되기 전에 취소했습니다.")
                future = asyncio.run_coroutine_threadsafe(send_upload(cancel_event), loop)
                while not future.done():
                    if cancel_event.wait(0.1):
                        future.cancel()
                        return TaskOutcome("blocked", "전송 중 취소 요청으로 전달 여부가 불확실합니다. 자동 재전송하지 않습니다.")
                try:
                    result = future.result()
                except SafeOperationError as exc:
                    return TaskOutcome("blocked", str(exc))
                except Exception:
                    return TaskOutcome("blocked", "문서 전달 여부가 불확실합니다. 목적지를 확인하세요. 자동 재전송하지 않습니다.")
                if isinstance(result, TaskOutcome):
                    return result
                store._dashboard_event(task, "file_uploaded", "Inspected document transferred", mode="upload")
                return result

            return store.submit(
                owner_key=owner_key, conversation_key=conversation_key,
                prompt="Explicit inspected document transfer", mode="upload",
                responder=lambda response: respond_later(response) if response else None,
                request_id=request_id, operation=operation,
            )

        if command in UPLOAD_CONFIRM_COMMANDS:
            args = text.split()
            try:
                if len(args) != (3 if command == "upload-approve" else 2):
                    raise SafeOperationError("Upload confirmation arguments are incomplete")
                record = upload_approval.get_upload(store.operations.path, args[1], owner_key=owner_key, conversation_key=conversation_key)
                if command != "upload-approve":
                    upload_approval.reject_upload(store.operations.path, args[1], owner_key=owner_key, conversation_key=conversation_key)
                    return finish("문서 전송 확인을 거절/취소했습니다. 전송하지 않았습니다.", mode="control")
                meta = record["metadata"]
                if str(message.channel.id) != meta["request_channel_id"]:
                    raise SafeOperationError("Use the original request channel")
                workspace = store.execution_workspace(owner_key)
                if str(workspace) != meta["workspace"]:
                    raise SafeOperationError("Registered upload workspace changed")
                return queue_bound_upload(workspace, meta["relative_path"], meta["relative_path"], meta["destination_id"], meta["sha256"], meta["file_identity"], approval_id=record["id"], supplied_hash=args[2])
            except OutcomeSignal as exc:
                return finish(exc.outcome.text, status=exc.outcome.status, mode="control")
            except (ValueError, PermissionError, OSError):
                return finish("문서 전송 확인을 보류했습니다. 요청자·원 채널·파일·목적지·만료를 확인하고 필요하면 새 업로드를 요청하세요.", status="blocked", mode="control")

        parts = text.split(maxsplit=1)
        scope = parts[1].strip().lower() if len(parts) > 1 else ""
        if command in TASK_STATUS_COMMANDS and scope in {"", "all", "전체", "global"}:
            show_all = bool(scope) and store.is_owner(str(message.author.id))
            if scope and not show_all:
                return finish("전체 작업 목록은 관리자만 조회할 수 있습니다.", status="failed", error="owner required", mode="control")
            return finish(store.task_status_text(None) if show_all else store.operations.handle_intent(
                "tasks", owner_key, conversation_key=conversation_key, request_id=request_id,
            ), mode="control")

        intent = classify(text)
        if intent.kind != "work_request":
            try:
                response = store.operations.handle_intent(
                    text, owner_key, conversation_key=conversation_key,
                    request_id=request_id, responder=respond_later,
                )
                return finish(response or "제어 요청을 해석하지 못했습니다.", mode="control")
            except (ValueError, PermissionError, OSError) as exc:
                return finish(
                    f"제어 요청을 처리하지 못했습니다: {type(exc).__name__}. 소유자와 대상 상태를 확인하세요.",
                    status="failed", mode="control",
                )

        if command in TASK_STATUS_COMMANDS:
            return finish("작업 목록 범위를 확인하세요. tasks 또는 tasks all을 사용하세요.", mode="control")

        if command in {'why', 'plan', 'approve', 'revoke', 'resume', 'reconcile', 'resolve', 'plan-file', 'open-draft', 'draft-show', 'draft-close', 'draft-feedback'} or (command == 'cancel' and len(text.split()) == 2):
            try:
                response = store.operations.control(text, owner_key, conversation_key=conversation_key, responder=respond_later)
                return finish(response or '명령 인자를 확인하세요.', mode='control')
            except (ValueError, PermissionError, OSError) as exc:
                return finish(f'제어 요청을 처리하지 못했습니다: {type(exc).__name__}. 소유자·상태·변경안 hash를 확인하세요.', status='failed', mode='control')

        if not text and attachment_note:
            text = "첨부파일 내용을 확인해 주세요."
            command = command_name(text)

        if command in {"result", "결과"}:
            parts = text.split(maxsplit=1)
            if len(parts) != 2:
                return finish("사용법: result 작업ID", mode="control")
            saved = work_queue.result(store.durable_tasks.db_path, parts[1].strip(), owner_key)
            if not saved:
                return finish("조회 가능한 저장 결과가 없습니다.", mode="control")
            current = execution_store.get_task(parts[1].strip(), db_path=store.operations.path)
            return finish(format_saved_result(saved, current), mode="control")
        if command in {"recovery", "복구"}:
            return finish(store.operations.control("recovery", owner_key), mode="control")

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
            return finish(store.operations.handle_intent("취소", owner_key, conversation_key=conversation_key), mode="control")
        if command in SET_HOME_COMMANDS:
            if not store.is_owner(str(message.author.id)):
                return finish("홈워크스페이스 설정은 관리자만 사용할 수 있습니다.", status="failed", error="owner required", mode="control")
            parts = text.split(maxsplit=2)
            if len(parts) < 3:
                return finish("사용법: set_home <user-id> /absolute/workspace/path", status="failed", error="missing arguments", mode="control")
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
            try:
                store.reset(conversation_key, owner_key=owner_key)
            except OutcomeSignal as exc:
                return finish(exc.outcome.text, status="blocked", mode="control")
            except (ValueError, PermissionError, OSError):
                return finish("대화 초기화를 보류했습니다. 등록된 작업공간과 대화 접근 권한을 확인해 주세요.", status="blocked", mode="control")
            return finish("이 대화의 이어받기 내용을 초기화했습니다. 작업과 승인 기록은 그대로 보존됩니다.", mode="control")
        if command in {"save", "/save"}:
            try:
                path = store.save(conversation_key, owner_key=owner_key)
            except OutcomeSignal as exc:
                return finish(exc.outcome.text, status="blocked", mode="control")
            except (ValueError, PermissionError, OSError):
                return finish("대화 저장을 보류했습니다. 등록된 작업공간과 안전한 저장 경로를 확인해 주세요.", status="blocked", mode="control")
            return finish(f"이 대화의 최근 내용을 비공개 파일로 저장했습니다: {path}" if path else "세션 저장이 꺼져 있습니다.", mode="control")
        if command in {"status", "/status"}:
            return finish(
                (
                    "NyaNya Agent bridge is running.\n"
                    f"provider={store.config.get('provider')}\n"
                    f"model={store.config.get('model')}\n"
                    f"작업 목록: {prefix} tasks"
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
                return finish("사용법: upload <파일_경로>", status="failed", mode="upload")
            file_path = parts[1].strip().strip("`\"'")
            try:
                workspace = store.execution_workspace(owner_key)
                resolved = scoped_path(workspace, file_path)
                relative_path = resolved.relative_to(workspace).as_posix()
                channel = await upload_destination_channel(message)
                destination = upload_destination_key(channel)
                with open_upload_file(workspace, file_path, max_bytes=upload_byte_limit(channel)) as stream:
                    digest, identity, counts = stream.sha256, stream.identity, stream.privacy_counts
                if counts:
                    record = upload_approval.request_upload(
                        store.operations.path, owner_key=owner_key, conversation_key=conversation_key,
                        workspace=str(workspace), relative_path=relative_path, destination_id=destination,
                        request_channel_id=str(message.channel.id), sha256=digest, file_identity=identity, counts=counts,
                    )
                    kinds = ", ".join(f"{kind}: {count}건" for kind, count in sorted(counts.items()))
                    notice = (
                        "문서 전송을 보류했습니다. 개인정보 패턴이 탐지됐습니다. 실제 값은 표시하지 않습니다.\n"
                        f"종류/개수: {kinds}\nSHA-256: {digest}\n목적지: <#{channel.id}>\n만료: {record['expires_at']}\n"
                        "원 요청자가 이 채널에서 이 파일과 목적지의 전송을 확인하세요.\n"
                        f"upload-approve {record['id']} {digest}\n"
                        f"upload-reject {record['id']} 또는 upload-cancel {record['id']}"
                    )
                    return finish(notice, status="blocked", mode="upload")
                return queue_bound_upload(workspace, file_path, relative_path, destination, digest, identity)
            except OutcomeSignal as exc:
                return finish(exc.outcome.text, status=exc.outcome.status, mode="upload")
            except (ValueError, PermissionError, OSError) as exc:
                reason = str(exc) if isinstance(exc, SafeOperationError) else "Secure document access or extraction failed"
                return finish(f"문서 전송을 보류했습니다: {reason}", status="blocked", mode="upload")
        return store.submit(
            owner_key=owner_key,
            conversation_key=conversation_key,
            prompt=prompt_with_attachments(text),
            mode="auto",
            responder=respond_later,
            request_id=request_id,
        )

    def recovery_message(tasks) -> str:
        if not tasks:
            return "확인이 필요한 이전 작업이 없습니다."
        lines = [f"이전 작업 {len(tasks)}개가 남아 있습니다. 자동 재실행하지 않았습니다."]
        lines.extend(f"- {item['id']}: {item['status']}" for item in tasks[:20])
        lines.append("why 작업ID로 원래 요청과 원인을 확인하세요. 안전한 요청은 resume 작업ID로 재시도하고, 파일 적용 중단은 reconcile 변경안ID로 확인하세요.")
        return "\n".join(lines)

    recovery_notice_task = None

    async def recovery_notice_loop() -> None:
        while not client.is_closed():
            try:
                from nyanya_agent import operation_store, reviewed_changes

                operation_store.recover(store.operations.path)
                reviewed_changes.settle_expired(store.operations.path)
                await report_recovery()
            except Exception as exc:
                print(f"Recovery inventory unavailable: {type(exc).__name__}", file=sys.stderr, flush=True)
            await asyncio.sleep(60)

    async def report_recovery() -> None:
        groups: set[tuple[str, str]] = set()
        from nyanya_agent.operation_store import recovery_inventory
        for item in recovery_inventory(store.operations.path):
            source_id = item.get("delivery_request_id")
            request = dashboard_store.get_request(source_id, db_path=store.durable_tasks.db_path) if source_id else None
            if not request or request.get("source") != "discord":
                continue
            owner = f"discord-user:{request['user_id']}"
            if store.workspace_for_owner(owner) is None:
                continue
            # Keep historical recovery notices within currently permitted destinations.
            if request["channel_id"] not in allowed_channel_ids and request["user_id"] not in allowed_user_ids:
                continue
            groups.add((request["channel_id"], owner))
        for channel_id, owner in groups:
            notice = workflow_notifications.prepare(store.operations.path, owner, source="discord", channel_id=channel_id)
            if not notice:
                continue
            try:
                channel = client.get_channel(int(channel_id)) or await client.fetch_channel(int(channel_id))
                await channel.send(notice.text.strip())
                workflow_notifications.delivered(store.operations.path, notice)
            except Exception as exc:
                print(f"Recovery notification pending: {type(exc).__name__}", file=sys.stderr, flush=True)

    @client.event
    async def on_ready() -> None:
        nonlocal phase_check_task, recovery_notice_task
        print("NyaNya Agent Discord bridge connected")
        if recovery_notice_task is None or recovery_notice_task.done():
            recovery_notice_task = asyncio.create_task(recovery_notice_loop())
        if phase_check_task is None or phase_check_task.done():
            phase_check_task = asyncio.create_task(phase_check_loop())

    @client.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot:
            return
        respond, text, trigger = should_respond(message)
        if not respond:
            return
        try:
            request_id, created = create_dashboard_request(message, text, trigger)
        except Exception as exc:  # noqa: BLE001 - fail closed before connector/task side effects.
            print(f"Discord intake held: {type(exc).__name__}", file=sys.stderr, flush=True)
            await reply(message, "요청 접수를 보류했습니다. 작업을 실행하지 않았습니다. 접수 기록과 저장소 상태를 확인하세요.")
            return
        if not created:
            return
        if is_file_share_channel(message):
            cmd = command_name(text)
            if trigger == "allowed_channel" and cmd not in {"upload", "/upload", "파일업로드", "/파일업로드", "sendfile", "file", *UPLOAD_CONFIRM_COMMANDS}:
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
            if classify(text).kind == "work_request" and request_mode(command_name(text)) != "control":
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

    discord.utils.setup_logging()
    try:
        asyncio.run(run_client(client, token, store))
    except KeyboardInterrupt:
        pass  # Preserve client.run's existing SIGINT behavior.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
