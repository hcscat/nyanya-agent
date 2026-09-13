from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime, timedelta
import multiprocessing
import threading

import pytest

from nyanya_agent import execution_store as ledger, work_queue
from nyanya_agent.task_outcomes import TaskOutcome
from nyanya_agent.task_service import DurableTaskService


def competing_claim(arguments):
    db, task, worker = arguments
    return work_queue.claim(db, task, worker, "operator")


def test_separate_processes_claim_once(tmp_path):
    db = str(tmp_path / "claims.db")
    task = ledger.create_task(title="one operation", db_path=db)
    with ProcessPoolExecutor(max_workers=3, mp_context=multiprocessing.get_context("spawn")) as pool:
        results = list(pool.map(competing_claim, [(db, task["id"], str(i)) for i in range(6)]))
    assert sum(item is not None for item in results) == 1
    assert len(ledger.get_task(task["id"], db_path=db)["executions"]) == 1


def test_pending_queue_not_limited_by_history(tmp_path):
    db = tmp_path / "history.db"
    task = ledger.create_task(title="old queued", requested_by="operator", db_path=db)
    with ledger.legacy.connect(db) as conn:
        for index in range(600):
            conn.execute("INSERT INTO agent_tasks (id, title, status, created_at, updated_at) "
                         "VALUES (?, 'history', 'completed', '2099', '2099')", (f"history-{index}",))
    assert [item["id"] for item in work_queue.pending_tasks(db, "operator")] == [task["id"]]


def test_expired_worker_cannot_renew_commit_or_be_replayed(tmp_path):
    db = tmp_path / "expiry.db"
    task = ledger.create_task(title="interrupted write", db_path=db)
    claim = work_queue.claim(db, task["id"], "old", "operator")
    with ledger.legacy.connect(db) as conn:
        conn.execute("UPDATE task_claims SET expires_at = '2000-01-01T00:00:00+00:00'")
    assert not work_queue.renew(db, claim)
    with pytest.raises(ValueError, match="Stale"):
        work_queue.finish(db, claim, TaskOutcome("succeeded", "late"))
    assert work_queue.claim(db, task["id"], "replacement", "operator") is None
    assert work_queue.recovery_tasks(db, "replacement")[0]["id"] == task["id"]
    assert ledger.get_task(task["id"], db_path=db)["status"] == "running"


@pytest.mark.parametrize("status,expected", [("awaiting_approval", "awaiting_approval"), ("blocked", "blocked"),
                                            ("timed_out", "failed"), ("failed", "failed"), ("succeeded", "completed")])
def test_typed_outcomes_are_saved_atomically(tmp_path, status, expected):
    db = tmp_path / "results.db"
    task = ledger.create_task(title="outcome", db_path=db)
    claim = work_queue.claim(db, task["id"], "worker", "operator")
    work_queue.finish(db, claim, TaskOutcome(status, "NyaNya Agent 요청 실패: arbitrary model quotation"))
    assert ledger.get_task(task["id"], db_path=db)["status"] == expected
    assert work_queue.result(db, task["id"], "operator")["outcome"] == status
    assert work_queue.result(db, task["id"], "another-user") is None
    if status == "awaiting_approval":
        assert ledger.get_task(task["id"], db_path=db)["approvals"][0]["action"] == "feedback.review"


def test_cancellation_request_does_not_prove_termination(tmp_path):
    db = tmp_path / "cancel.db"
    task = ledger.create_task(title="cancel", db_path=db)
    claim = work_queue.claim(db, task["id"], "worker", "operator")
    ledger.transition_execution(claim["execution_id"], "cancelling", db_path=db)
    work_queue.finish(db, claim, TaskOutcome("succeeded", "remote provider answered"))
    assert ledger.get_task(task["id"], db_path=db)["status"] == "blocked"


def test_delivery_failure_preserves_completed_result(tmp_path):
    db = tmp_path / "delivery.db"
    attempted = threading.Event()
    def send(_text):
        attempted.set()
        raise RuntimeError("not persisted private error")
    service = DurableTaskService(db_path=db)
    task = service.submit(title="result", prompt="inspect", requested_by="operator", owner_key="operator",
                          conversation_key="operator", mode="provider", runner=lambda *_: "retained", responder=send)
    assert attempted.wait(3)
    service.close()
    saved = work_queue.result(db, task["id"], "operator")
    assert saved["response"] == "retained"
    assert saved["delivery_status"] == "uncertain"
    assert saved["delivery_error"] == "RuntimeError"
    assert ledger.get_task(task["id"], db_path=db)["status"] == "completed"


def test_restarted_service_does_not_run_old_callbacks(tmp_path):
    db = tmp_path / "restart.db"
    task = ledger.create_task(title="old", requested_by="operator", db_path=db)
    service = DurableTaskService(db_path=db)
    ran = threading.Event()
    service.submit(title="new", prompt="new", requested_by="operator", owner_key="operator",
                   conversation_key="operator", mode="provider", runner=lambda *_: ran.set(), responder=lambda _: None)
    assert not ran.wait(0.6)
    assert task["id"] in {item["id"] for item in service.recovery_tasks()}
    service.close()


def test_old_attempt_cannot_override_new_attempt_even_with_force(tmp_path):
    db = tmp_path / "stale.db"
    task = ledger.create_task(title="attempts", db_path=db)
    old = ledger.create_execution(task_id=task["id"], adapter_type="test", db_path=db)
    new = ledger.create_execution(task_id=task["id"], adapter_type="test", db_path=db)
    with pytest.raises(ValueError, match="Stale"):
        ledger.transition_execution(old["id"], "succeeded", force=True, db_path=db)
    assert ledger.get_task(task["id"], db_path=db)["current_execution_id"] == new["id"]


def test_lease_fence_survives_release_and_expired_renewal_fails(tmp_path):
    db = tmp_path / "lease.db"
    first = ledger.acquire_writer_lease(resource_key="workspace", owner_id="one", db_path=db)
    ledger.release_writer_lease(resource_key="workspace", owner_id="one", fence_token=first["fence_token"], db_path=db)
    second = ledger.acquire_writer_lease(resource_key="workspace", owner_id="two", db_path=db)
    assert second["fence_token"] > first["fence_token"]
    with ledger.legacy.connect(db) as conn:
        conn.execute("UPDATE writer_leases SET expires_at = ?",
                     ((datetime.now(UTC) - timedelta(seconds=60)).isoformat(),))
    assert ledger.renew_writer_lease(resource_key="workspace", owner_id="two", fence_token=second["fence_token"], db_path=db) is None


def test_schema_two_upgrades_preserving_queued_work(tmp_path, monkeypatch):
    db = tmp_path / "upgrade.db"
    migrations = ledger.MIGRATIONS
    monkeypatch.setattr(ledger, "MIGRATIONS", migrations[:2])
    task = ledger.create_task(title="before upgrade", db_path=db)
    monkeypatch.setattr(ledger, "MIGRATIONS", migrations)
    assert ledger.apply_migrations(db) == 4
    assert ledger.get_task(task["id"], db_path=db)["status"] == "queued"
    assert work_queue.recovery_tasks(db, "new")[0]["id"] == task["id"]


def test_claim_cannot_change_task_owner(tmp_path):
    db = tmp_path / 'owner.db'
    task = ledger.create_task(title='owned', requested_by='operator', db_path=db)
    assert work_queue.claim(db, task['id'], 'worker', 'different-owner') is None
    assert ledger.get_task(task['id'], db_path=db)['status'] == 'queued'


def test_equal_timestamp_queue_preserves_insertion_order(tmp_path):
    db = tmp_path / 'fifo.db'
    ledger.apply_migrations(db)
    with ledger.legacy.connect(db) as conn:
        for task_id in ['z-old', 'a-new']:
            conn.execute("INSERT INTO agent_tasks (id, title, status, requested_by, created_at, updated_at) "
                         "VALUES (?, 'fifo', 'queued', 'operator', '2026-01-01', '2026-01-01')", (task_id,))
    assert [task['id'] for task in work_queue.pending_tasks(db, 'operator')] == ['z-old', 'a-new']
