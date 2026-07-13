"""Resolve immutable package paths separately from mutable user state."""

from __future__ import annotations

import os
import pathlib
import sys


SOURCE_ROOT = pathlib.Path(__file__).resolve().parents[2]


def resolve_code_root() -> pathlib.Path:
    configured = os.getenv("NYANYA_PROJECT_ROOT", "").strip()
    if configured:
        return pathlib.Path(configured).expanduser().resolve(strict=False)
    cwd = pathlib.Path.cwd()
    if (cwd / "config" / "nyanya.json").exists() and (cwd / "src" / "nyanya_agent").exists():
        return cwd.resolve(strict=False)
    return SOURCE_ROOT.resolve(strict=False)


def default_user_state_root(
    *,
    platform: str | None = None,
    home: pathlib.Path | None = None,
    env: dict[str, str] | None = None,
) -> pathlib.Path:
    platform = platform or sys.platform
    home = (home or pathlib.Path.home()).expanduser()
    env = env or dict(os.environ)
    if platform == "darwin":
        return home / "Library" / "Application Support" / "NyaNya Agent"
    if platform.startswith("win"):
        base = pathlib.Path(env.get("LOCALAPPDATA", str(home / "AppData" / "Local"))).expanduser()
        return base / "NyaNya Agent"
    base = pathlib.Path(env.get("XDG_DATA_HOME", str(home / ".local" / "share"))).expanduser()
    return base / "nyanya-agent"


def resolve_state_root(code_root: pathlib.Path | None = None) -> pathlib.Path:
    code_root = (code_root or resolve_code_root()).resolve(strict=False)
    configured = os.getenv("NYANYA_HOME", "").strip()
    if configured:
        return pathlib.Path(configured).expanduser().resolve(strict=False)
    configured_env = os.getenv("NYANYA_ENV_FILE", "").strip()
    if configured_env:
        return pathlib.Path(configured_env).expanduser().resolve(strict=False).parent
    if (code_root / ".env").exists():
        return code_root
    return default_user_state_root().resolve(strict=False)


CODE_ROOT = resolve_code_root()
STATE_ROOT = resolve_state_root(CODE_ROOT)
ENV_FILE = pathlib.Path(os.getenv("NYANYA_ENV_FILE", str(STATE_ROOT / ".env"))).expanduser().resolve(strict=False)
VENV_ROOT = STATE_ROOT / ".venv"


def code_path(value: str | os.PathLike[str]) -> pathlib.Path:
    path = pathlib.Path(value).expanduser()
    return path.resolve(strict=False) if path.is_absolute() else (CODE_ROOT / path).resolve(strict=False)


def state_path(value: str | os.PathLike[str]) -> pathlib.Path:
    path = pathlib.Path(value).expanduser()
    return path.resolve(strict=False) if path.is_absolute() else (STATE_ROOT / path).resolve(strict=False)
