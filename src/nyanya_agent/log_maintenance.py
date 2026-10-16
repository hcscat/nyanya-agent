"""Local gzip maintenance entry point; importing this module never opens state."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import shlex
import sys
from typing import Any


class DatabaseOutsideStateRoot(ValueError):
    """Choose a matching state root; an inherited DB override cannot cross it."""


def configured_paths(state_root: str | Path | None = None, db_path: str | Path | None = None) -> tuple[Path, Path]:
    from nyanya_agent.runtime_paths import ENV_FILE, resolve_state_root

    root = Path(os.path.abspath(Path(state_root).expanduser())) if state_root else resolve_state_root()
    configured = db_path or os.getenv("NYANYA_DASHBOARD_DB_PATH")
    if not configured:
        env_file = Path(os.getenv("NYANYA_ENV_FILE", str(root / ".env"))) if state_root else ENV_FILE
        if env_file.exists():
            if env_file.stat().st_size > 1024 * 1024:
                raise ValueError("Environment file exceeds the configuration limit")
            # Read only the database setting; never load credentials into the job.
            for line in env_file.read_text(encoding="utf-8").splitlines():
                key, separator, value = line.removeprefix("export ").partition("=")
                if separator and key.strip() == "NYANYA_DASHBOARD_DB_PATH":
                    values = shlex.split(value, comments=True)
                    if len(values) > 1:
                        raise ValueError("Quote a database path containing spaces")
                    configured = values[0] if values else None
    candidate = Path(configured or "data/nyanya_dashboard.db").expanduser()
    database = candidate if candidate.is_absolute() else root / candidate
    return root, Path(os.path.abspath(database))


def run_maintenance(*, state_root: Path, db_path: Path, apply: bool = False,
                    now: datetime | None = None) -> dict[str, Any]:
    if not db_path.resolve(strict=False).is_relative_to(state_root.resolve(strict=False)):
        raise DatabaseOutsideStateRoot("Database must be inside the selected state root")
    from nyanya_agent.log_archive import run_archive
    from nyanya_agent.service_logs import maintain_service_logs

    result: dict[str, Any] = {"mode": "apply" if apply else "dry-run", "status": "ok"}
    jobs = {
        "audit": lambda: run_archive(db_path=db_path, archive_dir=state_root / "logs/archive/audit",
                                     apply=apply, now=now),
        "service": lambda: maintain_service_logs(state_root / "logs", state_root / "logs/archive/service",
                                                  apply=apply, now=now),
    }
    for name, job in jobs.items():
        if name == "audit" and not os.path.lexists(db_path):
            result[name] = {"status": "absent"}
            continue
        try:
            report = job()
            result[name] = report
            if report.get("status") not in {"ok", "absent"} or report.get("errors"):
                result["status"] = "blocked"
        except Exception as exc:
            # Paths, SQL and record contents do not belong in service diagnostics.
            result[name] = {"status": "blocked", "error_type": type(exc).__name__}
            result["status"] = "blocked"
    return result


_PUBLIC_KEYS = frozenset({
    "status", "mode", "month", "count", "prunable", "pinned", "deleted", "expired",
    "archived_rows", "deleted_rows", "expired_archives", "pinned_rows", "remaining_prunable",
    "archived_files", "deleted_files", "raw_files", "raw_bytes", "error_type", "retention",
})


def report_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Keep CLI/background output bounded and free of captured log content."""
    summary = {key: value for key, value in report.items()
               if key in _PUBLIC_KEYS and isinstance(value, (str, int, bool, type(None)))}
    for name in ("audit", "service"):
        if isinstance(report.get(name), dict):
            summary[name] = report_summary(report[name])
    months = report.get("months")
    if isinstance(months, list):
        summary["month_count"] = len(months)
        summary["months"] = [report_summary(item) for item in months[:24] if isinstance(item, dict)]
    errors = report.get("errors")
    if isinstance(errors, list):
        summary["error_count"] = len(errors)
    if "error" in report:
        message = str(report["error"]).lower()
        summary["reason"] = next((code for text, code in (
            ("conflict", "archive-conflict"), ("verification", "archive-invalid"),
            ("bound", "resource-limit"), ("limit", "resource-limit"),
            ("0600", "private-permissions-required"), ("0700", "private-permissions-required"),
            ("lock", "maintenance-busy"), ("changed", "preimage-changed"),
        ) if text in message), "inspect-local-archive")
    return summary


async def scheduled_run(state_root: Path, db_path: Path) -> dict[str, Any]:
    """Run maintenance outside the HTTP process, with bounded time and no credentials."""
    environment = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "LANG", "LC_ALL", "TMPDIR")
                   if key in os.environ}
    environment.update({"PYTHONPATH": str(Path(__file__).resolve().parents[1]), "PYTHONNOUSERSITE": "1",
                        "NYANYA_HOME": str(state_root), "NYANYA_PROJECT_ROOT": str(Path(__file__).resolve().parents[2]),
                        "NYANYA_ENV_FILE": str(state_root / ".maintenance-unused.env"),
                        "NYANYA_DASHBOARD_DB_PATH": str(db_path)})
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "nyanya_agent.log_maintenance", "maintain", "--apply",
        "--state-root", str(state_root), "--db-path", str(db_path),
        cwd=state_root, env=environment, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=300)
        if len(output) > 64 * 1024:
            return {"status": "blocked", "error_type": "OutputLimit"}
        report = json.loads(output)
        if not isinstance(report, dict):
            raise ValueError("Invalid maintenance result")
        if process.returncode and report.get("status") == "ok":
            report = {"status": "blocked", "error_type": "MaintenanceExit"}
        return report_summary(report)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return {"status": "blocked", "error_type": type(exc).__name__}
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()


async def maintenance_loop(state_root: Path, db_path: Path, *, publish=None) -> None:
    # Hourly catch-up also handles a sleeping machine and bounded pruning batches.
    while True:
        try:
            report = await scheduled_run(state_root, db_path)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            report = {"status": "blocked", "error_type": type(exc).__name__}
        if publish is not None:
            publish(report)
        if report.get("status") == "blocked":
            print("log_maintenance_blocked: inspect nyanya logs status", file=sys.stderr, flush=True)
        await asyncio.sleep(3600)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect or apply local gzip log retention; no encryption.")
    parser.add_argument("command", nargs="?", choices=("status", "maintain"), default="status")
    parser.add_argument("--apply", action="store_true", help="Archive and prune only verified eligible records")
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--db-path", type=Path)
    args = parser.parse_args(argv)
    if args.apply and args.command != "maintain":
        parser.error("--apply requires maintain")
    try:
        root, database = configured_paths(args.state_root, args.db_path)
        result = report_summary(run_maintenance(state_root=root, db_path=database, apply=args.apply))
    except Exception as exc:
        result = {"status": "blocked", "error_type": type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 1 if result.get("status") == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
