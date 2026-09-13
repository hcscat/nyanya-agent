"""Task-scoped local file boundaries, independent of model instructions."""

from datetime import datetime
from pathlib import Path
import re
from uuid import uuid4


def scoped_path(workspace: Path, value: str | Path) -> Path:
    root = workspace.expanduser().resolve(strict=True)
    if not root.is_dir() or root == Path(root.anchor):
        raise ValueError("Invalid workspace")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(root):
        raise ValueError("Path is outside the assigned workspace")
    return resolved


def new_task_directory(workspace: Path, kind: str) -> Path:
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", kind):
        raise ValueError("Invalid task kind")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = scoped_path(workspace, f"nyanya-tasks/{kind}/{stamp}-{uuid4().hex[:8]}")
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    return destination
