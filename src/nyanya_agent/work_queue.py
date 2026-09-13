"""Atomic local worker ownership and result commits over the execution ledger.

Expired work is never automatically claimed again. The operator must reconcile
it; callbacks are intentionally not reconstructed from untrusted stored data.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from nyanya_agent import execution_store as ledger
from nyanya_agent.task_outcomes import TaskOutcome


def pending_tasks(db_path, owner_key: str | None = None) -> list[dict[str, Any]]:
    ledger.apply_migrations(db_path)
    query = "SELECT * FROM agent_tasks WHERE status NOT IN ('completed', 'failed', 'cancelled')"
    params: tuple = ()
    if owner_key:
        query += " AND COALESCE(json_extract(metadata_json, '$.owner_key'), requested_by) = ?"
        params = (owner_key,)
    with ledger.legacy.connect(db_path) as conn:
        rows = conn.execute(query + " ORDER BY priority, created_at, rowid", params).fetchall()
    return [ledger._parse_record(dict(row)) for row in rows]


def claim(db_path, task_id: str, worker_id: str, owner_key: str, ttl: int = 30) -> dict[str, Any] | None:
    now = datetime.now(UTC)
    timestamp = now.isoformat()
    with ledger.legacy.connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        task = conn.execute("SELECT * FROM agent_tasks WHERE id = ?", (task_id,)).fetchone()
        if not task or task["status"] != "queued":
            return None
        metadata = ledger.decode_json(task["metadata_json"], {})
        if (metadata.get("owner_key") or task["requested_by"] or "operator") != owner_key:
            return None
        # Even an expired claim requires explicit reconciliation, never takeover.
        if conn.execute("SELECT 1 FROM task_claims WHERE task_id = ?", (task_id,)).fetchone():
            return None
        if conn.execute(
            "SELECT 1 FROM task_claims WHERE owner_key = ? AND released = 0", (owner_key,)
        ).fetchone():
            return None
        execution_id = ledger.new_id("exec")
        conn.execute(
            "INSERT INTO executions (id, task_id, adapter_type, status, workdir, metadata_json, "
            "created_at, started_at, updated_at, last_heartbeat_at) VALUES (?, ?, ?, 'running', ?, ?, ?, ?, ?, ?)",
            (execution_id, task_id, metadata.get("execution_adapter", "provider"), metadata.get("workspace_root", ""),
             ledger.encode_json({"worker_id": worker_id}), timestamp, timestamp, timestamp, timestamp),
        )
        conn.execute(
            "INSERT INTO task_claims (task_id, worker_id, owner_key, execution_id, expires_at) VALUES (?, ?, ?, ?, ?)",
            (task_id, worker_id, owner_key, execution_id, (now + timedelta(seconds=ttl)).isoformat()),
        )
        conn.execute(
            "UPDATE agent_tasks SET status = 'running', current_execution_id = ?, updated_at = ? WHERE id = ?",
            (execution_id, timestamp, task_id),
        )
        ledger.append_event_conn(conn, task_id=task_id, execution_id=execution_id,
                                 event_type="task.claimed", status="running", message="Local worker claimed task")
    return {"task_id": task_id, "worker_id": worker_id, "execution_id": execution_id}


def renew(db_path, claim_record: dict[str, Any], ttl: int = 30) -> bool:
    now = datetime.now(UTC)
    with ledger.legacy.connect(db_path) as conn:
        changed = conn.execute(
            "UPDATE task_claims SET expires_at = ? WHERE task_id = ? AND worker_id = ? "
            "AND execution_id = ? AND released = 0 AND expires_at > ?",
            ((now + timedelta(seconds=ttl)).isoformat(), claim_record["task_id"], claim_record["worker_id"],
             claim_record["execution_id"], now.isoformat()),
        ).rowcount
        if changed:
            conn.execute("UPDATE executions SET last_heartbeat_at = ? WHERE id = ?",
                         (now.isoformat(), claim_record["execution_id"]))
    return bool(changed)


def finish(db_path, claim_record: dict[str, Any], outcome: TaskOutcome) -> None:
    timestamp = datetime.now(UTC).isoformat()
    task_id, execution_id = claim_record["task_id"], claim_record["execution_id"]
    task_status = {"succeeded": "completed", "timed_out": "failed"}.get(outcome.status, outcome.status)
    execution_status = "lost" if outcome.status == "blocked" else outcome.status
    terminal = task_status in ledger.TASK_TERMINAL_STATUSES
    with ledger.legacy.connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute(
            "SELECT c.*, t.current_execution_id, e.status AS execution_status FROM task_claims c "
            "JOIN agent_tasks t ON t.id = c.task_id JOIN executions e ON e.id = c.execution_id "
            "WHERE c.task_id = ?", (task_id,),
        ).fetchone()
        if (not current or current["worker_id"] != claim_record["worker_id"]
                or current["execution_id"] != execution_id or current["current_execution_id"] != execution_id
                or current["released"] or current["expires_at"] <= timestamp
                or current["execution_status"] in ledger.EXECUTION_TERMINAL_STATUSES):
            raise ValueError("Stale worker result rejected")
        if current["execution_status"] == "cancelling" and outcome.status != "cancelled":
            # Cancellation acknowledgement is not evidence of process termination.
            task_status, execution_status = "blocked", "lost"
            outcome = TaskOutcome("blocked", outcome.text + "\n취소 완료를 확인하지 못했습니다. 실행 상태 확인이 필요합니다.")
            terminal = False
        conn.execute(
            "UPDATE executions SET status = ?, ended_at = ?, updated_at = ? WHERE id = ?",
            (execution_status, timestamp if execution_status in ledger.EXECUTION_TERMINAL_STATUSES else None,
             timestamp, execution_id),
        )
        conn.execute(
            "UPDATE agent_tasks SET status = ?, completed_at = ?, updated_at = ? WHERE id = ?",
            (task_status, timestamp if terminal else None, timestamp, task_id),
        )
        conn.execute("UPDATE task_claims SET released = 1 WHERE task_id = ?", (task_id,))
        conn.execute(
            "INSERT INTO task_results (execution_id, task_id, outcome, response, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (execution_id, task_id, outcome.status, ledger.redact(outcome.text), timestamp, timestamp),
        )
        conn.execute(
            "UPDATE task_operations SET eligible=0,hold_reason=?,diagnosis=? WHERE task_id=?",
            ("" if outcome.status == "succeeded" else outcome.status,
             ledger.redact(outcome.text) if outcome.status != "succeeded" else "", task_id),
        )
        spec = claim_record.get("spec")
        if outcome.status == "succeeded" and spec and spec.kind == "apply":
            plan = conn.execute("SELECT task_id FROM change_plans WHERE id=? AND status='applied'", (spec.plan_id,)).fetchone()
            if not plan:
                raise ValueError("Applied plan evidence missing")
            changed = conn.execute(
                "UPDATE agent_tasks SET status='completed',completed_at=?,updated_at=? WHERE id=? AND status='awaiting_approval'",
                (timestamp, timestamp, plan["task_id"]),
            ).rowcount
            if changed:
                ledger.append_event_conn(conn, task_id=plan["task_id"], event_type="task.plan_completed",
                                         status="completed", message="Approved file apply committed",
                                         metadata={"apply_task_id": task_id, "plan_id": spec.plan_id})
        if outcome.status == "awaiting_approval":
            conn.execute(
                "INSERT INTO approvals (id, task_id, execution_id, action, status, requested_by, reason, "
                "metadata_json, requested_at, expires_at) VALUES (?, ?, ?, 'feedback.review', 'pending', ?, ?, '{}', ?, ?)",
                (ledger.new_id("approval"), task_id, execution_id, claim_record["worker_id"],
                 "Review the concrete file change plan; this feedback does not grant CLI write access", timestamp,
                 (datetime.now(UTC) + timedelta(hours=1)).isoformat()),
            )
        ledger.append_event_conn(conn, task_id=task_id, execution_id=execution_id,
                                 event_type="task.result", status=task_status, message="Worker result committed")


def record_delivery(db_path, execution_id: str, *, delivered: bool, error: str = "") -> None:
    with ledger.legacy.connect(db_path) as conn:
        conn.execute(
            "UPDATE task_results SET delivery_status = ?, delivery_error = ?, updated_at = ? WHERE execution_id = ?",
            ("delivered" if delivered else "uncertain", error, datetime.now(UTC).isoformat(), execution_id),
        )


def result(db_path, task_id: str, owner_key: str) -> dict[str, Any] | None:
    with ledger.legacy.connect(db_path) as conn:
        row = conn.execute(
            "SELECT r.* FROM task_results r JOIN agent_tasks t ON t.id = r.task_id "
            "WHERE t.id = ? AND COALESCE(json_extract(t.metadata_json, '$.owner_key'), t.requested_by) = ? "
            "ORDER BY r.created_at DESC LIMIT 1", (task_id, owner_key),
        ).fetchone()
    return dict(row) if row else None


def recovery_tasks(db_path, worker_id: str) -> list[dict[str, Any]]:
    """Read-only inventory; lease expiry is not proof the external process stopped."""
    timestamp = datetime.now(UTC).isoformat()
    with ledger.legacy.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT t.* FROM agent_tasks t LEFT JOIN task_claims c ON c.task_id = t.id "
            "WHERE t.status IN ('queued', 'running', 'blocked', 'awaiting_approval', 'cancelling') "
            "AND (c.task_id IS NULL OR (c.worker_id != ? AND (c.released = 1 OR c.expires_at <= ?))) "
            "ORDER BY t.created_at, t.id", (worker_id, timestamp),
        ).fetchall()
    return [ledger._parse_record(dict(row)) for row in rows]
