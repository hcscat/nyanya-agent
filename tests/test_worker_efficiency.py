"""Bounded idle-poll and lookup costs on a migrated ledger."""

from nyanya_agent import database as db, execution_store as ledger, operation_store as store
from nyanya_agent.operation_worker import Worker


NOTICE = (
    "SELECT metadata_json FROM execution_events WHERE event_type='workflow.notice_delivered' "
    "AND json_extract(metadata_json,'$.recipient')=? ORDER BY seq DESC LIMIT 1"
)
SELECTION = (
    "SELECT e.metadata_json FROM request_events e JOIN agent_requests r ON r.id=e.request_id "
    "WHERE e.event_type='control.selection' AND r.mode='control' "
    "AND json_extract(e.metadata_json,'$.actor')=? "
    "AND json_extract(e.metadata_json,'$.conversation')=? "
    "ORDER BY e.rowid DESC LIMIT 1"
)


def _plan(conn, query, args):
    return " ".join(row[3] for row in conn.execute("EXPLAIN QUERY PLAN " + query, args))


def test_v4_database_upgrade_adds_indexed_receipt_and_selection_reads(tmp_path, monkeypatch):
    path = tmp_path / "v4.db"
    # Rewind only the v5 workflow indexes.
    with monkeypatch.context() as patch:
        patch.setattr(ledger, "MIGRATIONS", ledger.MIGRATIONS[:5])
        assert ledger.apply_migrations(path) == 5
    with db.connect(path) as conn:
        conn.execute("DROP INDEX idx_workflow_notice_recipient")
        conn.execute("DROP INDEX idx_control_selection_scope")
        conn.execute("DELETE FROM schema_migrations WHERE version>=5")
        conn.execute("PRAGMA user_version=4")
        before_notice = _plan(conn, NOTICE, ("actor",))
        before_selection = _plan(conn, SELECTION, ("actor", "scope"))
    assert ledger.apply_migrations(path) == ledger.MIGRATIONS[-1][0]
    with db.connect(path) as conn:
        after_notice = _plan(conn, NOTICE, ("actor",))
        after_selection = _plan(conn, SELECTION, ("actor", "scope"))
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == ledger.MIGRATIONS[-1][0]
    assert "idx_workflow_notice_recipient" not in before_notice
    assert "idx_control_selection_scope" not in before_selection
    assert "idx_workflow_notice_recipient" in after_notice
    assert "idx_control_selection_scope" in after_selection


def test_idle_worker_does_not_claim_or_recover_each_tick(tmp_path, monkeypatch):
    worker = Worker(tmp_path / "idle.db", "idle-worker")
    ticks = iter([0.0, 1.0, 2.0])
    waits = iter([False, False, False, True])
    monkeypatch.setattr("nyanya_agent.operation_worker.time.monotonic", lambda: next(ticks))
    monkeypatch.setattr(worker.stop, "wait", lambda _: next(waits))
    calls = []
    real_recover = store.recover

    def recover(path):
        calls.append("recover")
        return real_recover(path)

    monkeypatch.setattr(store, "recover", recover)
    monkeypatch.setattr(store, "claim", lambda *_: (_ for _ in ()).throw(AssertionError("idle claim")))
    worker.run()
    # One startup recovery and one shutdown recovery, versus a recovery write
    # transaction at every idle claim tick in the previous loop.
    assert calls == ["recover", "recover"]
