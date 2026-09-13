"""Exact, expiring, single-use approval for the low-level command coordinator.

This contract authorizes one command invocation; it does not implement a
per-file patch review or authorize direct messenger write delegation.
"""

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

from nyanya_agent import execution_store as ledger


def command_scope(*, command, cwd, adapter_type, write_resource_key, env=None, timeout_seconds=600) -> str:
    payload = {"command": list(command), "cwd": str(Path(cwd).resolve(strict=True)),
               "adapter": adapter_type, "resource": write_resource_key,
               "env": env or {}, "timeout": timeout_seconds}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def check_approval(db_path, approval_id, task_id, scope_hash, *, execution_id=None) -> None:
    with ledger.legacy.connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if row is None:
            raise PermissionError("A persisted approval is required")
        metadata = ledger.decode_json(row["metadata_json"], {})
        expiry = ledger._parse_iso(row["expires_at"])
        if (row["status"] != "approved" or row["task_id"] != task_id or row["action"] != "workspace.write"
                or expiry is None or expiry <= datetime.now(UTC)
                or not metadata.get("authorized_actor") or metadata["authorized_actor"] != row["decided_by"]
                or metadata.get("scope_hash") != scope_hash):
            raise PermissionError("Approval is expired, consumed, or does not match this actor and command scope")
        if execution_id:
            conn.execute("UPDATE approvals SET status = 'consumed', execution_id = ? WHERE id = ?",
                         (execution_id, approval_id))
            ledger.append_event_conn(conn, task_id=task_id, execution_id=execution_id,
                                     event_type="approval.consumed", status="consumed", message="Bound approval consumed")
