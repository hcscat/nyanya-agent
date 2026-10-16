from __future__ import annotations

import threading
import time

import pytest

from nyanya_agent import execution_store as ledger
from nyanya_agent.task_service import DurableTaskService
from nyanya_agent.task_outcomes import TaskOutcome


def wait_for(predicate, timeout: float = 3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    return predicate()


def test_service_persists_queue_and_runs_one_task_per_owner(tmp_path):
    db_path = tmp_path / "ledger.db"
    first_started = threading.Event()
    release_first = threading.Event()
    responses: list[str] = []

    def runner(task, cancel_event):  # noqa: ANN001
        if task["prompt"] == "first":
            first_started.set()
            release_first.wait(2)
        if cancel_event.is_set():
            return TaskOutcome("cancelled", "요청이 취소되었습니다.")
        return f"done:{task['prompt']}"

    service = DurableTaskService(db_path=db_path)
    first = service.submit(
        title="First",
        prompt="first",
        requested_by="operator",
        owner_key="terminal:test",
        conversation_key="terminal:test",
        mode="provider",
        workspace_root=str(tmp_path / "workspace"),
        runner=runner,
        responder=responses.append,
    )
    assert first_started.wait(2)

    second = service.submit(
        title="Second",
        prompt="second",
        requested_by="operator",
        owner_key="terminal:test",
        conversation_key="terminal:test",
        mode="provider",
        workspace_root=str(tmp_path / "workspace"),
        runner=runner,
        responder=responses.append,
    )
    assert ledger.get_task(second["id"], db_path=db_path)["status"] == "queued"
    assert ledger.get_task(first["id"], db_path=db_path)["project_id"]

    release_first.set()
    assert wait_for(lambda: len(responses) == 2)
    assert wait_for(lambda: ledger.get_task(second["id"], db_path=db_path)["status"] == "completed")
    assert [item["status"] for item in ledger.list_executions(db_path=db_path)] == ["succeeded", "succeeded"]


def test_service_cancellation_reaches_running_handler_and_queued_task(tmp_path):
    db_path = tmp_path / "ledger.db"
    started = threading.Event()
    responses: list[str] = []

    def runner(_task, cancel_event):  # noqa: ANN001
        started.set()
        while not cancel_event.wait(0.01):
            pass
        return TaskOutcome("cancelled", "요청이 취소되었습니다.")

    service = DurableTaskService(db_path=db_path)
    first = service.submit(
        title="Active",
        prompt="active",
        requested_by="operator",
        owner_key="discord:test",
        conversation_key="discord:test",
        mode="provider",
        runner=runner,
        responder=responses.append,
    )
    assert started.wait(2)
    second = service.submit(
        title="Queued",
        prompt="queued",
        requested_by="operator",
        owner_key="discord:test",
        conversation_key="discord:test",
        mode="provider",
        runner=runner,
        responder=responses.append,
    )

    service.cancel_task(second["id"], actor="operator", reason="remove queued")
    assert ledger.get_task(second["id"], db_path=db_path)["status"] == "cancelled"
    service.cancel_task(first["id"], actor="operator", reason="stop active")
    assert wait_for(lambda: ledger.get_task(first["id"], db_path=db_path)["status"] == "cancelled")
    assert wait_for(lambda: len(responses) == 1)


@pytest.fixture
def cancellable_task(tmp_path):
    service = DurableTaskService(db_path=tmp_path / "cancel.db")
    task = ledger.create_task(title="Cancellation race", status="running", db_path=service.db_path)
    execution = ledger.create_execution(task_id=task["id"], adapter_type="fixture",
                                        status="running", db_path=service.db_path)
    event = threading.Event()
    service._cancel_events[task["id"]] = event
    return service, task, execution, event


def test_cancel_persists_before_signalling(cancellable_task, monkeypatch):
    service, task, execution, event = cancellable_task
    transition = ledger.transition_execution

    def persist(execution_id, status, **kwargs):
        assert not event.is_set(), "handler must not finish before cancellation is durable"
        return transition(execution_id, status, **kwargs)

    monkeypatch.setattr(ledger, "transition_execution", persist)
    service.cancel_task(task["id"])
    assert ledger.get_execution(execution["id"], db_path=service.db_path)["status"] == "cancelling"
    assert event.is_set()


@pytest.mark.parametrize("finish_before_read", [True, False])
def test_cancel_preserves_racing_completion(cancellable_task, monkeypatch, finish_before_read):
    service, task, execution, event = cancellable_task
    transition, get_execution = ledger.transition_execution, ledger.get_execution
    finished = False

    def complete():
        nonlocal finished
        if not finished:
            finished = True
            transition(execution["id"], "succeeded", db_path=service.db_path)

    if finish_before_read:
        def read(execution_id, **kwargs):
            if execution_id == execution["id"]:
                complete()
            return get_execution(execution_id, **kwargs)
        monkeypatch.setattr(ledger, "get_execution", read)
    else:
        def persist(execution_id, status, **kwargs):
            if status == "cancelling":
                complete()
            return transition(execution_id, status, **kwargs)
        monkeypatch.setattr(ledger, "transition_execution", persist)

    result = service.cancel_task(task["id"])
    assert result["status"] == "completed"
    assert ledger.get_task(task["id"], db_path=service.db_path)["status"] == "completed"
    assert get_execution(execution["id"], db_path=service.db_path)["status"] == "succeeded"
    assert not event.is_set()


@pytest.mark.parametrize("rejection", ["unrelated", "completed", "new_attempt"])
def test_cancel_preserves_rejections_without_signalling(cancellable_task, monkeypatch, rejection):
    service, task, execution, event = cancellable_task

    transition = ledger.transition_execution

    def reject(execution_id, status, **kwargs):
        if rejection == "new_attempt":
            ledger.create_execution(task_id=task["id"], adapter_type="fixture",
                                    status="running", db_path=service.db_path)
            return transition(execution_id, status, **kwargs)
        if rejection == "completed":
            transition(execution_id, "succeeded", db_path=service.db_path)
        raise ValueError("fixture cancellation rejection")

    monkeypatch.setattr(ledger, "transition_execution", reject)
    with pytest.raises(ValueError, match="Stale execution" if rejection == "new_attempt" else "fixture cancellation rejection"):
        service.cancel_task(task["id"])
    assert not event.is_set()
    expected = "succeeded" if rejection == "completed" else "running"
    assert ledger.get_execution(execution["id"], db_path=service.db_path)["status"] == expected
    if rejection == "new_attempt":
        current = ledger.get_task(task["id"], db_path=service.db_path)
        assert current["current_execution_id"] != execution["id"]
        assert ledger.get_execution(current["current_execution_id"], db_path=service.db_path)["status"] == "running"
