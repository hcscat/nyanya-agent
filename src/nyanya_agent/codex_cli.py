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
