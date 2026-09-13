from __future__ import annotations

import threading
import time

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
