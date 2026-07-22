from __future__ import annotations

from datetime import UTC, datetime, timedelta
import sqlite3

import pytest

from nyanya_agent import dashboard_store as legacy
from nyanya_agent import execution_store as store


def test_versioned_migration_is_idempotent_and_events_are_append_only(tmp_path):
    db_path = tmp_path / "ledger.db"

    first = store.schema_state(db_path)
    second = store.schema_state(db_path)

    assert first["version"] == first["latest"] == 1
    assert second["migrations"] == first["migrations"]

    task = store.create_task(title="Build ledger", db_path=db_path)
    event = store.list_events(db_path=db_path)[0]

    with legacy.connect(db_path) as conn:
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("UPDATE execution_events SET message = 'changed' WHERE seq = ?", (event["seq"],))

    assert store.get_task(task["id"], db_path=db_path)["status"] == "queued"


def test_task_execution_lifecycle_and_status_projection(tmp_path):
    db_path = tmp_path / "ledger.db"
    host = store.register_host(name="mac-a", role="control-hub", db_path=db_path)
    agent = store.upsert_agent_profile(name="codex-read", adapter_type="codex", db_path=db_path)
    task = store.create_task(title="Inspect", assigned_agent_id=agent["id"], db_path=db_path)
    execution = store.create_execution(
        task_id=task["id"],
        adapter_type="codex",
        host_id=host["id"],
        agent_profile_id=agent["id"],
        db_path=db_path,
    )

    store.transition_execution(execution["id"], "running", db_path=db_path)
    completed = store.transition_execution(execution["id"], "succeeded", exit_code=0, db_path=db_path)

    assert completed["status"] == "succeeded"
    assert completed["ended_at"]
    assert store.get_task(task["id"], db_path=db_path)["status"] == "completed"
    with pytest.raises(ValueError, match="Invalid execution transition"):
        store.transition_execution(execution["id"], "running", db_path=db_path)


def test_approval_and_audit_metadata_are_redacted(tmp_path):
    db_path = tmp_path / "ledger.db"
    task = store.create_task(title="Approved write", metadata={"api_key": "secret-value"}, db_path=db_path)
    approval = store.request_approval(
        task_id=task["id"],
        action="workspace.write",
        requested_by="agent",
        reason="token=secret-value",
        metadata={"password": "secret-value"},
        db_path=db_path,
    )
    decided = store.decide_approval(
        approval["id"],
        decision="approved",
        decided_by="operator",
        db_path=db_path,
    )

    assert decided["status"] == "approved"
    assert approval["metadata"]["password"] == "[REDACTED]"
    assert "secret-value" not in approval["reason"]
    assert "secret-value" not in str(store.list_events(db_path=db_path))


def test_writer_lease_uses_fencing_and_owner_checks(tmp_path):
    db_path = tmp_path / "ledger.db"
    first = store.acquire_writer_lease(resource_key="repo:main", owner_id="worker-a", db_path=db_path)

    assert first is not None
    assert first["fence_token"] == 1
    assert store.acquire_writer_lease(resource_key="repo:main", owner_id="worker-b", db_path=db_path) is None
    renewed = store.renew_writer_lease(
        resource_key="repo:main",
        owner_id="worker-a",
        fence_token=first["fence_token"],
        db_path=db_path,
    )
    assert renewed is not None
    assert store.release_writer_lease(
        resource_key="repo:main",
        owner_id="worker-a",
        fence_token=first["fence_token"],
        db_path=db_path,
    )


def test_heartbeat_reports_stale_and_offline_without_destroying_raw_status(tmp_path):
    db_path = tmp_path / "ledger.db"
    host = store.register_host(name="mac-b", db_path=db_path)
    session = store.heartbeat_runtime_session(
        session_id="tmux-1",
        adapter_type="tmux",
        host_id=host["id"],
        db_path=db_path,
    )
    old = (datetime.now(UTC) - timedelta(seconds=400)).replace(microsecond=0).isoformat()
    with legacy.connect(db_path) as conn:
        conn.execute("UPDATE hosts SET last_heartbeat_at = ? WHERE id = ?", (old, host["id"]))
        conn.execute("UPDATE runtime_sessions SET last_heartbeat_at = ? WHERE id = ?", (old, session["id"]))

    assert store.list_hosts(db_path=db_path)[0]["observed_status"] == "offline"
    assert store.list_runtime_sessions(db_path=db_path)[0]["observed_status"] == "offline"


def test_legacy_request_is_synchronized_on_status_change(tmp_path):
    db_path = tmp_path / "ledger.db"
    request_id = legacy.create_agent_request(prompt="legacy request", db_path=db_path)

    task = store.list_tasks(db_path=db_path)[0]
    assert task["source_request_id"] == request_id
    assert task["status"] == "queued"

    legacy.mark_request_status(request_id, "running", db_path=db_path)
    legacy.mark_request_status(request_id, "completed", result_summary="ok", db_path=db_path)

    task = store.get_task(task["id"], db_path=db_path)
    assert task is not None
    assert task["status"] == "completed"
    assert task["executions"][0]["status"] == "succeeded"
