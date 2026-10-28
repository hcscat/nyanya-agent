"""Audit rows record useful transitions without repeating heartbeat or memory text."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json

from nyanya_agent import dashboard_store, execution_store


def test_host_heartbeat_and_meaningful_update_have_distinct_audit_behavior(tmp_path):
    db_path = tmp_path / "audit.db"
    first = execution_store.register_host(name="test-host", metadata={"note": "private host note"}, db_path=db_path)
    old = (datetime.now(UTC) - timedelta(minutes=2)).isoformat()
    with dashboard_store.connect(db_path) as conn:
        conn.execute("UPDATE hosts SET last_heartbeat_at = ? WHERE id = ?", (old, first["id"]))

    heartbeat = execution_store.register_host(name="test-host", metadata={"note": "private host note"}, db_path=db_path)
    assert heartbeat["id"] == first["id"]
    assert heartbeat["last_heartbeat_at"] != old
    assert [entry["action"] for entry in dashboard_store.audit_log(db_path=db_path)] == ["host.registered"]

    updated = execution_store.register_host(
        name="test-host", status="busy", metadata={"note": "new private note"}, db_path=db_path
    )
    assert updated["status"] == "busy"
    audits = dashboard_store.audit_log(db_path=db_path)
    assert [entry["action"] for entry in audits].count("host.registered") == 1
    assert [entry["action"] for entry in audits].count("host.updated") == 1
    changed = next(entry for entry in audits if entry["action"] == "host.updated")
    assert set(changed["detail"]["changed_fields"]) == {"status", "metadata"}
    assert "private" not in json.dumps([entry["detail"] for entry in audits])


def test_concurrent_identical_host_registration_creates_one_audit(tmp_path):
    db_path = tmp_path / "audit.db"

    def register(_):
        return execution_store.register_host(name="shared-host", db_path=db_path)["id"]

    with ThreadPoolExecutor(max_workers=8) as executor:
        ids = list(executor.map(register, range(24)))

    assert len(set(ids)) == 1
    with dashboard_store.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM hosts WHERE name = 'shared-host'").fetchone()[0] == 1
    assert [entry["action"] for entry in dashboard_store.audit_log(db_path=db_path)] == ["host.registered"]


def test_memory_audit_omits_query_owner_and_edited_values(tmp_path):
    db_path = tmp_path / "audit.db"
    dashboard_store.init_db(db_path)
    memory_id = "mem_private_test"
    with dashboard_store.connect(db_path) as conn:
        conn.execute(
            """INSERT INTO memory_items
               (id, owner_key, memory_type, title, content, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                memory_id,
                "operator:private-owner",
                "preference",
                "private title",
                "needleword private original content",
                "approved",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )

    found = dashboard_store.search_approved_memories(
        "needleword private query", owner_key="operator:private-owner", db_path=db_path
    )
    assert [item["id"] for item in found] == [memory_id]
    dashboard_store.update_memory(
        memory_id, title="new private title", content="new private content", db_path=db_path
    )
    dashboard_store.update_memory(
        memory_id, title="new private title", content="new private content", db_path=db_path
    )

    audits = dashboard_store.audit_log(db_path=db_path)
    assert [entry["action"] for entry in audits].count("memory.retrieved") == 1
    assert [entry["action"] for entry in audits].count("memory.updated") == 1
    retrieved = next(entry for entry in audits if entry["action"] == "memory.retrieved")
    updated = next(entry for entry in audits if entry["action"] == "memory.updated")
    assert retrieved["entity_id"] == memory_id
    assert retrieved["detail"] == {"count": 1}
    assert set(updated["detail"]["changed_fields"]) == {"title", "content"}
    assert "private" not in json.dumps([entry["detail"] for entry in audits])


def test_audit_feed_uses_newest_first_covering_index(tmp_path):
    db_path = tmp_path / "audit.db"
    dashboard_store.init_db(db_path)
    with dashboard_store.connect(db_path) as conn:
        plan = conn.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM audit_logs ORDER BY created_at DESC, id DESC LIMIT ?", (50,)
        ).fetchall()
    assert any("idx_audit_logs_created_id" in row["detail"] for row in plan)
