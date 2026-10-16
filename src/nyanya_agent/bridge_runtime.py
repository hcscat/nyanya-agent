#!/usr/bin/env python3
"""Runtime helpers for NyaNya messenger bridges."""

from __future__ import annotations

import os
import pathlib
import subprocess
from typing import Any

from nyanya_agent import core as nyanya

def load_runtime_config(config_path: str | None = None) -> dict[str, Any]:
    nyanya.load_env(nyanya.DEFAULT_ENV)
    path = pathlib.Path(config_path) if config_path else nyanya.DEFAULT_CONFIG
    return nyanya.load_config(path)


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_id_set(value: str | None) -> set[str]:
    if not value:
        return set()
    return {item.strip() for item in value.split(",") if item.strip()}


def env_first(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return ""


def visible_config(config: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if "key" not in key.lower()}


def system_resource_report(limit: int = 10) -> str:
    proc = subprocess.run(
        ["ps", "-axo", "pid,ppid,pcpu,pmem,rss,comm"],
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        return f"시스템 리소스 조회 실패: {detail or f'exit code {proc.returncode}'}"

    rows: list[dict[str, str | float | int]] = []
    for line in proc.stdout.splitlines()[1:]:
        parts = line.split(None, 5)
        if len(parts) < 6:
            continue
        try:
            rows.append(
                {
                    "pid": int(parts[0]),
                    "ppid": int(parts[1]),
                    "cpu": float(parts[2]),
                    "mem": float(parts[3]),
                    "rss_mb": int(parts[4]) / 1024,
                    "comm": parts[5],
                }
            )
        except ValueError:
            continue

    rows.sort(key=lambda item: (float(item["cpu"]), float(item["mem"]), float(item["rss_mb"])), reverse=True)
    selected = rows[:limit]
    lines = [
        f"시스템 리소스 상위 {len(selected)}개 프로세스",
        "",
        "| # | PID | PPID | CPU% | MEM% | RSS MB | COMMAND |",
        "|---:|---:|---:|---:|---:|---:|---|",
    ]
    for index, row in enumerate(selected, 1):
        command = str(row["comm"])
        if len(command) > 90:
            command = command[:87] + "..."
        lines.append(
            f"| {index} | {row['pid']} | {row['ppid']} | {float(row['cpu']):.1f} | "
            f"{float(row['mem']):.1f} | {float(row['rss_mb']):.1f} | `{command}` |"
        )
    return "\n".join(lines)
