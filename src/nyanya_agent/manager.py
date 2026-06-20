#!/usr/bin/env python3
"""Operational CLI for nyanya-agent."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import plistlib
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any

from nyanya_agent import core as nyanya


DISCORD_LABEL = "com.hcs.nyanya.discord"
DASHBOARD_LABEL = "com.hcs.nyanya.dashboard"
MEMORY_WORKER_LABEL = "com.hcs.nyanya.memory-worker"
CODEX_LABEL = "com.hcs.codex.app"
CODEX_APP_NAME = "Codex"
CODEX_APP_PATH = pathlib.Path("/Applications/Codex.app")
LABEL = DISCORD_LABEL
DEFAULT_RUNTIME_PATH = "/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/local/sbin:/usr/bin:/bin:/usr/sbin:/sbin"


def run(command: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=check)


def launch_domain() -> str:
    return f"gui/{os.getuid()}"


def launch_agents_dir() -> pathlib.Path:
    return pathlib.Path.home() / "Library" / "LaunchAgents"


def plist_path(label: str = DISCORD_LABEL) -> pathlib.Path:
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


def resolve_executable(command: str) -> str | None:
    expanded = str(pathlib.Path(command).expanduser()) if command.startswith(("~", "/")) else command
    found = shutil.which(expanded)
    if found:
        return found
    candidate = pathlib.Path(expanded)
    if candidate.exists() and os.access(candidate, os.X_OK):
        return str(candidate)
    return None


def configured_codex_cli() -> str | None:
    load_env()
    candidates = [
        os.getenv("NYANYA_CODEX_CLI", "").strip(),
        "codex",
        str(CODEX_APP_PATH / "Contents" / "Resources" / "codex"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        resolved = resolve_executable(candidate)
        if resolved:
            return resolved
    return None


def matching_processes(pattern: str) -> list[str]:
    result = run(["ps", "-axo", "pid=,command="], check=False)
    if result.returncode != 0:
        return []
    regex = re.compile(pattern)
    lines: list[str] = []
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if regex.search(stripped):
            lines.append(stripped)
    return lines


def write_discord_plist() -> pathlib.Path:
    ensure_dirs()
    payload: dict[str, Any] = {
        "Label": LABEL,
        "ProgramArguments": [str(project_root() / "scripts" / "run_discord_bridge.sh")],
        "EnvironmentVariables": {"PATH": DEFAULT_RUNTIME_PATH},
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


def write_codex_plist() -> pathlib.Path:
    ensure_dirs()
    payload: dict[str, Any] = {
        "Label": CODEX_LABEL,
        "ProgramArguments": ["/usr/bin/open", "-a", CODEX_APP_NAME],
        "EnvironmentVariables": {"PATH": DEFAULT_RUNTIME_PATH},
        "RunAtLoad": True,
        "KeepAlive": False,
        "StandardOutPath": str(project_root() / "logs" / "codex.launchd.out.log"),
        "StandardErrorPath": str(project_root() / "logs" / "codex.launchd.err.log"),
        "WorkingDirectory": str(pathlib.Path.home()),
    }
    path = plist_path(CODEX_LABEL)
    with path.open("wb") as f:
        plistlib.dump(payload, f)
    return path


def write_dashboard_plist() -> pathlib.Path:
    ensure_dirs()
    payload: dict[str, Any] = {
        "Label": DASHBOARD_LABEL,
        "ProgramArguments": [str(project_root() / "scripts" / "run_dashboard.sh")],
        "EnvironmentVariables": {"PATH": DEFAULT_RUNTIME_PATH},
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(project_root() / "logs" / "dashboard.launchd.out.log"),
        "StandardErrorPath": str(project_root() / "logs" / "dashboard.launchd.err.log"),
        "WorkingDirectory": str(project_root()),
    }
    path = plist_path(DASHBOARD_LABEL)
    with path.open("wb") as f:
        plistlib.dump(payload, f)
    return path


def write_memory_worker_plist() -> pathlib.Path:
    ensure_dirs()
    payload: dict[str, Any] = {
        "Label": MEMORY_WORKER_LABEL,
        "ProgramArguments": [str(project_root() / "scripts" / "run_memory_worker.sh")],
        "EnvironmentVariables": {"PATH": DEFAULT_RUNTIME_PATH},
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(project_root() / "logs" / "memory-worker.launchd.out.log"),
        "StandardErrorPath": str(project_root() / "logs" / "memory-worker.launchd.err.log"),
        "WorkingDirectory": str(project_root()),
    }
    path = plist_path(MEMORY_WORKER_LABEL)
    with path.open("wb") as f:
        plistlib.dump(payload, f)
    return path


def bootout(label: str) -> None:
    run(["launchctl", "bootout", f"{launch_domain()}/{label}"], check=False)


def bootstrap(path: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return run(["launchctl", "bootstrap", launch_domain(), str(path)], check=False)


def kickstart(label: str = LABEL) -> subprocess.CompletedProcess[str]:
    return run(["launchctl", "kickstart", "-k", f"{launch_domain()}/{label}"], check=False)


def launch_status(label: str) -> tuple[int, list[str]]:
    result = run(["launchctl", "print", f"{launch_domain()}/{label}"], check=False)
    if result.returncode != 0:
        return result.returncode, [f"{label}: not loaded"]
    lines = [
        line.strip()
        for line in result.stdout.splitlines()
        if "state =" in line or "pid =" in line or "last exit code =" in line
    ]
    return 0, lines


def install() -> int:
    path = write_discord_plist()
    bootout(DISCORD_LABEL)
    result = bootstrap(path)
    if result.returncode != 0:
        sys.stderr.write(result.stderr or result.stdout)
        return result.returncode
    kick = kickstart(DISCORD_LABEL)
    if kick.returncode != 0:
        sys.stderr.write(kick.stderr or kick.stdout)
        return kick.returncode
    print(f"installed={DISCORD_LABEL}")
    print(f"plist={path}")
    return 0


def stop() -> int:
    bootout(DISCORD_LABEL)
    print(f"stopped={DISCORD_LABEL}")
    return 0


def start() -> int:
    path = plist_path()
    if not path.exists():
        write_discord_plist()
    result = bootstrap(path)
    if result.returncode not in (0, 5):
        sys.stderr.write(result.stderr or result.stdout)
        return result.returncode
    kick = kickstart(DISCORD_LABEL)
    if kick.returncode != 0:
        sys.stderr.write(kick.stderr or kick.stdout)
        return kick.returncode
    print(f"started={DISCORD_LABEL}")
    return 0


def restart() -> int:
    check_rc = check_config(include_backend=False)
    if check_rc != 0:
        return check_rc
    bootout(DISCORD_LABEL)
    return install()


def uninstall() -> int:
    bootout(DISCORD_LABEL)
    plist_path().unlink(missing_ok=True)
    print(f"removed={DISCORD_LABEL}")
    return 0


def status() -> int:
    rc, lines = launch_status(DISCORD_LABEL)
    for line in lines:
        print(line)
    return 0 if rc == 0 else 1


def start_all() -> int:
    print("runtime_entrypoint=discord_bridge")
    print("dashboard=nyanya_dashboard")
    print("memory_worker=nyanya_memory_worker")
    print("codex_policy=separate_recovery_channel_not_managed_by_start_all")
    discord_rc = start()
    dashboard_rc = dashboard_start()
    memory_rc = memory_worker_start()
    return 0 if discord_rc == 0 and dashboard_rc == 0 and memory_rc == 0 else 1


def restart_all() -> int:
    print("runtime_entrypoint=discord_bridge")
    print("dashboard=nyanya_dashboard")
    print("memory_worker=nyanya_memory_worker")
    print("codex_policy=separate_recovery_channel_not_managed_by_restart_all")
    discord_rc = restart()
    dashboard_rc = dashboard_restart()
    memory_rc = memory_worker_restart()
    return 0 if discord_rc == 0 and dashboard_rc == 0 and memory_rc == 0 else 1


def status_all() -> int:
    print("runtime_entrypoint=discord_bridge")
    print("codex_policy=separate_recovery_channel")
    print("[discord_bridge]")
    discord_rc = status()
    print("[dashboard]")
    dashboard_rc = dashboard_status()
    print("[memory_worker]")
    memory_rc = memory_worker_status()
    print("[codex]")
    codex_rc = codex_status()
    return 0 if discord_rc == 0 and dashboard_rc == 0 and memory_rc == 0 and codex_rc in (0, 1) else 1


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


def health() -> int:
    rc = 0
    print("runtime_entrypoint=discord_bridge")
    print("codex_policy=separate_recovery_channel")
    print("[launchagent]")
    launch_rc, lines = launch_status(DISCORD_LABEL)
    for line in lines:
        print(line)
    if launch_rc != 0:
        rc = max(rc, 1)

    print("[config]")
    rc = max(rc, check_config(include_backend=False))

    print("[discord_api]")
    try:
        data = discord_api("GET")
        print(f"bot_username={data.get('username', '<unknown>')}")
    except Exception as exc:  # noqa: BLE001
        print(f"discord_api_ok=false reason={exc}", file=sys.stderr)
        rc = max(rc, 1)

    print("[codex_separate]")
    codex_cli = configured_codex_cli()
    print(f"codex_cli_configured={bool(codex_cli)}")
    if codex_cli:
        print(f"codex_cli={codex_cli}")
    if os.getenv("NYANYA_CODEX_ENABLED", "").strip().lower() in {"1", "true", "yes", "y", "on"} and not codex_cli:
        rc = max(rc, 1)
    print("[dashboard_db]")
    try:
        from nyanya_agent import dashboard_store

        dashboard_store.init_db()
        print(f"dashboard_db={dashboard_store.resolve_db_path()}")
    except Exception as exc:  # noqa: BLE001
        print(f"dashboard_db_ok=false reason={exc}", file=sys.stderr)
        rc = max(rc, 1)
    return rc


def deep_health() -> int:
    print("deep_health=true")
    rc = health()
    print("[dashboard_http]")
    rc = max(rc, dashboard_health())
    print("[backend]")
    rc = max(rc, auth())
    print("[smoke]")
    rc = max(rc, smoke())
    return rc


def smoke() -> int:
    rc = 0
    print("smoke_mode=local_no_discord_message")
    print("runtime_entrypoint=discord_bridge")
    try:
        from nyanya_agent.bridge_policy import default_codex_workdir, protected_delete_violation

        violation = protected_delete_violation("삭제 .env", workdir=default_codex_workdir())
        print(f"protected_delete_guard_ok={bool(violation)}")
        if not violation:
            rc = 1
    except Exception as exc:  # noqa: BLE001
        print(f"protected_delete_guard_ok=false reason={exc}", file=sys.stderr)
        rc = 1

    try:
        data = discord_api("GET")
        print(f"discord_api_ok=true bot_username={data.get('username', '<unknown>')}")
    except Exception as exc:  # noqa: BLE001
        print(f"discord_api_ok=false reason={exc}", file=sys.stderr)
        rc = 1
    return rc


def repair() -> int:
    print("repair_target=discord_bridge")
    print("codex_policy=separate_recovery_channel_not_repaired_here")
    rc = health()
    if rc == 0:
        print("repair_needed=false")
        return 0
    print("repair_needed=true")
    return restart()


def auth() -> int:
    result = run([python_executable(), "-m", "nyanya_agent.core", "--check"], check=False)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


def codex_status() -> int:
    app_exists = CODEX_APP_PATH.exists()
    cli = configured_codex_cli()
    app_processes = matching_processes(r"/Applications/Codex\.app/Contents/MacOS/Codex")
    app_server_processes = matching_processes(r"codex app-server")
    codex_launch_rc, codex_launch_lines = launch_status(CODEX_LABEL)

    print(f"codex_app_exists={app_exists}")
    print(f"codex_app_running={bool(app_processes)}")
    print(f"codex_app_process_count={len(app_processes)}")
    print(f"codex_app_server_running={bool(app_server_processes)}")
    print(f"codex_app_server_process_count={len(app_server_processes)}")
    print(f"codex_cli_available={bool(cli)}")
    if cli:
        print(f"codex_cli={cli}")
    print(f"codex_launchagent_loaded={codex_launch_rc == 0}")
    for line in codex_launch_lines:
        print(line)
    if not app_exists and not cli:
        return 1
    return 0


def codex_start() -> int:
    if not CODEX_APP_PATH.exists():
        print(f"codex_app_missing={CODEX_APP_PATH}", file=sys.stderr)
        return 1
    result = run(["/usr/bin/open", "-a", CODEX_APP_NAME], check=False)
    if result.returncode != 0:
        sys.stderr.write(result.stderr or result.stdout)
        return result.returncode
    print("codex_started=true")
    print("codex_policy=separate_recovery_channel")
    return 0


def codex_install() -> int:
    path = write_codex_plist()
    bootout(CODEX_LABEL)
    result = bootstrap(path)
    if result.returncode != 0:
        sys.stderr.write(result.stderr or result.stdout)
        return result.returncode
    kick = kickstart(CODEX_LABEL)
    if kick.returncode != 0:
        sys.stderr.write(kick.stderr or kick.stdout)
        return kick.returncode
    print(f"installed={CODEX_LABEL}")
    print(f"plist={path}")
    print("codex_policy=separate_recovery_channel")
    return 0


def codex_uninstall() -> int:
    bootout(CODEX_LABEL)
    plist_path(CODEX_LABEL).unlink(missing_ok=True)
    print(f"removed={CODEX_LABEL}")
    print("codex_policy=separate_recovery_channel")
    return 0


def dashboard_url() -> str:
    load_env()
    host = os.getenv("NYANYA_DASHBOARD_HOST", "127.0.0.1")
    port = int(os.getenv("NYANYA_DASHBOARD_PORT", "8765"))
    return f"http://{host}:{port}"


def dashboard_install() -> int:
    path = write_dashboard_plist()
    bootout(DASHBOARD_LABEL)
    result = bootstrap(path)
    if result.returncode != 0:
        sys.stderr.write(result.stderr or result.stdout)
        return result.returncode
    kick = kickstart(DASHBOARD_LABEL)
    if kick.returncode != 0:
        sys.stderr.write(kick.stderr or kick.stdout)
        return kick.returncode
    print(f"installed={DASHBOARD_LABEL}")
    print(f"plist={path}")
    print(f"url={dashboard_url()}")
    return 0


def dashboard_start() -> int:
    path = plist_path(DASHBOARD_LABEL)
    if not path.exists():
        write_dashboard_plist()
    result = bootstrap(path)
    if result.returncode not in (0, 5):
        sys.stderr.write(result.stderr or result.stdout)
        return result.returncode
    kick = kickstart(DASHBOARD_LABEL)
    if kick.returncode != 0:
        sys.stderr.write(kick.stderr or kick.stdout)
        return kick.returncode
    print(f"started={DASHBOARD_LABEL}")
    print(f"url={dashboard_url()}")
    return 0


def dashboard_stop() -> int:
    bootout(DASHBOARD_LABEL)
    print(f"stopped={DASHBOARD_LABEL}")
    return 0


def dashboard_restart() -> int:
    bootout(DASHBOARD_LABEL)
    return dashboard_install()


def dashboard_uninstall() -> int:
    bootout(DASHBOARD_LABEL)
    plist_path(DASHBOARD_LABEL).unlink(missing_ok=True)
    print(f"removed={DASHBOARD_LABEL}")
    return 0


def dashboard_status() -> int:
    rc, lines = launch_status(DASHBOARD_LABEL)
    for line in lines:
        print(line)
    print(f"url={dashboard_url()}")
    return 0 if rc == 0 else 1


def dashboard_health() -> int:
    url = f"{dashboard_url()}/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        print(f"dashboard_http_ok=true url={url} status={payload.get('status')}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"dashboard_http_ok=false url={url} reason={exc}", file=sys.stderr)
        return 1


def memory_worker_install() -> int:
    path = write_memory_worker_plist()
    bootout(MEMORY_WORKER_LABEL)
    result = bootstrap(path)
    if result.returncode != 0:
        sys.stderr.write(result.stderr or result.stdout)
        return result.returncode
    kick = kickstart(MEMORY_WORKER_LABEL)
    if kick.returncode != 0:
        sys.stderr.write(kick.stderr or kick.stdout)
        return kick.returncode
    print(f"installed={MEMORY_WORKER_LABEL}")
    print(f"plist={path}")
    return 0


def memory_worker_start() -> int:
    path = plist_path(MEMORY_WORKER_LABEL)
    if not path.exists():
        write_memory_worker_plist()
    result = bootstrap(path)
    if result.returncode not in (0, 5):
        sys.stderr.write(result.stderr or result.stdout)
        return result.returncode
    kick = kickstart(MEMORY_WORKER_LABEL)
    if kick.returncode != 0:
        sys.stderr.write(kick.stderr or kick.stdout)
        return kick.returncode
    print(f"started={MEMORY_WORKER_LABEL}")
    return 0


def memory_worker_stop() -> int:
    bootout(MEMORY_WORKER_LABEL)
    print(f"stopped={MEMORY_WORKER_LABEL}")
    return 0


def memory_worker_restart() -> int:
    bootout(MEMORY_WORKER_LABEL)
    return memory_worker_install()


def memory_worker_uninstall() -> int:
    bootout(MEMORY_WORKER_LABEL)
    plist_path(MEMORY_WORKER_LABEL).unlink(missing_ok=True)
    print(f"removed={MEMORY_WORKER_LABEL}")
    return 0


def memory_worker_status() -> int:
    rc, lines = launch_status(MEMORY_WORKER_LABEL)
    for line in lines:
        print(line)
    return 0 if rc == 0 else 1


def memory_worker_once() -> int:
    result = run([python_executable(), "-m", "nyanya_agent.memory_worker", "--once"], check=False)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


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
    for name in (
        "install",
        "start",
        "stop",
        "restart",
        "uninstall",
        "status",
        "check",
        "preflight",
        "auth",
        "start-all",
        "restart-all",
        "status-all",
        "health",
        "deep-health",
        "smoke",
        "repair",
        "dashboard-install",
        "dashboard-start",
        "dashboard-stop",
        "dashboard-restart",
        "dashboard-uninstall",
        "dashboard-status",
        "dashboard-health",
        "memory-worker-install",
        "memory-worker-start",
        "memory-worker-stop",
        "memory-worker-restart",
        "memory-worker-uninstall",
        "memory-worker-status",
        "memory-worker-once",
        "codex-status",
        "codex-start",
        "codex-install",
        "codex-uninstall",
    ):
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
    if args.command == "start-all":
        return start_all()
    if args.command == "stop":
        return stop()
    if args.command == "restart":
        return restart()
    if args.command == "restart-all":
        return restart_all()
    if args.command == "uninstall":
        return uninstall()
    if args.command == "status":
        return status()
    if args.command == "status-all":
        return status_all()
    if args.command == "check":
        return check_config()
    if args.command == "preflight":
        return check_config(include_backend=False)
    if args.command == "auth":
        return auth()
    if args.command == "health":
        return health()
    if args.command == "deep-health":
        return deep_health()
    if args.command == "smoke":
        return smoke()
    if args.command == "repair":
        return repair()
    if args.command == "dashboard-install":
        return dashboard_install()
    if args.command == "dashboard-start":
        return dashboard_start()
    if args.command == "dashboard-stop":
        return dashboard_stop()
    if args.command == "dashboard-restart":
        return dashboard_restart()
    if args.command == "dashboard-uninstall":
        return dashboard_uninstall()
    if args.command == "dashboard-status":
        return dashboard_status()
    if args.command == "dashboard-health":
        return dashboard_health()
    if args.command == "memory-worker-install":
        return memory_worker_install()
    if args.command == "memory-worker-start":
        return memory_worker_start()
    if args.command == "memory-worker-stop":
        return memory_worker_stop()
    if args.command == "memory-worker-restart":
        return memory_worker_restart()
    if args.command == "memory-worker-uninstall":
        return memory_worker_uninstall()
    if args.command == "memory-worker-status":
        return memory_worker_status()
    if args.command == "memory-worker-once":
        return memory_worker_once()
    if args.command == "codex-status":
        return codex_status()
    if args.command == "codex-start":
        return codex_start()
    if args.command == "codex-install":
        return codex_install()
    if args.command == "codex-uninstall":
        return codex_uninstall()
    if args.command == "bot-name":
        return bot_name(args.name)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
