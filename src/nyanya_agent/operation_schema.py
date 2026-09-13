"""Additive P0 operation/worker/plan and recovery schema."""

SQL = """
CREATE TABLE operation_workers (
 id TEXT PRIMARY KEY, heartbeat_at TEXT NOT NULL, closed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE task_operations (
 task_id TEXT PRIMARY KEY REFERENCES agent_tasks(id), spec_json TEXT NOT NULL,
 worker_generation TEXT NOT NULL, eligible INTEGER NOT NULL DEFAULT 1,
 attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3,
 hold_reason TEXT NOT NULL DEFAULT '', assessment_json TEXT NOT NULL DEFAULT '{}',
 diagnosis TEXT NOT NULL DEFAULT '', parent_task_id TEXT REFERENCES agent_tasks(id)
);
CREATE TABLE change_plans (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES agent_tasks(id), owner_key TEXT NOT NULL,
 workspace TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, plan_hash TEXT NOT NULL,
 changes_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
 expires_at TEXT NOT NULL, decided_by TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE change_journal (
 plan_id TEXT NOT NULL REFERENCES change_plans(id), ordinal INTEGER NOT NULL,
 path TEXT NOT NULL, before_hash TEXT, after_hash TEXT, before_content BLOB,
 state TEXT NOT NULL DEFAULT 'prepared', PRIMARY KEY(plan_id, ordinal)
);
CREATE INDEX idx_operations_eligible ON task_operations(eligible,worker_generation);

CREATE VIEW request_read_model AS SELECT r.id,r.source,r.guild_id,r.channel_id,r.channel_name,r.user_id,r.trigger,r.command,r.mode,r.provider,r.model,r.prompt,COALESCE(t.status,r.status) AS status,COALESCE(result.response,r.result_summary) AS result_summary,r.error,r.prompt_tokens,r.completion_tokens,r.total_tokens,r.started_at,COALESCE(t.completed_at,r.ended_at) AS ended_at,r.duration_ms,r.metadata_json,r.created_at,COALESCE(t.updated_at,r.updated_at) AS updated_at FROM agent_requests r LEFT JOIN agent_tasks t ON t.source_request_id=r.id LEFT JOIN task_results result ON result.execution_id=t.current_execution_id;
"""
