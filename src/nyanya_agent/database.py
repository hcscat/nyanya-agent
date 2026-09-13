"""Shared SQLite infrastructure; no dashboard, provider or environment-file imports."""

from contextlib import contextmanager
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4
from typing import Any
from nyanya_agent.runtime_paths import resolve_state_root, resolve_code_root


def now_iso():
    return datetime.now(UTC).isoformat()


def new_id(prefix):
    return f"{prefix}_{uuid4().hex[:12]}"


def encode_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def resolve_db_path(db_path=None):
    root = resolve_state_root(resolve_code_root())
    path = Path(db_path or os.getenv("NYANYA_DASHBOARD_DB_PATH") or root / "data/nyanya_dashboard.db").expanduser()
    return (path if path.is_absolute() else root / path).resolve()


@contextmanager
def connect(db_path=None):
    path = resolve_db_path(db_path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        pass
    else:
        os.close(fd)
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 10000")
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

CREATE TABLE IF NOT EXISTS memory_items (
  id TEXT PRIMARY KEY,
  owner_key TEXT NOT NULL DEFAULT 'global',
  memory_type TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  importance REAL NOT NULL DEFAULT 0,
  confidence REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending',
  source_request_id TEXT REFERENCES agent_requests(id) ON DELETE SET NULL,
  evidence_count INTEGER NOT NULL DEFAULT 1,
  explicit_score REAL NOT NULL DEFAULT 0,
  frequency_score REAL NOT NULL DEFAULT 0,
  outcome_score REAL NOT NULL DEFAULT 0,
  correction_score REAL NOT NULL DEFAULT 0,
  risk_score REAL NOT NULL DEFAULT 0,
  recency_score REAL NOT NULL DEFAULT 0,
  graph_score REAL NOT NULL DEFAULT 0,
  retrieval_score REAL NOT NULL DEFAULT 0,
  staleness_penalty REAL NOT NULL DEFAULT 0,
  sensitivity TEXT NOT NULL DEFAULT 'normal',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_used_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_memory_items_status ON memory_items(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_memory_items_owner_type ON memory_items(owner_key, memory_type, importance);
CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_items_source_type_title
  ON memory_items(COALESCE(source_request_id, ''), memory_type, title);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_items_fts USING fts5(
  title,
  content,
  memory_type UNINDEXED,
  owner_key UNINDEXED,
  content='memory_items',
  content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS memory_items_ai AFTER INSERT ON memory_items BEGIN
  INSERT INTO memory_items_fts(rowid, title, content, memory_type, owner_key)
  VALUES (new.rowid, new.title, new.content, new.memory_type, new.owner_key);
END;

CREATE TRIGGER IF NOT EXISTS memory_items_ad AFTER DELETE ON memory_items BEGIN
  INSERT INTO memory_items_fts(memory_items_fts, rowid, title, content, memory_type, owner_key)
  VALUES('delete', old.rowid, old.title, old.content, old.memory_type, old.owner_key);
END;

CREATE TRIGGER IF NOT EXISTS memory_items_au AFTER UPDATE ON memory_items BEGIN
  INSERT INTO memory_items_fts(memory_items_fts, rowid, title, content, memory_type, owner_key)
  VALUES('delete', old.rowid, old.title, old.content, old.memory_type, old.owner_key);
  INSERT INTO memory_items_fts(rowid, title, content, memory_type, owner_key)
  VALUES (new.rowid, new.title, new.content, new.memory_type, new.owner_key);
END;

CREATE TABLE IF NOT EXISTS memory_edges (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES memory_items(id) ON DELETE CASCADE,
  target_id TEXT NOT NULL REFERENCES memory_items(id) ON DELETE CASCADE,
  relation TEXT NOT NULL DEFAULT 'related_to',
  weight REAL NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  UNIQUE(source_id, target_id, relation)
);

CREATE INDEX IF NOT EXISTS idx_memory_edges_source ON memory_edges(source_id);
"""


def init_db(db_path=None):
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)


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
