#!/usr/bin/env python3
"""Run one adapter command and persist an atomic completion marker."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import sys
import time


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def write_marker(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a command and write a completion marker")
    parser.add_argument("--status-file", required=True)
    parser.add_argument("--started-at", default="")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        raise SystemExit("No command supplied")

    started_at = args.started_at or now_iso()
    started_monotonic = time.monotonic()
    try:
        completed = subprocess.run(command, check=False)
        returncode = completed.returncode
        error = ""
    except Exception as exc:
        returncode = 127
        error = f"{type(exc).__name__}: {exc}"
    write_marker(
        Path(args.status_file),
        {
            "command": command,
            "started_at": started_at,
            "ended_at": now_iso(),
            "duration_ms": int((time.monotonic() - started_monotonic) * 1000),
            "returncode": returncode,
            "error": error,
        },
    )
    return returncode


if __name__ == "__main__":
    sys.exit(main())
