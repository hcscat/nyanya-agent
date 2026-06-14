#!/usr/bin/env python3
"""SQLite-backed operational dashboard store for NyaNya Agent."""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import contextmanager
import datetime as dt
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

from nyanya_agent import core as nyanya


DEFAULT_DB_PATH = nyanya.PROJECT_ROOT / "data" / "nyanya_dashboard.db"
PHASE_ORDER = ("planning", "design", "implementation", "test")
PHASE_LABELS = {
    "planning": "기획",
    "design": "설계",
    "implementation": "구현",
    "test": "테스트",
}
TERMINAL_REQUEST_STATUSES = {"completed", "failed", "cancelled", "ignored"}


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def encode_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def decode_json(value: str | None, fallback: Any = None) -> Any:
    if value in (None, ""):
        return fallback
    return json.loads(value)


def resolve_db_path(db_path: str | Path | None = None) -> Path:
    raw = db_path or os.getenv("NYANYA_DASHBOARD_DB_PATH") or DEFAULT_DB_PATH
    return Path(raw).expanduser().resolve(strict=False)


@contextmanager
def connect(db_path: str | Path | None = None) -> Iterable[sqlite3.Connection]:
    path = resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agent_requests (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL DEFAULT 'discord',
  guild_id TEXT NOT NULL DEFAULT '',
  channel_id TEXT NOT NULL DEFAULT '',
  channel_name TEXT NOT NULL DEFAULT '',
  user_id TEXT NOT NULL DEFAULT '',
  trigger TEXT NOT NULL DEFAULT '',
  command TEXT NOT NULL DEFAULT '',
  mode TEXT NOT NULL DEFAULT 'auto',
  provider TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL DEFAULT '',
  prompt TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'received',
  result_summary TEXT NOT NULL DEFAULT '',
  error TEXT NOT NULL DEFAULT '',
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  total_tokens INTEGER,
  started_at TEXT,
  ended_at TEXT,
  duration_ms INTEGER,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_requests_created_at ON agent_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_agent_requests_status ON agent_requests(status);
CREATE INDEX IF NOT EXISTS idx_agent_requests_source_channel ON agent_requests(source, channel_id);

CREATE TABLE IF NOT EXISTS request_events (
  id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL REFERENCES agent_requests(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  message TEXT NOT NULL DEFAULT '',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_request_events_request_id ON request_events(request_id, created_at);

CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  goal TEXT NOT NULL DEFAULT '',
  owner TEXT NOT NULL DEFAULT 'operator',
  status TEXT NOT NULL DEFAULT 'active',
  health TEXT NOT NULL DEFAULT 'green',
  current_phase TEXT NOT NULL DEFAULT 'planning',
  next_action TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_phases (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  phase_key TEXT NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'waiting',
  summary TEXT NOT NULL DEFAULT '',
  next_action TEXT NOT NULL DEFAULT '',
  requires_confirmation INTEGER NOT NULL DEFAULT 0,
  last_checked_at TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(project_id, phase_key)
);

CREATE INDEX IF NOT EXISTS idx_project_phases_project ON project_phases(project_id, sort_order);

CREATE TABLE IF NOT EXISTS phase_checks (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  phase_key TEXT NOT NULL,
  status TEXT NOT NULL,
  finding TEXT NOT NULL DEFAULT '',
  recommended_next_action TEXT NOT NULL DEFAULT '',
  confirmation_required INTEGER NOT NULL DEFAULT 0,
  discord_message TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_phase_checks_project ON phase_checks(project_id, created_at);

CREATE TABLE IF NOT EXISTS audit_logs (
  id TEXT PRIMARY KEY,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  detail_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
"""


def init_db(db_path: str | Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return None if row is None else dict(row)


def rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def parse_json_fields(data: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    parsed = dict(data)
    for field in fields:
        public = field.removesuffix("_json")
        parsed[public] = decode_json(parsed.pop(field, None), {})
    return parsed


def log_audit(
    conn: sqlite3.Connection,
    *,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str,
    detail: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO audit_logs (id, actor, action, entity_type, entity_id, detail_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (new_id("audit"), actor, action, entity_type, entity_id, encode_json(detail or {}), now_iso()),
    )


def safe_summary(text: str, limit: int = 600) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 15].rstrip() + " ...[truncated]"


def iso_duration_ms(started_at: str | None, ended_at: str | None) -> int | None:
    if not started_at or not ended_at:
        return None
    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, int((end - start).total_seconds() * 1000))


def create_agent_request(
    *,
    source: str = "discord",
    guild_id: str = "",
    channel_id: str = "",
    channel_name: str = "",
    user_id: str = "",
    trigger: str = "",
    command: str = "",
    mode: str = "auto",
    provider: str = "",
    model: str = "",
    prompt: str = "",
    status: str = "received",
    metadata: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> str:
    init_db(db_path)
    request_id = new_id("req")
    timestamp = now_iso()
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO agent_requests
              (id, source, guild_id, channel_id, channel_name, user_id, trigger, command, mode,
               provider, model, prompt, status, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                source,
                guild_id,
                channel_id,
                channel_name,
                user_id,
                trigger,
                command,
                mode,
                provider,
                model,
                prompt,
                status,
                encode_json(metadata or {}),
                timestamp,
                timestamp,
            ),
        )
        append_request_event_conn(conn, request_id, "received", "Request received", metadata or {})
        log_audit(conn, actor=source, action="request.received", entity_type="agent_request", entity_id=request_id)
    return request_id


def append_request_event_conn(
    conn: sqlite3.Connection,
    request_id: str,
    event_type: str,
    message: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event_id = new_id("event")
    conn.execute(
        """
        INSERT INTO request_events (id, request_id, event_type, message, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (event_id, request_id, event_type, message, encode_json(metadata or {}), now_iso()),
    )
    return dict(conn.execute("SELECT * FROM request_events WHERE id = ?", (event_id,)).fetchone())


def append_request_event(
    request_id: str,
    event_type: str,
    message: str = "",
    metadata: dict[str, Any] | None = None,
    *,
    db_path: str | Path | None = None,
) -> None:
    init_db(db_path)
    with connect(db_path) as conn:
        append_request_event_conn(conn, request_id, event_type, message, metadata or {})


def mark_request_status(
    request_id: str | None,
    status: str,
    *,
    event_type: str | None = None,
    message: str = "",
    result_summary: str | None = None,
    error: str | None = None,
    mode: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    token_usage: dict[str, int | None] | None = None,
    metadata: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> None:
    if not request_id:
        return
    init_db(db_path)
    timestamp = now_iso()
    with connect(db_path) as conn:
        current = conn.execute("SELECT * FROM agent_requests WHERE id = ?", (request_id,)).fetchone()
        if current is None:
            return
        updates: dict[str, Any] = {"status": status, "updated_at": timestamp}
        if status == "running" and not current["started_at"]:
            updates["started_at"] = timestamp
        if status in TERMINAL_REQUEST_STATUSES:
            updates["ended_at"] = timestamp
            updates["duration_ms"] = iso_duration_ms(current["started_at"] or current["created_at"], timestamp)
        if result_summary is not None:
            updates["result_summary"] = safe_summary(result_summary)
        if error is not None:
            updates["error"] = safe_summary(error)
        if mode is not None:
            updates["mode"] = mode
        if provider is not None:
            updates["provider"] = provider
        if model is not None:
            updates["model"] = model
        if token_usage:
            for column in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if column in token_usage:
                    updates[column] = token_usage[column]
        if metadata:
            existing = decode_json(current["metadata_json"], {})
            if not isinstance(existing, dict):
                existing = {}
            existing.update(metadata)
            updates["metadata_json"] = encode_json(existing)
        assignments = ", ".join(f"{field} = ?" for field in updates)
        conn.execute(f"UPDATE agent_requests SET {assignments} WHERE id = ?", [*updates.values(), request_id])
        append_request_event_conn(conn, request_id, event_type or status, message or f"Request status changed to {status}", metadata or {})
        if status in TERMINAL_REQUEST_STATUSES:
            log_audit(
                conn,
                actor="nyanya-agent",
                action=f"request.{status}",
                entity_type="agent_request",
                entity_id=request_id,
                detail={"duration_ms": updates.get("duration_ms")},
            )


def list_requests(
    *,
    status: str | None = None,
    limit: int = 50,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        if status:
            data = rows(
                conn,
                "SELECT * FROM agent_requests WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            )
        else:
            data = rows(conn, "SELECT * FROM agent_requests ORDER BY created_at DESC LIMIT ?", (limit,))
    return [parse_json_fields(item, ("metadata_json",)) for item in data]


def get_request(request_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    init_db(db_path)
    with connect(db_path) as conn:
        request = row_to_dict(conn.execute("SELECT * FROM agent_requests WHERE id = ?", (request_id,)).fetchone())
        if request is None:
            return None
        request = parse_json_fields(request, ("metadata_json",))
        request["events"] = [
            parse_json_fields(item, ("metadata_json",))
            for item in rows(conn, "SELECT * FROM request_events WHERE request_id = ? ORDER BY created_at ASC", (request_id,))
        ]
        return request


def create_project(
    *,
    name: str,
    goal: str = "",
    owner: str = "operator",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_db(db_path)
    timestamp = now_iso()
    project_id = new_id("project")
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO projects (id, name, goal, owner, status, health, current_phase, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'active', 'green', 'planning', ?, ?)
            """,
            (project_id, name, goal, owner, timestamp, timestamp),
        )
        for index, phase_key in enumerate(PHASE_ORDER):
            status = "running" if index == 0 else "waiting"
            conn.execute(
                """
                INSERT INTO project_phases
                  (id, project_id, phase_key, title, status, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("phase"),
                    project_id,
                    phase_key,
                    PHASE_LABELS[phase_key],
                    status,
                    index,
                    timestamp,
                    timestamp,
                ),
            )
        log_audit(conn, actor=owner, action="project.created", entity_type="project", entity_id=project_id)
    project = get_project(project_id, db_path=db_path)
    if project is None:
        raise RuntimeError(f"Project was not created: {project_id}")
    return project


def list_projects(*, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        return rows(conn, "SELECT * FROM projects ORDER BY updated_at DESC")


def get_project(project_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    init_db(db_path)
    with connect(db_path) as conn:
        project = row_to_dict(conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone())
        if project is None:
            return None
        project["phases"] = rows(
            conn,
            "SELECT * FROM project_phases WHERE project_id = ? ORDER BY sort_order ASC",
            (project_id,),
        )
        project["checks"] = rows(
            conn,
            "SELECT * FROM phase_checks WHERE project_id = ? ORDER BY created_at DESC LIMIT 20",
            (project_id,),
        )
        return project


def update_phase(
    project_id: str,
    phase_key: str,
    *,
    status: str | None = None,
    summary: str | None = None,
    next_action: str | None = None,
    requires_confirmation: bool | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    init_db(db_path)
    updates: dict[str, Any] = {"updated_at": now_iso()}
    if status is not None:
        updates["status"] = status
    if summary is not None:
        updates["summary"] = summary
    if next_action is not None:
        updates["next_action"] = next_action
    if requires_confirmation is not None:
        updates["requires_confirmation"] = 1 if requires_confirmation else 0
    with connect(db_path) as conn:
        assignments = ", ".join(f"{field} = ?" for field in updates)
        conn.execute(
            f"UPDATE project_phases SET {assignments} WHERE project_id = ? AND phase_key = ?",
            [*updates.values(), project_id, phase_key],
        )
        if status == "running":
            conn.execute(
                "UPDATE projects SET current_phase = ?, updated_at = ? WHERE id = ?",
                (phase_key, now_iso(), project_id),
            )
        phase = row_to_dict(
            conn.execute("SELECT * FROM project_phases WHERE project_id = ? AND phase_key = ?", (project_id, phase_key)).fetchone()
        )
        log_audit(conn, actor="operator", action="phase.updated", entity_type="project_phase", entity_id=phase["id"] if phase else phase_key)
        return phase


def check_project_phase(
    project_id: str,
    *,
    phase_key: str | None = None,
    actor: str = "nyanya-agent",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    init_db(db_path)
    timestamp = now_iso()
    with connect(db_path) as conn:
        project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if project is None:
            raise KeyError(project_id)
        phase_key = phase_key or project["current_phase"]
        phase = conn.execute(
            "SELECT * FROM project_phases WHERE project_id = ? AND phase_key = ?",
            (project_id, phase_key),
        ).fetchone()
        if phase is None:
            raise KeyError(f"{project_id}:{phase_key}")

        next_action = phase["next_action"] or project["next_action"]
        confirmation_required = bool(next_action) and phase["status"] not in {"completed", "cancelled"}
        if confirmation_required:
            finding = f"{phase['title']} 단계에서 다음 작업 확인이 필요합니다."
            recommended = next_action
            status = "needs_confirmation"
            discord_message = (
                f"[NyaNya 단계 확인]\n프로젝트: {project['name']}\n"
                f"현재 단계: {phase['title']}\n다음 작업: {next_action}\n"
                "진행하려면 승인 또는 보류 의견을 남겨주세요."
            )
        else:
            finding = f"{phase['title']} 단계는 현재 추가 확인 항목이 없습니다."
            recommended = ""
            status = "ok"
            discord_message = ""

        check_id = new_id("check")
        conn.execute(
            """
            INSERT INTO phase_checks
              (id, project_id, phase_key, status, finding, recommended_next_action,
               confirmation_required, discord_message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                check_id,
                project_id,
                phase_key,
                status,
                finding,
                recommended,
                1 if confirmation_required else 0,
                discord_message,
                timestamp,
            ),
        )
        conn.execute(
            """
            UPDATE project_phases
            SET last_checked_at = ?, requires_confirmation = ?, updated_at = ?
            WHERE project_id = ? AND phase_key = ?
            """,
            (timestamp, 1 if confirmation_required else 0, timestamp, project_id, phase_key),
        )
        log_audit(conn, actor=actor, action="phase.checked", entity_type="phase_check", entity_id=check_id)
        return dict(conn.execute("SELECT * FROM phase_checks WHERE id = ?", (check_id,)).fetchone())


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def due_phase_checks(
    *,
    interval_seconds: int,
    limit: int = 5,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    init_db(db_path)
    cutoff = datetime.now(UTC) - dt.timedelta(seconds=max(60, interval_seconds))
    due: list[tuple[str, str]] = []
    with connect(db_path) as conn:
        candidates = rows(
            conn,
            """
            SELECT project_id, phase_key, last_checked_at
            FROM project_phases
            WHERE status NOT IN ('completed', 'cancelled')
              AND TRIM(next_action) != ''
            ORDER BY COALESCE(last_checked_at, '') ASC, updated_at ASC
            LIMIT ?
            """,
            (limit * 3,),
        )
    for candidate in candidates:
        checked_at = _parse_iso(candidate.get("last_checked_at"))
        if checked_at is None or checked_at <= cutoff:
            due.append((candidate["project_id"], candidate["phase_key"]))
        if len(due) >= limit:
            break

    checks: list[dict[str, Any]] = []
    for project_id, phase_key in due:
        checks.append(check_project_phase(project_id, phase_key=phase_key, actor="phase-checker", db_path=db_path))
    return checks


def usage_series(period: str = "daily", limit: int = 30, *, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    period_expr = {
        "daily": "substr(created_at, 1, 10)",
        "weekly": "strftime('%Y-W%W', created_at)",
        "monthly": "substr(created_at, 1, 7)",
    }.get(period)
    if period_expr is None:
        raise ValueError("period must be daily, weekly, or monthly")
    with connect(db_path) as conn:
        data = rows(
            conn,
            f"""
            SELECT {period_expr} AS bucket,
                   COUNT(*) AS requests,
                   SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
                   SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                   SUM(COALESCE(total_tokens, 0)) AS total_tokens,
                   AVG(duration_ms) AS avg_duration_ms
            FROM agent_requests
            GROUP BY bucket
            ORDER BY bucket DESC
            LIMIT ?
            """,
            (limit,),
        )
    return list(reversed(data))


def dashboard_summary(*, db_path: str | Path | None = None) -> dict[str, Any]:
    init_db(db_path)
    with connect(db_path) as conn:
        status_counts = {
            row["status"]: row["count"]
            for row in conn.execute("SELECT status, COUNT(*) AS count FROM agent_requests GROUP BY status").fetchall()
        }
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        today_count = conn.execute(
            "SELECT COUNT(*) AS count FROM agent_requests WHERE substr(created_at, 1, 10) = ?",
            (today,),
        ).fetchone()["count"]
        running = rows(
            conn,
            """
            SELECT * FROM agent_requests
            WHERE status IN ('queued', 'running', 'received')
            ORDER BY created_at DESC
            LIMIT 8
            """,
        )
        recent_failures = rows(
            conn,
            """
            SELECT * FROM agent_requests
            WHERE status = 'failed'
            ORDER BY created_at DESC
            LIMIT 8
            """,
        )
        projects = conn.execute("SELECT COUNT(*) AS count FROM projects WHERE status != 'archived'").fetchone()["count"]
        confirmations = conn.execute(
            "SELECT COUNT(*) AS count FROM project_phases WHERE requires_confirmation = 1"
        ).fetchone()["count"]
        return {
            "requests": sum(status_counts.values()),
            "today_requests": today_count,
            "status_counts": status_counts,
            "running": [parse_json_fields(item, ("metadata_json",)) for item in running],
            "recent_failures": [parse_json_fields(item, ("metadata_json",)) for item in recent_failures],
            "projects": projects,
            "phase_confirmations": confirmations,
        }


def audit_log(limit: int = 50, *, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    with connect(db_path) as conn:
        data = rows(conn, "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?", (limit,))
    return [parse_json_fields(item, ("detail_json",)) for item in data]
