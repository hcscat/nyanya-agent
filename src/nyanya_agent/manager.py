#!/usr/bin/env python3
"""Operational CLI for nyanya-agent."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import plistlib
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any

from nyanya_agent import core as nyanya


LABEL = "com.hcs.nyanya.discord"


def run(command: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=check)


def launch_domain() -> str:
    return f"gui/{os.getuid()}"


def launch_agents_dir() -> pathlib.Path:
    return pathlib.Path.home() / "Library" / "LaunchAgents"


def plist_path(label: str = LABEL) -> pathlib.Path:
    return launch_agents_dir() / f"{label}.plist"


def project_root() -> pathlib.Path:
    return nyanya.PROJECT_ROOT


def python_executable() -> str:
    local_python = project_root() / ".venv" / "bin" / "python"
    if local_python.exists() and os.access(local_python, os.X_OK):
        return str(local_python)
    return sys.executable


def ensure_dirs() -> None:
    launch_agents_dir().mkdir(parents=True, exist_ok=True)
    (project_root() / "logs").mkdir(parents=True, exist_ok=True)
    (project_root() / "run").mkdir(parents=True, exist_ok=True)


def load_env() -> None:
    nyanya.load_env(nyanya.DEFAULT_ENV)


def discord_token() -> str:
    load_env()
    return os.getenv("NYANYA_DISCORD_BOT_TOKEN", "") or os.getenv("DISCORD_BOT_TOKEN", "")


def write_discord_plist() -> pathlib.Path:
    ensure_dirs()
    payload: dict[str, Any] = {
        "Label": LABEL,
        "ProgramArguments": [str(project_root() / "scripts" / "run_discord_bridge.sh")],
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(project_root() / "logs" / "discord.launchd.out.log"),
        "StandardErrorPath": str(project_root() / "logs" / "discord.launchd.err.log"),
        "WorkingDirectory": str(project_root()),
    }
    path = plist_path()
    with path.open("wb") as f:
        plistlib.dump(payload, f)
    return path


def bootout(label: str) -> None:
    run(["launchctl", "bootout", f"{launch_domain()}/{label}"], check=False)


def bootstrap(path: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return run(["launchctl", "bootstrap", launch_domain(), str(path)], check=False)


def kickstart(label: str = LABEL) -> subprocess.CompletedProcess[str]:
    return run(["launchctl", "kickstart", "-k", f"{launch_domain()}/{label}"], check=False)


def install() -> int:
    path = write_discord_plist()
    bootout(LABEL)
    result = bootstrap(path)
    if result.returncode != 0:
        sys.stderr.write(result.stderr or result.stdout)
        return result.returncode
    kick = kickstart()
    if kick.returncode != 0:
        sys.stderr.write(kick.stderr or kick.stdout)
        return kick.returncode
    print(f"installed={LABEL}")
    print(f"plist={path}")
    return 0


def stop() -> int:
    bootout(LABEL)
    print(f"stopped={LABEL}")
    return 0


def start() -> int:
    path = plist_path()
    if not path.exists():
        write_discord_plist()
    result = bootstrap(path)
    if result.returncode not in (0, 5):
        sys.stderr.write(result.stderr or result.stdout)
        return result.returncode
    kick = kickstart()
    if kick.returncode != 0:
        sys.stderr.write(kick.stderr or kick.stdout)
        return kick.returncode
    print(f"started={LABEL}")
    return 0


def restart() -> int:
    check_rc = check_config(include_backend=False)
    if check_rc != 0:
        return check_rc
    bootout(LABEL)
    return install()


def uninstall() -> int:
    bootout(LABEL)
    plist_path().unlink(missing_ok=True)
    print(f"removed={LABEL}")
    return 0


def status() -> int:
    result = run(["launchctl", "print", f"{launch_domain()}/{LABEL}"], check=False)
    if result.returncode != 0:
        print(f"{LABEL}: not loaded")
        return 1
    for line in result.stdout.splitlines():
        if "state =" in line or "pid =" in line or "last exit code =" in line:
            print(line.strip())
    return 0


def check_config(*, include_backend: bool = True) -> int:
    python = python_executable()
    commands = []
    if include_backend:
        commands.append([python, "-m", "nyanya_agent.core", "--check"])
    commands.append([python, "-m", "nyanya_agent.discord_bridge", "--check-config"])
    rc = 0
    for command in commands:
        result = run(command, check=False)
        if result.stdout:
            print(result.stdout.strip())
        if result.stderr:
            sys.stderr.write(result.stderr)
        rc = max(rc, result.returncode)
    return rc


def discord_api(method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    token = discord_token()
    if not token:
        raise RuntimeError("NYANYA_DISCORD_BOT_TOKEN is not configured")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request("https://discord.com/api/v10/users/@me", data=data, method=method)
    request.add_header("Authorization", f"Bot {token}")
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", "nyanya-agent/0.1.0")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def bot_name(name: str | None) -> int:
    try:
        if name:
            data = discord_api("PATCH", {"username": name})
        else:
            data = discord_api("GET")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        sys.stderr.write(f"discord_api_error={exc.code} {detail}\n")
        return 1
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"discord_api_error={exc}\n")
        return 1
    print(f"bot_username={data.get('username', '<unknown>')}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage nyanya-agent local services")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("install", "start", "stop", "restart", "uninstall", "status", "check", "preflight"):
        sub.add_parser(name)
    bot = sub.add_parser("bot-name")
    bot.add_argument("name", nargs="?", help="New Discord bot username. Omit to read current username.")
    return parser.parse_args()


def main() -> int:
    load_env()
    args = parse_args()
    if args.command == "install":
        return install()
    if args.command == "start":
        return start()
    if args.command == "stop":
        return stop()
    if args.command == "restart":
        return restart()
    if args.command == "uninstall":
        return uninstall()
    if args.command == "status":
        return status()
    if args.command == "check":
        return check_config()
    if args.command == "preflight":
        return check_config(include_backend=False)
    if args.command == "bot-name":
        return bot_name(args.name)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
