#!/usr/bin/env python3
"""Bounded local developer launcher for the public source copy.

This launcher deliberately has no application imports.  It prepares an
isolated environment and executes a small, fixed command set from the source
tree.  Production service, setup, and manager commands are outside its
interface; the terminal command is opt-in and is never exercised automatically.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
import secrets
from pathlib import Path
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence


COMMANDS = ("paths", "test", "lint", "typecheck", "build", "dashboard", "terminal")
DEFAULT_DASHBOARD_HOST = "127.0.0.1"
DEFAULT_DASHBOARD_PORT = 8875
DEV_SERVICE_PREFIX = "com.hcs.nyanya.dev"
_REMOVED_ENV_KEYS = {"PYTHONHOME", "PYTHONPATH", "PYTHONUSERBASE", "VIRTUAL_ENV"}
_REMOVED_CREDENTIAL_KEYS = {
    "ANTHROPIC_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "COHERE_API_KEY",
    "DISCORD_BOT_TOKEN",
    "GEMINI_API_KEY",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GOOGLE_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GROQ_API_KEY",
    "MISTRAL_API_KEY",
    "NPM_TOKEN",
    "OPENAI_API_KEY",
    "PERPLEXITY_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TOGETHER_API_KEY",
    "XAI_API_KEY",
}
_DEFAULT_PATH = "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


class DevLauncherError(RuntimeError):
    """A bounded, user-actionable developer launcher failure."""


@dataclass(frozen=True)
class DevLayout:
    """Source-local paths used by the launcher."""

    project_root: Path
    state_root: Path
    env_file: Path
    venv_root: Path
    venv_python: Path


Executor = Callable[..., int]


def _project_root(script_path: Path | None = None) -> Path:
    """Resolve the checked-out source root from this script, not from CWD."""

    script = (script_path or Path(__file__)).resolve(strict=True)
    root = script.parent.parent.resolve(strict=True)
    if not root.is_dir():
        raise DevLauncherError("source project root is not a directory")
    return root


def _guard_local_path(path: Path, root: Path, label: str, *, directory: bool = False) -> None:
    """Reject symlink escapes and non-directory paths under the source root."""

    # A direct symlink is rejected even when it points back into the source
    # tree.  This keeps mutable state and the venv identity stable.
    if path.is_symlink():
        raise DevLauncherError(f"{label} must not be a symlink")
    if path.exists():
        if directory and not path.is_dir():
            raise DevLauncherError(f"{label} must be a directory")
        resolved = path.resolve(strict=True)
    else:
        resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise DevLauncherError(f"{label} must stay inside the source tree") from exc


def layout(project_root: Path | None = None) -> DevLayout:
    """Return and validate source-local paths without creating anything."""

    root = (project_root or _project_root()).resolve(strict=True)
    if not root.is_dir():
        raise DevLauncherError("source project root is not a directory")
    state_root = root / ".dev-state"
    venv_root = root / ".venv"
    env_file = state_root / ".env"
    _guard_local_path(state_root, root, "developer state root", directory=True)
    _guard_local_path(venv_root, root, "developer virtual environment", directory=True)
    _guard_local_path(env_file, root, "developer environment file")
    return DevLayout(root, state_root, env_file, venv_root, venv_root / "bin" / "python")


def _require_venv(dev_layout: DevLayout, command: str) -> Path:
    """Return the local interpreter or fail without creating/installing it."""

    if not dev_layout.venv_root.is_dir() or dev_layout.venv_root.is_symlink():
        raise DevLauncherError(f"local .venv is required for '{command}'; create it under the source tree")
    python = dev_layout.venv_python
    if not python.is_file() or not os.access(python, os.X_OK):
        raise DevLauncherError(f"local .venv Python is unavailable for '{command}'")
    # The venv directory itself must be local; its normal interpreter symlink
    # may point at the interpreter used to create the venv.
    _guard_local_path(dev_layout.venv_root, dev_layout.project_root, "developer virtual environment", directory=True)
    return python


def _ensure_runtime_state(dev_layout: DevLayout) -> None:
    """Create private runtime directories only for commands that need them."""

    _guard_local_path(dev_layout.state_root, dev_layout.project_root, "developer state root", directory=True)
    if not dev_layout.state_root.exists():
        dev_layout.state_root.mkdir(mode=0o700)
    for name in ("data", "logs", "run", "sessions", ".npm-cache"):
        child = dev_layout.state_root / name
        _guard_local_path(child, dev_layout.project_root, f"developer state {name}", directory=True)
        if not child.exists():
            child.mkdir(mode=0o700)


def isolated_environment(dev_layout: DevLayout) -> dict[str, str]:
    """Build an environment that cannot inherit production NyaNya settings."""

    environment = dict(os.environ)
    for key in tuple(environment):
        if key.startswith("NYANYA_") or key in _REMOVED_ENV_KEYS or key in _REMOVED_CREDENTIAL_KEYS:
            environment.pop(key, None)

    environment.update(
        {
            "NYANYA_PROJECT_ROOT": str(dev_layout.project_root),
            "NYANYA_HOME": str(dev_layout.state_root),
            "NYANYA_ENV_FILE": str(dev_layout.env_file),
            "NYANYA_SERVICE_LABEL_PREFIX": DEV_SERVICE_PREFIX,
            "NYANYA_DASHBOARD_HOST": DEFAULT_DASHBOARD_HOST,
            "NYANYA_DASHBOARD_PORT": str(DEFAULT_DASHBOARD_PORT),
            "NYANYA_DASHBOARD_DB_PATH": str(dev_layout.state_root / "data" / "nyanya_dashboard.db"),
            "NYANYA_SESSIONS_DIR": str(dev_layout.state_root / "sessions"),
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": str(dev_layout.project_root / "src"),
            "NPM_CONFIG_CACHE": str(dev_layout.state_root / ".npm-cache"),
        }
    )
    venv_bin = str(dev_layout.venv_root / "bin")
    environment["PATH"] = os.pathsep.join((venv_bin, environment.get("PATH", _DEFAULT_PATH)))
    return environment


def command_argv(command: str, python: Path | None = None) -> list[str]:
    """Return one of the fixed command vectors; extra arguments are impossible."""

    if command not in COMMANDS or command == "paths":
        raise DevLauncherError(f"unsupported developer command: {command}")
    if command == "test":
        assert python is not None
        return [str(python), "-m", "pytest", "tests/"]
    if command == "lint":
        assert python is not None
        return [str(python), "-m", "ruff", "check", "src", "tests", "scripts/dev.py"]
    if command == "typecheck":
        return ["npm", "run", "typecheck"]
    if command == "build":
        return ["npm", "run", "build"]
    if command == "dashboard":
        assert python is not None
        return [str(python), "-m", "nyanya_agent.dashboard_api"]
    if command == "terminal":
        assert python is not None
        return [str(python), "-m", "nyanya_agent.core"]
    raise DevLauncherError(f"unsupported developer command: {command}")


def _execute(argv: Sequence[str], *, cwd: Path, env: Mapping[str, str]) -> int:
    return subprocess.run(list(argv), cwd=cwd, env=dict(env), check=False).returncode


def paths_report(dev_layout: DevLayout) -> dict[str, object]:
    """Return JSON-safe diagnostics without importing application modules."""

    return {
        "project_root": str(dev_layout.project_root),
        "state_root": str(dev_layout.state_root),
        "state_exists": dev_layout.state_root.is_dir(),
        "env_file": str(dev_layout.env_file),
        "env_file_exists": dev_layout.env_file.is_file(),
        "venv_root": str(dev_layout.venv_root),
        "venv_exists": dev_layout.venv_root.is_dir(),
        "venv_python": str(dev_layout.venv_python),
        "venv_python_exists": dev_layout.venv_python.is_file(),
        "dashboard_host": DEFAULT_DASHBOARD_HOST,
        "dashboard_port": DEFAULT_DASHBOARD_PORT,
    }


def run_command(
    command: str,
    *,
    project_root: Path | None = None,
    executor: Executor | None = None,
) -> int:
    """Run one fixed developer command or print the local paths report."""

    if command not in COMMANDS:
        raise DevLauncherError(f"unsupported developer command: {command}")
    dev_layout = layout(project_root)
    if command == "paths":
        print(json.dumps(paths_report(dev_layout), sort_keys=True))
        return 0

    python = _require_venv(dev_layout, command)
    if command in {"dashboard", "terminal"}:
        _ensure_runtime_state(dev_layout)
    if command == "dashboard":
        token_file = dev_layout.state_root / "data" / "dashboard_control.token"
        _guard_local_path(token_file, dev_layout.project_root, "developer dashboard token")
        try:
            fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(secrets.token_urlsafe(32) + "\n")
    env = isolated_environment(dev_layout)
    argv = command_argv(command, python)
    runner = executor or _execute
    return int(runner(argv, cwd=dev_layout.project_root, env=env))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run bounded source-local developer checks.")
    parser.add_argument("command", choices=COMMANDS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return run_command(args.command)
    except DevLauncherError as exc:
        print(f"developer launcher unavailable: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
