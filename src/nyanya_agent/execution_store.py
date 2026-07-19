#!/usr/bin/env python3
"""Versioned execution ledger for local and remote NyaNya workers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any
from uuid import uuid4

from nyanya_agent import dashboard_store as legacy


TASK_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
EXECUTION_TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "timed_out", "lost"}
TASK_TRANSITIONS = {
    "queued": {"running", "awaiting_approval", "blocked", "completed", "failed", "cancelled"},
    "running": {"awaiting_approval", "blocked", "completed", "failed", "cancelled"},
    "awaiting_approval": {"queued", "running", "blocked", "failed", "cancelled"},
    "blocked": {"queued", "running", "failed", "cancelled"},
    "completed": set(),
    "failed": {"queued"},
    "cancelled": {"queued"},
}
EXECUTION_TRANSITIONS = {
    "pending": {"starting", "running", "awaiting_approval", "cancelled", "failed"},
    "starting": {"running", "awaiting_approval", "cancelling", "failed", "cancelled", "timed_out"},
    "running": {"awaiting_approval", "cancelling", "succeeded", "failed", "cancelled", "timed_out", "stale"},
    "awaiting_approval": {"running", "cancelling", "failed", "cancelled", "timed_out"},
    "cancelling": {"cancelled", "failed", "timed_out", "lost"},
    "stale": {"running", "cancelling", "failed", "cancelled", "lost"},
    "succeeded": set(),
    "failed": set(),
    "cancelled": set(),
    "timed_out": set(),
    "lost": set(),
}

SECRET_KEY_RE = re.compile(r"(?i)(token|secret|password|passwd|authorization|api[_-]?key|private[_-]?key)")
NON_SECRET_TOKEN_KEYS = {"fence_token", "prompt_tokens", "completion_tokens", "total_tokens"}
SECRET_TEXT_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|password|passwd|secret|authorization|bearer)\b\s*[:= ]\s*['\"]?[^'\"\s,}]+"
)


MIGRATION_1 = r"""
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  checksum TEXT NOT NULL,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hosts (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  role TEXT NOT NULL DEFAULT 'worker',
  platform TEXT NOT NULL DEFAULT '',
  architecture TEXT NOT NULL DEFAULT '',
  tailscale_name TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'unknown',
  capabilities_json TEXT NOT NULL DEFAULT '{}',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  last_heartbeat_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_profiles (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  adapter_type TEXT NOT NULL,
  model TEXT NOT NULL DEFAULT '',
  workspace_root TEXT NOT NULL DEFAULT '',
  enabled INTEGER NOT NULL DEFAULT 1,
  capabilities_json TEXT NOT NULL DEFAULT '{}',
  policy_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_tasks (
  id TEXT PRIMARY KEY,
  source_request_id TEXT REFERENCES agent_requests(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  prompt TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'queued',
  priority INTEGER NOT NULL DEFAULT 100,
  requested_by TEXT NOT NULL DEFAULT 'operator',
  assigned_agent_id TEXT REFERENCES agent_profiles(id) ON DELETE SET NULL,
  current_execution_id TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_tasks_source_request
  ON agent_tasks(source_request_id) WHERE source_request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agent_tasks_status_priority
  ON agent_tasks(status, priority, created_at);

CREATE TABLE IF NOT EXISTS executions (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL REFERENCES agent_tasks(id) ON DELETE RESTRICT,
  host_id TEXT REFERENCES hosts(id) ON DELETE SET NULL,
  agent_profile_id TEXT REFERENCES agent_profiles(id) ON DELETE SET NULL,
  adapter_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  status_confidence REAL NOT NULL DEFAULT 1.0,
  command_summary TEXT NOT NULL DEFAULT '',
  workdir TEXT NOT NULL DEFAULT '',
  exit_code INTEGER,
  error TEXT NOT NULL DEFAULT '',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  started_at TEXT,
  ended_at TEXT,
  last_heartbeat_at TEXT,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_executions_task_created ON executions(task_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_executions_status_updated ON executions(status, updated_at DESC);

CREATE TABLE IF NOT EXISTS runtime_sessions (
  id TEXT PRIMARY KEY,
  execution_id TEXT REFERENCES executions(id) ON DELETE SET NULL,
  host_id TEXT REFERENCES hosts(id) ON DELETE SET NULL,
  adapter_type TEXT NOT NULL,
  external_id TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'starting',
  pid INTEGER,
  tmux_session TEXT NOT NULL DEFAULT '',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  started_at TEXT NOT NULL,
  last_heartbeat_at TEXT NOT NULL,
  ended_at TEXT,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runtime_sessions_execution ON runtime_sessions(execution_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_runtime_sessions_heartbeat ON runtime_sessions(status, last_heartbeat_at);

CREATE TABLE IF NOT EXISTS execution_events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  id TEXT NOT NULL UNIQUE,
  task_id TEXT REFERENCES agent_tasks(id) ON DELETE RESTRICT,
  execution_id TEXT REFERENCES executions(id) ON DELETE RESTRICT,
  event_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT '',
  message TEXT NOT NULL DEFAULT '',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  CHECK (task_id IS NOT NULL OR execution_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_execution_events_task_seq ON execution_events(task_id, seq);
CREATE INDEX IF NOT EXISTS idx_execution_events_execution_seq ON execution_events(execution_id, seq);

CREATE TRIGGER IF NOT EXISTS execution_events_no_update
BEFORE UPDATE ON execution_events BEGIN
  SELECT RAISE(ABORT, 'execution_events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS execution_events_no_delete
BEFORE DELETE ON execution_events BEGIN
  SELECT RAISE(ABORT, 'execution_events are append-only');
END;

CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY,
  task_id TEXT REFERENCES agent_tasks(id) ON DELETE RESTRICT,
  execution_id TEXT REFERENCES executions(id) ON DELETE RESTRICT,
  action TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  requested_by TEXT NOT NULL,
  decided_by TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT '',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  requested_at TEXT NOT NULL,
  decided_at TEXT,
  expires_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_approvals_status_requested ON approvals(status, requested_at DESC);

CREATE TABLE IF NOT EXISTS artifacts (
  id TEXT PRIMARY KEY,
  task_id TEXT REFERENCES agent_tasks(id) ON DELETE RESTRICT,
  execution_id TEXT REFERENCES executions(id) ON DELETE RESTRICT,
  kind TEXT NOT NULL DEFAULT 'file',
  path TEXT NOT NULL,
  sha256 TEXT NOT NULL DEFAULT '',
  size_bytes INTEGER,
  mime_type TEXT NOT NULL DEFAULT '',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_artifacts_task_created ON artifacts(task_id, created_at DESC);

CREATE TABLE IF NOT EXISTS writer_leases (
  resource_key TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  fence_token INTEGER NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  acquired_at TEXT NOT NULL,
  heartbeat_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
"""

MIGRATIONS = ((1, "execution-ledger", MIGRATION_1),)


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


def redact(value: Any, key: str = "") -> Any:
    if key.lower() not in NON_SECRET_TOKEN_KEYS and SECRET_KEY_RE.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return SECRET_TEXT_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
    return value


def _migration_checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def apply_migrations(db_path: str | Path | None = None) -> int:
    legacy.init_db(db_path)
    with legacy.connect(db_path) as conn:
        for version, name, sql in MIGRATIONS:
            table_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
            ).fetchone()
            applied = None
            if table_exists:
                applied = conn.execute(
                    "SELECT checksum FROM schema_migrations WHERE version = ?", (version,)
                ).fetchone()
            checksum = _migration_checksum(sql)
            if applied is not None:
                if applied["checksum"] != checksum:
                    raise RuntimeError(f"Migration checksum mismatch at version {version}")
                continue
            script = (
                "BEGIN IMMEDIATE;\n"
                + sql
                + "\nINSERT INTO schema_migrations(version, name, checksum, applied_at) VALUES ("
                + f"{version}, {_sql_literal(name)}, {_sql_literal(checksum)}, {_sql_literal(now_iso())});\n"
                + f"PRAGMA user_version = {version};\nCOMMIT;"
            )
            conn.executescript(script)
        row = conn.execute("PRAGMA user_version").fetchone()
        return int(row[0])


def schema_state(db_path: str | Path | None = None) -> dict[str, Any]:
    version = apply_migrations(db_path)
    with legacy.connect(db_path) as conn:
        migrations = [dict(row) for row in conn.execute("SELECT * FROM schema_migrations ORDER BY version")]
    return {"version": version, "latest": MIGRATIONS[-1][0], "migrations": migrations}


def _rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _parse_record(item: dict[str, Any], fields: tuple[str, ...] = ("metadata_json",)) -> dict[str, Any]:
    parsed = dict(item)
    for field in fields:
        public = field.removesuffix("_json")
        parsed[public] = decode_json(parsed.pop(field, None), {})
    return parsed


def append_event_conn(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    task_id: str | None = None,
    execution_id: str | None = None,
    status: str = "",
    message: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event_id = new_id("evt")
    safe_message = str(redact(message))
    safe_metadata = redact(metadata or {})
    conn.execute(
        """
        INSERT INTO execution_events
          (id, task_id, execution_id, event_type, status, message, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (event_id, task_id, execution_id, event_type, status, safe_message, encode_json(safe_metadata), now_iso()),
    )
    return dict(conn.execute("SELECT * FROM execution_events WHERE id = ?", (event_id,)).fetchone())


def append_event(**kwargs: Any) -> dict[str, Any]:
    db_path = kwargs.pop("db_path", None)
    apply_migrations(db_path)
    with legacy.connect(db_path) as conn:
        return _parse_record(append_event_conn(conn, **kwargs))


def register_host(
    *,
    name: str,
    role: str = "worker",
    platform: str = "",
    architecture: str = "",
    tailscale_name: str = "",
    status: str = "online",
    capabilities: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    host_id: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    apply_migrations(db_path)
    timestamp = now_iso()
    host_id = host_id or new_id("host")
    with legacy.connect(db_path) as conn:
        existing = conn.execute("SELECT id FROM hosts WHERE name = ?", (name,)).fetchone()
        if existing:
            host_id = existing["id"]
            conn.execute(
                """
                UPDATE hosts SET role = ?, platform = ?, architecture = ?, tailscale_name = ?, status = ?,
                  capabilities_json = ?, metadata_json = ?, last_heartbeat_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    role,
                    platform,
                    architecture,
                    tailscale_name,
                    status,
                    encode_json(capabilities or {}),
                    encode_json(redact(metadata or {})),
                    timestamp,
                    timestamp,
                    host_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO hosts
                  (id, name, role, platform, architecture, tailscale_name, status, capabilities_json,
                   metadata_json, last_heartbeat_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    host_id,
                    name,
                    role,
                    platform,
                    architecture,
                    tailscale_name,
                    status,
                    encode_json(capabilities or {}),
                    encode_json(redact(metadata or {})),
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
        legacy.log_audit(
            conn,
            actor="nyanya-agent",
            action="host.registered",
            entity_type="host",
            entity_id=host_id,
            detail=redact({"name": name, "role": role}),
        )
        row = dict(conn.execute("SELECT * FROM hosts WHERE id = ?", (host_id,)).fetchone())
    return _parse_record(row, ("capabilities_json", "metadata_json"))


def list_hosts(
    *,
    stale_after_seconds: int = 90,
    offline_after_seconds: int = 300,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    apply_migrations(db_path)
    now = datetime.now(UTC)
    with legacy.connect(db_path) as conn:
        data = _rows(conn, "SELECT * FROM hosts ORDER BY name")
    result = []
    for item in data:
        heartbeat = _parse_iso(item.get("last_heartbeat_at"))
        observed_status = item["status"]
        if heartbeat:
            age = max(0, int((now - heartbeat).total_seconds()))
            if age >= offline_after_seconds:
                observed_status = "offline"
            elif age >= stale_after_seconds:
                observed_status = "stale"
            item["heartbeat_age_seconds"] = age
        item["observed_status"] = observed_status
        result.append(_parse_record(item, ("capabilities_json", "metadata_json")))
    return result


def upsert_agent_profile(
    *,
    name: str,
    adapter_type: str,
    model: str = "",
    workspace_root: str = "",
    enabled: bool = True,
    capabilities: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    profile_id: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    apply_migrations(db_path)
    timestamp = now_iso()
    profile_id = profile_id or new_id("agent")
    with legacy.connect(db_path) as conn:
        existing = conn.execute("SELECT id FROM agent_profiles WHERE name = ?", (name,)).fetchone()
        if existing:
            profile_id = existing["id"]
            conn.execute(
                """
                UPDATE agent_profiles SET adapter_type = ?, model = ?, workspace_root = ?, enabled = ?,
                  capabilities_json = ?, policy_json = ?, updated_at = ? WHERE id = ?
                """,
                (
                    adapter_type,
                    model,
                    workspace_root,
                    1 if enabled else 0,
                    encode_json(capabilities or {}),
                    encode_json(redact(policy or {})),
                    timestamp,
                    profile_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO agent_profiles
                  (id, name, adapter_type, model, workspace_root, enabled, capabilities_json,
                   policy_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_id,
                    name,
                    adapter_type,
                    model,
                    workspace_root,
                    1 if enabled else 0,
                    encode_json(capabilities or {}),
                    encode_json(redact(policy or {})),
                    timestamp,
                    timestamp,
                ),
            )
        row = dict(conn.execute("SELECT * FROM agent_profiles WHERE id = ?", (profile_id,)).fetchone())
    return _parse_record(row, ("capabilities_json", "policy_json"))


def list_agent_profiles(*, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    apply_migrations(db_path)
    with legacy.connect(db_path) as conn:
        data = _rows(conn, "SELECT * FROM agent_profiles ORDER BY name")
    return [_parse_record(item, ("capabilities_json", "policy_json")) for item in data]


def create_task(
    *,
    title: str,
    prompt: str = "",
    status: str = "queued",
    priority: int = 100,
    requested_by: str = "operator",
    assigned_agent_id: str | None = None,
    source_request_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    task_id: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    if status not in TASK_TRANSITIONS:
        raise ValueError(f"Unknown task status: {status}")
    apply_migrations(db_path)
    timestamp = now_iso()
    task_id = task_id or new_id("task")
    completed_at = timestamp if status in TASK_TERMINAL_STATUSES else None
    with legacy.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO agent_tasks
              (id, source_request_id, title, prompt, status, priority, requested_by, assigned_agent_id,
               metadata_json, created_at, updated_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                source_request_id,
                title,
                prompt,
                status,
                priority,
                requested_by,
                assigned_agent_id,
                encode_json(redact(metadata or {})),
                timestamp,
                timestamp,
                completed_at,
            ),
        )
        append_event_conn(
            conn,
            task_id=task_id,
            event_type="task.created",
            status=status,
            message="Task created",
            metadata={"requested_by": requested_by, "priority": priority},
        )
        legacy.log_audit(
            conn,
            actor=requested_by,
            action="task.created",
            entity_type="agent_task",
            entity_id=task_id,
            detail=redact({"status": status, "source_request_id": source_request_id}),
        )
    task = get_task(task_id, db_path=db_path)
    if task is None:
        raise RuntimeError(f"Task was not created: {task_id}")
    return task


def transition_task(
    task_id: str,
    status: str,
    *,
    actor: str = "nyanya-agent",
    message: str = "",
    metadata: dict[str, Any] | None = None,
    force: bool = False,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    apply_migrations(db_path)
    with legacy.connect(db_path) as conn:
        current = conn.execute("SELECT * FROM agent_tasks WHERE id = ?", (task_id,)).fetchone()
        if current is None:
            raise KeyError(task_id)
        current_status = current["status"]
        if status != current_status and not force and status not in TASK_TRANSITIONS.get(current_status, set()):
            raise ValueError(f"Invalid task transition: {current_status} -> {status}")
        timestamp = now_iso()
        completed_at = timestamp if status in TASK_TERMINAL_STATUSES else None
        conn.execute(
            "UPDATE agent_tasks SET status = ?, updated_at = ?, completed_at = ? WHERE id = ?",
            (status, timestamp, completed_at, task_id),
        )
        if status != current_status:
            append_event_conn(
                conn,
                task_id=task_id,
                event_type="task.status",
                status=status,
                message=message or f"Task status changed from {current_status} to {status}",
                metadata=metadata,
            )
            legacy.log_audit(
                conn,
                actor=actor,
                action="task.status_changed",
                entity_type="agent_task",
                entity_id=task_id,
                detail=redact({"from": current_status, "to": status, **(metadata or {})}),
            )
        row = dict(conn.execute("SELECT * FROM agent_tasks WHERE id = ?", (task_id,)).fetchone())
    return _parse_record(row)


def list_tasks(
    *,
    status: str | None = None,
    limit: int = 100,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    apply_migrations(db_path)
    with legacy.connect(db_path) as conn:
        if status:
            data = _rows(
                conn,
                "SELECT * FROM agent_tasks WHERE status = ? ORDER BY priority, created_at DESC LIMIT ?",
                (status, limit),
            )
        else:
            data = _rows(conn, "SELECT * FROM agent_tasks ORDER BY created_at DESC LIMIT ?", (limit,))
    return [_parse_record(item) for item in data]


def get_task(task_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    apply_migrations(db_path)
    with legacy.connect(db_path) as conn:
        row = conn.execute("SELECT * FROM agent_tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        task = _parse_record(dict(row))
        task["executions"] = [
            _parse_record(item)
            for item in _rows(conn, "SELECT * FROM executions WHERE task_id = ? ORDER BY created_at DESC", (task_id,))
        ]
        task["approvals"] = [
            _parse_record(item)
            for item in _rows(conn, "SELECT * FROM approvals WHERE task_id = ? ORDER BY requested_at DESC", (task_id,))
        ]
        task["artifacts"] = [
            _parse_record(item)
            for item in _rows(conn, "SELECT * FROM artifacts WHERE task_id = ? ORDER BY created_at DESC", (task_id,))
        ]
        return task


def create_execution(
    *,
    task_id: str,
    adapter_type: str,
    host_id: str | None = None,
    agent_profile_id: str | None = None,
    status: str = "pending",
    command_summary: str = "",
    workdir: str = "",
    metadata: dict[str, Any] | None = None,
    execution_id: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    if status not in EXECUTION_TRANSITIONS:
        raise ValueError(f"Unknown execution status: {status}")
    apply_migrations(db_path)
    timestamp = now_iso()
    execution_id = execution_id or new_id("exec")
    started_at = timestamp if status in {"starting", "running"} else None
    ended_at = timestamp if status in EXECUTION_TERMINAL_STATUSES else None
    with legacy.connect(db_path) as conn:
        if conn.execute("SELECT 1 FROM agent_tasks WHERE id = ?", (task_id,)).fetchone() is None:
            raise KeyError(task_id)
        conn.execute(
            """
            INSERT INTO executions
              (id, task_id, host_id, agent_profile_id, adapter_type, status, command_summary, workdir,
               metadata_json, created_at, started_at, ended_at, last_heartbeat_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution_id,
                task_id,
                host_id,
                agent_profile_id,
                adapter_type,
                status,
                command_summary,
                workdir,
                encode_json(redact(metadata or {})),
                timestamp,
                started_at,
                ended_at,
                started_at,
                timestamp,
            ),
        )
        conn.execute(
            "UPDATE agent_tasks SET current_execution_id = ?, updated_at = ? WHERE id = ?",
            (execution_id, timestamp, task_id),
        )
        append_event_conn(
            conn,
            task_id=task_id,
            execution_id=execution_id,
            event_type="execution.created",
            status=status,
            message="Execution created",
            metadata={"adapter_type": adapter_type, "host_id": host_id},
        )
    execution = get_execution(execution_id, db_path=db_path)
    if execution is None:
        raise RuntimeError(f"Execution was not created: {execution_id}")
    return execution


def transition_execution(
    execution_id: str,
    status: str,
    *,
    actor: str = "nyanya-agent",
    message: str = "",
    exit_code: int | None = None,
    error: str | None = None,
    status_confidence: float | None = None,
    metadata: dict[str, Any] | None = None,
    force: bool = False,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    apply_migrations(db_path)
    with legacy.connect(db_path) as conn:
        current = conn.execute("SELECT * FROM executions WHERE id = ?", (execution_id,)).fetchone()
        if current is None:
            raise KeyError(execution_id)
        current_status = current["status"]
        if status != current_status and not force and status not in EXECUTION_TRANSITIONS.get(current_status, set()):
            raise ValueError(f"Invalid execution transition: {current_status} -> {status}")
        timestamp = now_iso()
        updates: dict[str, Any] = {"status": status, "updated_at": timestamp}
        if status in {"starting", "running"} and not current["started_at"]:
            updates["started_at"] = timestamp
        if status == "running":
            updates["last_heartbeat_at"] = timestamp
        if status in EXECUTION_TERMINAL_STATUSES:
            updates["ended_at"] = timestamp
        if exit_code is not None:
            updates["exit_code"] = exit_code
        if error is not None:
            updates["error"] = str(redact(error))[:1200]
        if status_confidence is not None:
            updates["status_confidence"] = max(0.0, min(1.0, status_confidence))
        if metadata:
            existing = decode_json(current["metadata_json"], {})
            existing.update(redact(metadata))
            updates["metadata_json"] = encode_json(existing)
        assignments = ", ".join(f"{field} = ?" for field in updates)
        conn.execute(f"UPDATE executions SET {assignments} WHERE id = ?", [*updates.values(), execution_id])
        if status != current_status:
            append_event_conn(
                conn,
                task_id=current["task_id"],
                execution_id=execution_id,
                event_type="execution.status",
                status=status,
                message=message or f"Execution status changed from {current_status} to {status}",
                metadata=metadata,
            )
        task_status = {
            "starting": "running",
            "running": "running",
            "awaiting_approval": "awaiting_approval",
            "stale": "blocked",
            "succeeded": "completed",
            "failed": "failed",
            "timed_out": "failed",
            "lost": "failed",
            "cancelled": "cancelled",
        }.get(status)
        if task_status:
            completed_at = timestamp if task_status in TASK_TERMINAL_STATUSES else None
            conn.execute(
                "UPDATE agent_tasks SET status = ?, completed_at = ?, updated_at = ? WHERE id = ?",
                (task_status, completed_at, timestamp, current["task_id"]),
            )
        legacy.log_audit(
            conn,
            actor=actor,
            action="execution.status_changed",
            entity_type="execution",
            entity_id=execution_id,
            detail=redact({"from": current_status, "to": status, "exit_code": exit_code}),
        )
        row = dict(conn.execute("SELECT * FROM executions WHERE id = ?", (execution_id,)).fetchone())
    return _parse_record(row)


def list_executions(
    *,
    status: str | None = None,
    limit: int = 100,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    apply_migrations(db_path)
    with legacy.connect(db_path) as conn:
        if status:
            data = _rows(
                conn,
                "SELECT * FROM executions WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            )
        else:
            data = _rows(conn, "SELECT * FROM executions ORDER BY created_at DESC LIMIT ?", (limit,))
    return [_parse_record(item) for item in data]


def get_execution(execution_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    apply_migrations(db_path)
    with legacy.connect(db_path) as conn:
        row = conn.execute("SELECT * FROM executions WHERE id = ?", (execution_id,)).fetchone()
        if row is None:
            return None
        execution = _parse_record(dict(row))
        execution["sessions"] = [
            _parse_record(item)
            for item in _rows(
                conn,
                "SELECT * FROM runtime_sessions WHERE execution_id = ? ORDER BY started_at DESC",
                (execution_id,),
            )
        ]
        execution["events"] = [
            _parse_record(item)
            for item in _rows(
                conn,
                "SELECT * FROM execution_events WHERE execution_id = ? ORDER BY seq",
                (execution_id,),
            )
        ]
        return execution


def list_events(
    *,
    after_seq: int = 0,
    limit: int = 200,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    apply_migrations(db_path)
    with legacy.connect(db_path) as conn:
        data = _rows(
            conn,
            "SELECT * FROM execution_events WHERE seq > ? ORDER BY seq LIMIT ?",
            (max(0, after_seq), limit),
        )
    return [_parse_record(item) for item in data]


def heartbeat_runtime_session(
    *,
    session_id: str,
    adapter_type: str,
    status: str = "running",
    execution_id: str | None = None,
    host_id: str | None = None,
    external_id: str = "",
    pid: int | None = None,
    tmux_session: str = "",
    metadata: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    apply_migrations(db_path)
    timestamp = now_iso()
    ended_at = timestamp if status in {"stopped", "failed", "cancelled"} else None
    with legacy.connect(db_path) as conn:
        current = conn.execute("SELECT id FROM runtime_sessions WHERE id = ?", (session_id,)).fetchone()
        if current:
            conn.execute(
                """
                UPDATE runtime_sessions SET execution_id = ?, host_id = ?, adapter_type = ?, external_id = ?,
                  status = ?, pid = ?, tmux_session = ?, metadata_json = ?, last_heartbeat_at = ?,
                  ended_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    execution_id,
                    host_id,
                    adapter_type,
                    external_id,
                    status,
                    pid,
                    tmux_session,
                    encode_json(redact(metadata or {})),
                    timestamp,
                    ended_at,
                    timestamp,
                    session_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO runtime_sessions
                  (id, execution_id, host_id, adapter_type, external_id, status, pid, tmux_session,
                   metadata_json, started_at, last_heartbeat_at, ended_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    execution_id,
                    host_id,
                    adapter_type,
                    external_id,
                    status,
                    pid,
                    tmux_session,
                    encode_json(redact(metadata or {})),
                    timestamp,
                    timestamp,
                    ended_at,
                    timestamp,
                ),
            )
        if host_id:
            conn.execute(
                "UPDATE hosts SET status = 'online', last_heartbeat_at = ?, updated_at = ? WHERE id = ?",
                (timestamp, timestamp, host_id),
            )
        if execution_id:
            conn.execute(
                "UPDATE executions SET last_heartbeat_at = ?, updated_at = ? WHERE id = ?",
                (timestamp, timestamp, execution_id),
            )
        row = dict(conn.execute("SELECT * FROM runtime_sessions WHERE id = ?", (session_id,)).fetchone())
    return _parse_record(row)


def list_runtime_sessions(
    *,
    stale_after_seconds: int = 90,
    offline_after_seconds: int = 300,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    apply_migrations(db_path)
    now = datetime.now(UTC)
    with legacy.connect(db_path) as conn:
        data = _rows(conn, "SELECT * FROM runtime_sessions ORDER BY updated_at DESC")
    result = []
    for item in data:
        heartbeat = _parse_iso(item.get("last_heartbeat_at"))
        observed_status = item["status"]
        if heartbeat and item["status"] not in {"stopped", "failed"}:
            age = max(0, int((now - heartbeat).total_seconds()))
            if age >= offline_after_seconds:
                observed_status = "offline"
            elif age >= stale_after_seconds:
                observed_status = "stale"
            item["heartbeat_age_seconds"] = age
        item["observed_status"] = observed_status
        result.append(_parse_record(item))
    return result


def request_approval(
    *,
    action: str,
    requested_by: str,
    task_id: str | None = None,
    execution_id: str | None = None,
    reason: str = "",
    ttl_seconds: int = 3600,
    metadata: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    if not task_id and not execution_id:
        raise ValueError("task_id or execution_id is required")
    apply_migrations(db_path)
    timestamp = datetime.now(UTC).replace(microsecond=0)
    approval_id = new_id("approval")
    with legacy.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO approvals
              (id, task_id, execution_id, action, status, requested_by, reason, metadata_json,
               requested_at, expires_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)
            """,
            (
                approval_id,
                task_id,
                execution_id,
                action,
                requested_by,
                str(redact(reason)),
                encode_json(redact(metadata or {})),
                timestamp.isoformat(),
                (timestamp + timedelta(seconds=max(60, ttl_seconds))).isoformat(),
            ),
        )
        if task_id:
            conn.execute(
                "UPDATE agent_tasks SET status = 'awaiting_approval', updated_at = ? WHERE id = ?",
                (timestamp.isoformat(), task_id),
            )
        if execution_id:
            conn.execute(
                "UPDATE executions SET status = 'awaiting_approval', updated_at = ? WHERE id = ?",
                (timestamp.isoformat(), execution_id),
            )
        append_event_conn(
            conn,
            task_id=task_id,
            execution_id=execution_id,
            event_type="approval.requested",
            status="pending",
            message=reason,
            metadata={"approval_id": approval_id, "action": action},
        )
        legacy.log_audit(
            conn,
            actor=requested_by,
            action="approval.requested",
            entity_type="approval",
            entity_id=approval_id,
            detail=redact({"action": action, "task_id": task_id, "execution_id": execution_id}),
        )
        row = dict(conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone())
    return _parse_record(row)


def decide_approval(
    approval_id: str,
    *,
    decision: str,
    decided_by: str,
    reason: str = "",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    if decision not in {"approved", "rejected"}:
        raise ValueError("decision must be approved or rejected")
    apply_migrations(db_path)
    timestamp = datetime.now(UTC).replace(microsecond=0)
    with legacy.connect(db_path) as conn:
        current = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if current is None:
            raise KeyError(approval_id)
        if current["status"] != "pending":
            if current["status"] == decision:
                return _parse_record(dict(current))
            raise ValueError(f"Approval already decided: {current['status']}")
        expires_at = _parse_iso(current["expires_at"])
        if expires_at and expires_at < timestamp:
            conn.execute("UPDATE approvals SET status = 'expired', decided_at = ? WHERE id = ?", (timestamp.isoformat(), approval_id))
            raise ValueError("Approval expired")
        conn.execute(
            "UPDATE approvals SET status = ?, decided_by = ?, reason = ?, decided_at = ? WHERE id = ?",
            (decision, decided_by, str(redact(reason)), timestamp.isoformat(), approval_id),
        )
        append_event_conn(
            conn,
            task_id=current["task_id"],
            execution_id=current["execution_id"],
            event_type="approval.decided",
            status=decision,
            message=reason,
            metadata={"approval_id": approval_id, "decided_by": decided_by},
        )
        if decision == "rejected" and current["task_id"]:
            conn.execute(
                "UPDATE agent_tasks SET status = 'blocked', updated_at = ? WHERE id = ?",
                (timestamp.isoformat(), current["task_id"]),
            )
        legacy.log_audit(
            conn,
            actor=decided_by,
            action=f"approval.{decision}",
            entity_type="approval",
            entity_id=approval_id,
            detail={"decision": decision},
        )
        row = dict(conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone())
    return _parse_record(row)


def list_approvals(
    *,
    status: str | None = None,
    limit: int = 100,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    apply_migrations(db_path)
    with legacy.connect(db_path) as conn:
        if status:
            data = _rows(
                conn,
                "SELECT * FROM approvals WHERE status = ? ORDER BY requested_at DESC LIMIT ?",
                (status, limit),
            )
        else:
            data = _rows(conn, "SELECT * FROM approvals ORDER BY requested_at DESC LIMIT ?", (limit,))
    return [_parse_record(item) for item in data]


def get_approval(approval_id: str, *, db_path: str | Path | None = None) -> dict[str, Any] | None:
    apply_migrations(db_path)
    with legacy.connect(db_path) as conn:
        row = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
    return None if row is None else _parse_record(dict(row))


def add_artifact(
    *,
    path: str,
    task_id: str | None = None,
    execution_id: str | None = None,
    kind: str = "file",
    sha256: str = "",
    size_bytes: int | None = None,
    mime_type: str = "",
    metadata: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    if not task_id and not execution_id:
        raise ValueError("task_id or execution_id is required")
    apply_migrations(db_path)
    artifact_id = new_id("artifact")
    with legacy.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO artifacts
              (id, task_id, execution_id, kind, path, sha256, size_bytes, mime_type, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id,
                task_id,
                execution_id,
                kind,
                path,
                sha256,
                size_bytes,
                mime_type,
                encode_json(redact(metadata or {})),
                now_iso(),
            ),
        )
        append_event_conn(
            conn,
            task_id=task_id,
            execution_id=execution_id,
            event_type="artifact.created",
            status="available",
            message=path,
            metadata={"artifact_id": artifact_id, "kind": kind, "sha256": sha256},
        )
        row = dict(conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone())
    return _parse_record(row)


def acquire_writer_lease(
    *,
    resource_key: str,
    owner_id: str,
    ttl_seconds: int = 60,
    metadata: dict[str, Any] | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    apply_migrations(db_path)
    now = datetime.now(UTC).replace(microsecond=0)
    expires = now + timedelta(seconds=max(10, ttl_seconds))
    with legacy.connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute("SELECT * FROM writer_leases WHERE resource_key = ?", (resource_key,)).fetchone()
        if current and current["owner_id"] != owner_id:
            current_expiry = _parse_iso(current["expires_at"])
            if current_expiry and current_expiry > now:
                return None
        fence_token = int(current["fence_token"]) + 1 if current else 1
        acquired_at = current["acquired_at"] if current and current["owner_id"] == owner_id else now.isoformat()
        conn.execute(
            """
            INSERT INTO writer_leases
              (resource_key, owner_id, fence_token, metadata_json, acquired_at, heartbeat_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(resource_key) DO UPDATE SET
              owner_id = excluded.owner_id,
              fence_token = excluded.fence_token,
              metadata_json = excluded.metadata_json,
              acquired_at = excluded.acquired_at,
              heartbeat_at = excluded.heartbeat_at,
              expires_at = excluded.expires_at
            """,
            (
                resource_key,
                owner_id,
                fence_token,
                encode_json(redact(metadata or {})),
                acquired_at,
                now.isoformat(),
                expires.isoformat(),
            ),
        )
        row = dict(conn.execute("SELECT * FROM writer_leases WHERE resource_key = ?", (resource_key,)).fetchone())
    return _parse_record(row)


def renew_writer_lease(
    *,
    resource_key: str,
    owner_id: str,
    fence_token: int,
    ttl_seconds: int = 60,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    apply_migrations(db_path)
    now = datetime.now(UTC).replace(microsecond=0)
    with legacy.connect(db_path) as conn:
        changed = conn.execute(
            """
            UPDATE writer_leases SET heartbeat_at = ?, expires_at = ?
            WHERE resource_key = ? AND owner_id = ? AND fence_token = ?
            """,
            (
                now.isoformat(),
                (now + timedelta(seconds=max(10, ttl_seconds))).isoformat(),
                resource_key,
                owner_id,
                fence_token,
            ),
        ).rowcount
        if not changed:
            return None
        row = dict(conn.execute("SELECT * FROM writer_leases WHERE resource_key = ?", (resource_key,)).fetchone())
    return _parse_record(row)


def release_writer_lease(
    *,
    resource_key: str,
    owner_id: str,
    fence_token: int,
    db_path: str | Path | None = None,
) -> bool:
    apply_migrations(db_path)
    with legacy.connect(db_path) as conn:
        changed = conn.execute(
            "DELETE FROM writer_leases WHERE resource_key = ? AND owner_id = ? AND fence_token = ?",
            (resource_key, owner_id, fence_token),
        ).rowcount
    return bool(changed)


def _legacy_ids(request_id: str) -> tuple[str, str]:
    digest = hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:16]
    return f"task_legacy_{digest}", f"exec_legacy_{digest}"


def mirror_legacy_request(request_id: str, *, db_path: str | Path | None = None) -> str | None:
    apply_migrations(db_path)
    task_id, execution_id = _legacy_ids(request_id)
    timestamp = now_iso()
    with legacy.connect(db_path) as conn:
        request = conn.execute("SELECT * FROM agent_requests WHERE id = ?", (request_id,)).fetchone()
        if request is None:
            return None
        task_status = {
            "received": "queued",
            "queued": "queued",
            "running": "running",
            "completed": "completed",
            "failed": "failed",
            "cancelled": "cancelled",
            "ignored": "cancelled",
        }.get(request["status"], "blocked")
        task_exists = conn.execute("SELECT status FROM agent_tasks WHERE id = ?", (task_id,)).fetchone()
        title = legacy.safe_summary(request["command"] or request["prompt"] or "Messenger request", 120)
        if task_exists is None:
            conn.execute(
                """
                INSERT INTO agent_tasks
                  (id, source_request_id, title, prompt, status, requested_by, metadata_json,
                   created_at, updated_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    request_id,
                    title,
                    request["prompt"],
                    task_status,
                    f"{request['source']}:{request['user_id']}",
                    encode_json({"legacy": True, "channel_id": request["channel_id"]}),
                    request["created_at"],
                    request["updated_at"],
                    request["ended_at"] if task_status in TASK_TERMINAL_STATUSES else None,
                ),
            )
            append_event_conn(
                conn,
                task_id=task_id,
                event_type="legacy.request_imported",
                status=task_status,
                message="Legacy messenger request imported",
                metadata={"source_request_id": request_id},
            )
        elif task_exists["status"] != task_status:
            conn.execute(
                "UPDATE agent_tasks SET status = ?, updated_at = ?, completed_at = ? WHERE id = ?",
                (
                    task_status,
                    request["updated_at"],
                    request["ended_at"] if task_status in TASK_TERMINAL_STATUSES else None,
                    task_id,
                ),
            )
            append_event_conn(
                conn,
                task_id=task_id,
                event_type="legacy.request_status",
                status=task_status,
                message=f"Legacy request status synchronized to {task_status}",
                metadata={"source_request_id": request_id},
            )
        execution_status = {
            "received": "pending",
            "queued": "pending",
            "running": "running",
            "completed": "succeeded",
            "failed": "failed",
            "cancelled": "cancelled",
            "ignored": "cancelled",
        }.get(request["status"], "lost")
        execution = conn.execute("SELECT status FROM executions WHERE id = ?", (execution_id,)).fetchone()
        if execution is None:
            conn.execute(
                """
                INSERT INTO executions
                  (id, task_id, adapter_type, status, command_summary, metadata_json, created_at,
                   started_at, ended_at, last_heartbeat_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution_id,
                    task_id,
                    request["provider"] or request["mode"] or "messenger",
                    execution_status,
                    title,
                    encode_json({"legacy": True, "source_request_id": request_id}),
                    request["created_at"],
                    request["started_at"],
                    request["ended_at"],
                    request["updated_at"],
                    request["updated_at"],
                ),
            )
            conn.execute(
                "UPDATE agent_tasks SET current_execution_id = ? WHERE id = ?",
                (execution_id, task_id),
            )
            append_event_conn(
                conn,
                task_id=task_id,
                execution_id=execution_id,
                event_type="legacy.execution_imported",
                status=execution_status,
                message="Legacy execution imported",
                metadata={"source_request_id": request_id},
            )
        elif execution["status"] != execution_status:
            conn.execute(
                """
                UPDATE executions SET status = ?, exit_code = ?, error = ?, started_at = ?, ended_at = ?,
                  last_heartbeat_at = ?, updated_at = ? WHERE id = ?
                """,
                (
                    execution_status,
                    0 if execution_status == "succeeded" else None,
                    str(redact(request["error"])),
                    request["started_at"],
                    request["ended_at"],
                    request["updated_at"],
                    request["updated_at"],
                    execution_id,
                ),
            )
            append_event_conn(
                conn,
                task_id=task_id,
                execution_id=execution_id,
                event_type="legacy.execution_status",
                status=execution_status,
                message=f"Legacy execution synchronized to {execution_status}",
                metadata={"source_request_id": request_id},
            )
        conn.execute("UPDATE agent_tasks SET updated_at = ? WHERE id = ?", (request["updated_at"] or timestamp, task_id))
    return task_id


def reconcile_legacy_requests(*, limit: int = 500, db_path: str | Path | None = None) -> dict[str, int]:
    apply_migrations(db_path)
    with legacy.connect(db_path) as conn:
        request_ids = [
            row["id"]
            for row in conn.execute("SELECT id FROM agent_requests ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        ]
    imported = 0
    for request_id in request_ids:
        if mirror_legacy_request(request_id, db_path=db_path):
            imported += 1
    return {"scanned": len(request_ids), "synchronized": imported}
