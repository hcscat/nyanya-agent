#!/usr/bin/env python3
"""Workspace, command, and routing policy helpers for NyaNya bridges."""

from __future__ import annotations

import os
import pathlib
import re

from nyanya_agent import core as nyanya
from nyanya_agent.bridge_constants import *

def _resolve_configured_path(value: str, *, default_base: pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(value).expanduser()
    if not path.is_absolute():
        path = default_base / path
    return path.resolve(strict=False)


def workspace_roots() -> list[pathlib.Path]:
    raw_roots = os.getenv("NYANYA_WORKSPACE_ROOTS", "").strip()
    if raw_roots:
        roots = [
            _resolve_configured_path(item.strip(), default_base=pathlib.Path.home())
            for item in raw_roots.split(",")
            if item.strip()
        ]
    else:
        raw = os.getenv("NYANYA_WORKSPACE_ROOT", "").strip()
        roots = [_resolve_configured_path(raw, default_base=pathlib.Path.home())] if raw else [pathlib.Path.home()]

    unique: list[pathlib.Path] = []
    for root in roots:
        if root == pathlib.Path("/"):
            continue
        if root not in unique:
            unique.append(root)
    return unique or [pathlib.Path.home().resolve(strict=False)]


def workspace_root() -> pathlib.Path:
    return workspace_roots()[0]


def workspace_config_path() -> pathlib.Path:
    raw = os.getenv("NYANYA_USER_WORKSPACES_FILE", "").strip()
    path = pathlib.Path(raw).expanduser() if raw else nyanya.PROJECT_ROOT / "config" / "user_workspaces.json"
    if not path.is_absolute():
        path = nyanya.PROJECT_ROOT / path
    return path.resolve(strict=False)


def resolve_workspace_path(value: str) -> pathlib.Path:
    if not value.strip():
        raise ValueError("워크스페이스 경로가 비어 있습니다.")
    roots = workspace_roots()
    candidate = pathlib.Path(value.strip()).expanduser()
    if not candidate.is_absolute():
        parts = candidate.parts
        matched_root = next((root for root in roots if parts and parts[0] == root.name), None)
        candidate = (matched_root / pathlib.Path(*parts[1:])) if matched_root else roots[0] / candidate
    resolved = candidate.resolve(strict=False)
    if not is_allowed_workspace_path(resolved):
        allowed = ", ".join(str(root) for root in roots)
        raise ValueError(f"워크스페이스는 다음 경로 하위여야 합니다: {allowed}")
    if resolved == pathlib.Path("/"):
        raise ValueError("파일시스템 루트(/)는 워크스페이스로 지정할 수 없습니다.")
    return resolved


def is_allowed_workspace_path(path: pathlib.Path) -> bool:
    resolved = path.expanduser().resolve(strict=False)
    for root in workspace_roots():
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def default_codex_workdir() -> pathlib.Path:
    configured_workdir = os.getenv("NYANYA_CODEX_WORKDIR", "").strip()
    workdir = pathlib.Path(configured_workdir).expanduser() if configured_workdir else workspace_root()
    resolved = workdir.resolve(strict=False)
    return resolved if is_allowed_workspace_path(resolved) else workspace_root()


def protected_delete_paths() -> list[pathlib.Path]:
    raw = os.getenv("NYANYA_PROTECTED_DELETE_PATHS", "").strip()
    items = [item.strip() for item in raw.split(",") if item.strip()] if raw else list(DEFAULT_PROTECTED_DELETE_PATHS)
    protected: list[pathlib.Path] = []
    for item in items:
        path = pathlib.Path(item).expanduser()
        if not path.is_absolute():
            path = nyanya.PROJECT_ROOT / path
        resolved = path.resolve(strict=False)
        if resolved not in protected:
            protected.append(resolved)
    return protected


def protected_delete_paths_text() -> str:
    return ", ".join(str(path) for path in protected_delete_paths())


def deletion_like_action_requested(prompt: str) -> bool:
    lowered = prompt.lower()
    action_text = lowered
    for phrase in FILE_MUTATION_NEGATIONS:
        action_text = action_text.replace(phrase, "")
    return any(keyword in action_text for keyword in PROTECTED_DELETE_KEYWORDS)


def _path_touches_protected_delete_path(path: pathlib.Path) -> pathlib.Path | None:
    resolved = path.expanduser().resolve(strict=False)
    for protected in protected_delete_paths():
        try:
            resolved.relative_to(protected)
            return protected
        except ValueError:
            pass
        try:
            protected.relative_to(resolved)
            return protected
        except ValueError:
            pass
    return None


def _prompt_path_candidates(prompt: str, *, workdir: pathlib.Path) -> list[pathlib.Path]:
    candidates: list[pathlib.Path] = []
    pattern = r"(?<![A-Za-z0-9_./~-])(?:~?/|/Users/|[A-Za-z0-9_.-]+/)[^\s`'\"<>]+|[A-Za-z0-9_.-]+\.(?:py|js|jsx|ts|tsx|md|txt|json|toml|ya?ml|csv|tsv|html?|css|scss|sh|sql|env|ini|cfg|log|zip|tar|tgz|gz|7z)"
    for match in re.finditer(pattern, prompt):
        raw = match.group(0).strip(".,;:)]}，。")
        if not raw:
            continue
        path = pathlib.Path(raw).expanduser()
        if path.is_absolute():
            resolved = path.resolve(strict=False)
        else:
            try:
                resolved = resolve_workspace_path(raw)
            except ValueError:
                resolved = (workdir / path).resolve(strict=False)
        if resolved not in candidates:
            candidates.append(resolved)
    return candidates


def protected_delete_violation(prompt: str, *, workdir: pathlib.Path) -> str | None:
    if not deletion_like_action_requested(prompt):
        return None

    lowered = prompt.lower()
    for candidate in _prompt_path_candidates(prompt, workdir=workdir):
        protected = _path_touches_protected_delete_path(candidate)
        if protected is not None:
            return f"보호 경로 `{protected}`에 영향을 줄 수 있습니다."

    protected_aliases: set[str] = set()
    for protected in protected_delete_paths():
        protected_aliases.add(str(protected).lower())
        try:
            relative = str(protected.relative_to(nyanya.PROJECT_ROOT))
            protected_aliases.add(relative.lower())
            protected_aliases.add(f"nyanya-agent/{relative}".lower())
            if protected.exists() and protected.is_dir():
                protected_aliases.add(f"{relative.lower()}/")
                protected_aliases.add(f"nyanya-agent/{relative.lower()}/")
            else:
                protected_aliases.add(protected.name.lower())
        except ValueError:
            protected_aliases.add(protected.name.lower())

    if any(alias and alias in lowered for alias in protected_aliases):
        return "NyaNya 핵심 파일 또는 디렉토리를 직접 가리키고 있습니다."
    if any(keyword in lowered for keyword in ("nyanya-agent", "nyanya agent", "냐냐", "nyanya")) and any(
        keyword in lowered for keyword in ("전체", "관련 파일", "폴더", "디렉토리", "프로젝트")
    ):
        return "NyaNya 에이전트 핵심 파일 삭제로 해석될 수 있습니다."
    return None


def normalize_owner_key(target: str, default_platform: str) -> str:
    cleaned = target.strip().strip("<>@!")
    if cleaned.startswith(("discord-user:", "telegram-user:")):
        return cleaned
    if cleaned.startswith("discord:"):
        return f"discord-user:{cleaned.split(':', 1)[1]}"
    if cleaned.startswith("telegram:"):
        return f"telegram-user:{cleaned.split(':', 1)[1]}"
    if default_platform not in {"discord", "telegram"}:
        raise ValueError(f"지원하지 않는 플랫폼입니다: {default_platform}")
    return f"{default_platform}-user:{cleaned}"


def command_name(text: str) -> str:
    if not text.strip():
        return ""
    token = text.split(maxsplit=1)[0].lower()
    if token.startswith("/") and "@" in token:
        token = token.split("@", 1)[0]
    return token


def discord_help_text(*, prefix: str, channel_id: str, user_id: str, is_admin: bool) -> str:
    admin_note = (
        "\n관리자 명령:\n"
        f"- `{prefix} set_home <discord_user_id> <workspace_path_or_alias>`: 사용자 작업 폴더 지정\n"
        f"- `{prefix} unset_home <discord_user_id>`: 사용자 홈워크스페이스 설정 해제\n"
        f"- `{prefix} 사용자취소 <discord_user_id>`: 특정 사용자 진행/대기 작업 취소\n"
        f"- `{prefix} 전체취소`: 전체 사용자 작업 취소\n"
        "- Telegram 사용자를 지정할 때는 `telegram-user:<id>`처럼 플랫폼 접두어를 붙입니다."
    )
    if not is_admin:
        admin_note = "\n관리자 명령은 등록된 관리자만 사용할 수 있습니다."

    return (
        "NyaNya Discord 명령어\n"
        f"channel_id={channel_id}\nuser_id={user_id}\n\n"
        "도움말 보기:\n"
        f"- `{prefix} help`\n"
        f"- `{prefix} commands`\n"
        f"- `{prefix} 명령어`\n"
        "- DM에서는 접두어 없이 `help` 또는 `commands`\n\n"
        "기본 사용:\n"
        f"- `{prefix} 질문`: Antigravity CLI가 기본 답변\n"
        f"- `{prefix} gemini 질문`: Google CLI로 직접 답변\n"
        f"- `{prefix} codex 검수/조사 내용`: Codex CLI 읽기 전용 위임\n"
        f"- `{prefix} codex-work 파일 생성/수정 요청`: Codex CLI 쓰기 작업 위임\n"
        "- 난이도 높은 파일/코딩/데이터 작업과 Chrome 조작 작업은 자동으로 Codex에 위임\n"
        f"- `{prefix} resources`: CPU/메모리 상위 프로세스 조회\n"
        f"- `{prefix} status`: 브리지 실행 상태\n"
        f"- `{prefix} config`: 현재 설정 요약\n"
        f"- `{prefix} home`: 내 홈워크스페이스 확인\n"
        f"- `{prefix} reset`: 내 대화 컨텍스트 초기화\n"
        f"- `{prefix} save`: 내 대화 기록 저장\n\n"
        "작업 제어:\n"
        f"- `{prefix} 취소`: 내 진행/대기 작업 모두 취소\n"
        f"- `{prefix} cancel`: 위와 동일\n"
        "- 사용자별로 1개 실행, 2개 대기까지 허용됩니다.\n"
        f"{admin_note}"
    )


def telegram_help_text(*, chat_id: str, user_id: str, is_admin: bool) -> str:
    admin_note = (
        "\n관리자 명령:\n"
        "- `/set_home <telegram_user_id> <workspace_path_or_alias>`: 사용자 작업 폴더 지정\n"
        "- `/set_home discord-user:<discord_user_id> <workspace_path_or_alias>`: Discord 사용자 작업 폴더 지정\n"
        "- `/unset_home <user_id>`: 사용자 홈워크스페이스 설정 해제\n"
        "- `사용자취소 <user_id>`: 특정 사용자 진행/대기 작업 취소\n"
        "- `전체취소`: 전체 사용자 작업 취소"
    )
    if not is_admin:
        admin_note = "\n관리자 명령은 등록된 관리자만 사용할 수 있습니다."

    return (
        "NyaNya Telegram 명령어\n"
        f"chat_id={chat_id}\nuser_id={user_id}\n\n"
        "도움말 보기:\n"
        "- `/help`\n"
        "- `/commands`\n"
        "- `/명령어`\n\n"
        "기본 사용:\n"
        "- `일반 질문`: Antigravity CLI가 기본 답변\n"
        "- `/gemini 질문`: Google CLI로 직접 답변\n"
        "- `/codex 검수/조사 내용`: Codex CLI 읽기 전용 위임\n"
        "- `/codex_work 파일 생성/수정 요청`: Codex CLI 쓰기 작업 위임\n"
        "- 난이도 높은 파일/코딩/데이터 작업과 Chrome 조작 작업은 자동으로 Codex에 위임\n"
        "- `/resources`: CPU/메모리 상위 프로세스 조회\n"
        "- `/status`: 브리지 실행 상태\n"
        "- `/config`: 현재 설정 요약\n"
        "- `/home`: 내 홈워크스페이스 확인\n"
        "- `/reset`: 내 대화 컨텍스트 초기화\n"
        "- `/save`: 내 대화 기록 저장\n\n"
        "작업 제어:\n"
        "- `취소`: 내 진행/대기 작업 모두 취소\n"
        "- `/cancel`: 위와 동일\n"
        "- 사용자별로 1개 실행, 2개 대기까지 허용됩니다.\n"
        f"{admin_note}"
    )
