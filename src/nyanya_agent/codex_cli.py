"""Shared, fail-closed Codex executable discovery for operations and bridges."""

from __future__ import annotations

import os
from pathlib import Path
import shutil


def resolve_codex_cli() -> str | None:
    """Respect explicit configuration; never silently replace a broken override."""
    configured = os.getenv("NYANYA_CODEX_CLI", "").strip()
    candidate = configured or "codex"
    expanded = os.path.expanduser(candidate)
    resolved = shutil.which(expanded)
    if resolved and Path(resolved).is_file():
        return resolved
    return None


def codex_launch_error(exc: OSError) -> str:
    """Describe OS failures without leaking executable or workspace paths."""
    import errno

    reasons = {
        errno.ENOENT: "실행 파일 또는 작업 폴더가 없습니다. Codex 경로와 작업 폴더를 확인하세요.",
        errno.EACCES: "실행 권한이 없습니다. 파일 실행 권한과 작업 폴더 접근 권한을 확인하세요.",
        errno.EPERM: "운영체제 보안 정책이 실행을 거부했습니다. 필요한 권한을 확인하세요.",
        errno.ENOEXEC: "실행 파일 형식이 올바르지 않습니다. 설치 파일과 운영체제 호환성을 확인하세요.",
    }
    return f"Codex 실행 불가 (errno={exc.errno}): " + reasons.get(
        exc.errno, "운영체제에서 프로세스를 시작하지 못했습니다. 로컬 실행 환경을 점검하세요."
    )
