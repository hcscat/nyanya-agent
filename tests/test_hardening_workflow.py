"""Regression checks for delivery ownership and review lifecycle consistency."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import threading

from nyanya_agent import database as db, execution_store as ledger
from nyanya_agent import operation_store as store, reviewed_changes as files
from nyanya_agent import work_queue
from nyanya_agent import workflow_notifications as notices
from nyanya_agent.control_intents import classify
from nyanya_agent.discord_bridge import format_saved_result
from nyanya_agent.operation_service import OperationService
from nyanya_agent.operation_spec import OperationSpec
from nyanya_agent.task_outcomes import TaskOutcome


def ready_task(tmp_path, monkeypatch, *, outcome="succeeded"):
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(root))
    path = tmp_path / "state.db"
    store.register_worker(path, "worker")
    task = store.submit(path, OperationSpec(prompt="inspect", workspace=str(root)), "operator", "worker")
    record = store.claim(path, "worker")
    store.finish(path, record, TaskOutcome(outcome, "saved result"))
    return path, root, task, record


def test_concurrent_watchers_send_one_attempt_once(tmp_path, monkeypatch):
    path, _, task, record = ready_task(tmp_path, monkeypatch)
    service = OperationService(path, generation="worker")
    calls = []
    lock = threading.Lock()

    def responder(value):
        with lock:
            calls.append(value)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: service.deliver(task["id"], "operator", responder, 1), range(8)))
    assert calls == ["saved result"]
    assert store.delivery_state(path, task["id"], "operator")["delivery_status"] == "delivered"
    service.deliver(task["id"], "operator", responder, 1)
    assert len(calls) == 1
    assert record["execution_id"] == store.delivery_state(path, task["id"], "operator")["execution_id"]


def test_legacy_delivery_claim_is_atomic_and_fences_stale_result(tmp_path, monkeypatch):
    path, _, task, record = ready_task(tmp_path, monkeypatch)
    with ThreadPoolExecutor(max_workers=6) as pool:
        claimed = list(pool.map(
            lambda _: work_queue.claim_delivery(path, task["id"], "operator", record["execution_id"]),
            range(6),
        ))
    assert claimed.count(True) == 1
    work_queue.record_delivery(path, record["execution_id"], delivered=False, error="ConnectionError")
    assert not work_queue.claim_delivery(path, task["id"], "operator", record["execution_id"])
    assert work_queue.result(path, task["id"], "operator")["delivery_status"] == "uncertain"


def test_failed_or_interrupted_send_remains_held(tmp_path, monkeypatch):
    path, _, task, record = ready_task(tmp_path, monkeypatch)
    service = OperationService(path, generation="worker")
    calls = []

    def uncertain(_):
        calls.append("attempted")
        raise ConnectionError("receipt unknown")

    service.deliver(task["id"], "operator", uncertain, 1)
    assert calls == ["attempted"]
    assert store.delivery_state(path, task["id"], "operator")["delivery_status"] == "uncertain"
    assert "자동 재전송하지 않음" in store.explain(path, task["id"], "operator")
    assert "결과 전달 확인 필요" in store.list_text(path, "operator")
    assert work_queue.result(path, task["id"], "operator")["delivery_status"] == "uncertain"
    service.deliver(task["id"], "operator", lambda _: calls.append("replayed"), 1)
    assert calls == ["attempted"]
    with db.connect(path) as conn:
        conn.execute("UPDATE task_results SET delivery_status='pending' WHERE execution_id=?", (record["execution_id"],))
    assert store.claim_delivery(path, task["id"], "operator", record["execution_id"], 1)
    # A controller restart cannot reclaim an in-progress send with unknown outcome.
    restarted = OperationService(path, generation="worker")
    restarted.deliver(task["id"], "operator", lambda _: calls.append("replayed"), 1)
    assert calls == ["attempted"]
    assert store.delivery_state(path, task["id"], "operator")["delivery_status"] == "sending"
    assert "자동 재전송하지 않음" in store.explain(path, task["id"], "operator")
    assert "결과 전달 확인 필요" in store.list_text(path, "operator")


def test_old_watcher_cannot_send_new_attempt(tmp_path, monkeypatch):
    path, _, task, first = ready_task(tmp_path, monkeypatch, outcome="failed")
    service = OperationService(path, generation="worker")
    store.resume(path, task["id"], "operator", "worker")
    second = store.claim(path, "worker")
    store.finish(path, second, TaskOutcome("succeeded", "retry result"))
    calls = []
    service.deliver(task["id"], "operator", calls.append, 1)
    restarted = OperationService(path, generation="worker")
    restarted.deliver(task["id"], "operator", calls.append, 2)
    assert calls == ["retry result"]
    with db.connect(path) as conn:
        assert conn.execute("SELECT delivery_status FROM task_results WHERE execution_id=?",
                            (first["execution_id"],)).fetchone()[0] == "pending"


def test_launch_failure_has_saved_result_and_one_callback(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(root))
    service = OperationService(tmp_path / "state.db")
    service.ensure_worker = lambda: (_ for _ in ()).throw(RuntimeError("fixture failure"))
    replies = []
    sent = threading.Event()

    def responder(value):
        replies.append(value)
        sent.set()

    task = service.submit("retained request", root, "operator", responder=responder)
    assert task["status"] == "blocked"
    assert sent.wait(2)
    service.watchers[0].join(timeout=2)
    saved = work_queue.result(service.path, task["id"], "operator")
    assert saved["outcome"] == "blocked"
    assert "retained request" in saved["response"]
    assert saved["delivery_status"] == "delivered"
    assert service.wait(task["id"], "operator", 1).status == "blocked"
    service.deliver(task["id"], "operator", responder, 0)
    assert len(replies) == 1
    service.close()


def test_discord_result_text_reports_ambiguous_delivery():
    saved = {"created_at": "fixture-time", "outcome": "succeeded", "response": "saved result",
             "delivery_status": "sending"}
    text = format_saved_result(saved, {"status": "completed"})
    assert "결과 전달 상태: sending" in text
    assert "자동 재전송하지 않음" in text
    saved["delivery_status"] = "delivered"
    assert "자동 재전송하지 않음" not in format_saved_result(saved, {"status": "completed"})


def test_owner_acknowledges_only_current_ambiguous_delivery(tmp_path, monkeypatch):
    path, _, task, record = ready_task(tmp_path, monkeypatch)
    service = OperationService(path, generation="worker")
    assert classify(f"ack-delivery {task['id']}").kind == "delivery_ack"
    assert classify(f"ack-delivery {task['id']} extra").kind == "clarify"
    assert classify(f"'ack-delivery {task['id']}'").kind == "clarify"
    assert store.claim_delivery(path, task["id"], "operator", record["execution_id"], 1)
    assert notices.prepare(path, "operator") is not None
    before = ledger.get_task(task["id"], db_path=path)["status"]
    try:
        service.handle_intent(f"ack-delivery {task['id']}", "other-owner")
    except PermissionError:
        pass
    else:
        raise AssertionError("another owner acknowledged this result")
    reply = service.handle_intent(f"ack-delivery {task['id']}", "operator")
    assert "전달 성공을 확인" in reply and "재전송" in reply
    assert service.handle_intent(f"ack-delivery {task['id']}", "operator") == reply
    assert work_queue.result(path, task["id"], "operator")["delivery_status"] == "acknowledged"
    assert ledger.get_task(task["id"], db_path=path)["status"] == before == "completed"
    assert notices.prepare(path, "operator") is None
    assert "현재 확인할 미완료 작업이 없습니다" in store.list_text(path, "operator")
    assert "전달 성공으로 확인한 것은 아님" in store.explain(path, task["id"], "operator")
    assert "전달 성공으로 확인한 것은 아님" in format_saved_result(
        work_queue.result(path, task["id"], "operator"), {"status": before})
    # A callback finishing after the owner's acknowledgment cannot overwrite it.
    store.settle_delivery(path, record["execution_id"], delivered=True)
    assert work_queue.result(path, task["id"], "operator")["delivery_status"] == "acknowledged"
    events = [event for event in ledger.list_events(db_path=path)
              if event["event_type"] == "workflow.delivery_acknowledged"]
    assert len(events) == 1


def test_delivery_ack_rejects_pending_or_stale_attempt(tmp_path, monkeypatch):
    path, _, task, first = ready_task(tmp_path, monkeypatch, outcome="failed")
    service = OperationService(path, generation="worker")
    from nyanya_agent.task_outcomes import SafeOperationError
    assert store.claim_delivery(path, task["id"], "operator", first["execution_id"], 1)
    store.settle_delivery(path, first["execution_id"], delivered=False, error="ConnectionError")
    try:
        store.resume(path, task["id"], "operator", "worker")
    except SafeOperationError:
        pass
    else:
        raise AssertionError("resume hid an ambiguous prior send")
    service.handle_intent(f"ack-delivery {task['id']}", "operator")
    store.resume(path, task["id"], "operator", "worker")
    second = store.claim(path, "worker")
    store.finish(path, second, TaskOutcome("succeeded", "new result"))
    assert first["execution_id"] != second["execution_id"]
    assert "의도를 확정" in service.handle_intent(f"ack-delivery {task['id']} extra", "operator")
    try:
        service.handle_intent(f"ack-delivery {task['id']}", "operator")
    except SafeOperationError:
        pass
    else:
        raise AssertionError("pending current result was acknowledged")
    assert work_queue.result(path, task["id"], "operator")["delivery_status"] == "pending"


def test_work_request_with_timeout_code_terms_keeps_control_safety():
    assert classify("Please fix timeout logic in the worker").kind == "work_request"
    assert classify("워커의 타임아웃 로직 수정해줘").kind == "work_request"
    assert classify("현재 실행 제한시간은?").kind == "runtime_status"
    assert classify('"fix timeout logic"').kind == "clarify"
    assert classify("취소하지 마").kind == "clarify"
    assert classify("cancel task_x extra").kind == "clarify"


def test_expired_plan_closes_review_attempt_even_for_terminal_parent(tmp_path, monkeypatch):
    path, root, task, _ = ready_task(tmp_path, monkeypatch, outcome="failed")
    # Build a real approval wait, then emulate the historical terminal-parent mismatch.
    other = store.submit(path, OperationSpec(prompt="review", workspace=str(root)), "operator", "worker")
    record = store.claim(path, "worker")
    (root / "note.txt").write_text("before")
    plan = files.propose(path, other["id"], "operator", root,
                         [{"path": "note.txt", "action": "modify", "content": "after", "reason": "review"}],
                         files.snapshot(root))
    store.finish(path, record, TaskOutcome("awaiting_approval", "review"))
    with db.connect(path) as conn:
        conn.execute("UPDATE agent_tasks SET status='cancelled' WHERE id=?", (other["id"],))
        conn.execute("UPDATE change_plans SET expires_at=? WHERE id=?",
                     ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), plan["id"]))
    assert files.settle_expired(path) == 1
    assert ledger.get_task(other["id"], db_path=path)["status"] == "cancelled"
    assert ledger.get_execution(record["execution_id"], db_path=path)["status"] == "cancelled"
    assert files.settle_expired(path) == 0
    assert task["id"] != other["id"]
