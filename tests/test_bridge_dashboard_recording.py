from __future__ import annotations

import threading
import time

from nyanya_agent import dashboard_store
from nyanya_agent import execution_store
from nyanya_agent.bridge_store import NyaNyaConversationStore


import json
import pytest


@pytest.fixture(autouse=True)
def registered_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(tmp_path))
    monkeypatch.setenv("NYANYA_DASHBOARD_DB_PATH", str(tmp_path / "dashboard.db"))
    settings = tmp_path / "workspaces.json"
    settings.write_text(
        json.dumps(
            {
                "version": 1,
                "users": {
                    "discord-user:test": {"workspace": str(tmp_path)},
                    "discord:test": {"workspace": str(tmp_path)},
                },
            }
        )
    )
    monkeypatch.setenv("NYANYA_USER_WORKSPACES_FILE", str(settings))


def test_bridge_submit_records_async_completion(tmp_path, monkeypatch, fixture_worker):
    db_path = tmp_path / "dashboard.db"
    monkeypatch.setenv("NYANYA_DASHBOARD_DB_PATH", str(db_path))
    monkeypatch.setenv("NYANYA_TASK_PROGRESS_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("NYANYA_TASK_START_DELAY_SECONDS", "0")

    request_id = dashboard_store.create_agent_request(
        source="discord",
        user_id="test",
        trigger="prefix",
        command="message",
        mode="auto",
        provider="test-provider",
        model="test-model",
        prompt="do work",
    )

    done = threading.Event()
    responses: list[str] = []

    def responder(text):  # noqa: ANN001
        responses.append(text)
        if text == "done":
            done.set()

    store = NyaNyaConversationStore({"provider": "test-provider", "model": "test-model"})
    ack = store.submit(
        owner_key="discord-user:test",
        conversation_key="discord:test",
        prompt="do work",
        mode="auto",
        responder=responder,
        request_id=request_id,
    )

    assert "요청을 접수했습니다" in ack
    assert "목표:" in ack
    assert "단계 일정:" in ack
    assert "목표 변경 규칙:" in ack
    assert "작업목록" in ack
    assert done.wait(2)
    assert responses[-1] == "done"
    deadline = time.monotonic() + 2
    request = dashboard_store.get_request(request_id)
    while request is not None and request["status"] != "completed" and time.monotonic() < deadline:
        time.sleep(0.01)
        request = dashboard_store.get_request(request_id)
    assert request is not None
    assert request["status"] == "completed"
    assert request["result_summary"] == "done"
    task = execution_store.find_task_by_source_request(request_id, db_path=db_path)
    assert task["status"] == "completed"
    store.close()


def test_bridge_task_status_lists_running_and_queued(tmp_path, monkeypatch):
    from nyanya_agent import operation_store
    from nyanya_agent.operation_worker import Worker

    store = NyaNyaConversationStore({})
    worker = Worker(store.operations.path, invoke=lambda *_: "{}")
    store.operations.ensure_worker = lambda: worker.generation
    for prompt in ("first long task", "second queued task"):
        ack = store.submit(
            owner_key="discord-user:test",
            conversation_key="discord:test",
            prompt=prompt,
            mode="auto",
            responder=lambda _: None,
        )
        assert "목표:" in ack
    assert operation_store.claim(store.operations.path, worker.generation)
    status = store.task_status_text("discord-user:test")
    assert "진행 중: 1개" in status and "대기열: 1개" in status
    assert "first long task" in status and "second queued task" in status
    store.close()


def test_bridge_custom_external_operation_is_durable(tmp_path, monkeypatch):
    db_path = tmp_path / "dashboard.db"
    monkeypatch.setenv("NYANYA_DASHBOARD_DB_PATH", str(db_path))
    monkeypatch.setenv("NYANYA_TASK_PROGRESS_INTERVAL_SECONDS", "0")

    done = threading.Event()
    responses: list[str] = []

    store = NyaNyaConversationStore({"provider": "test-provider", "model": "test-model"})
    ack = store.submit(
        owner_key="discord-user:test",
        conversation_key="discord:test",
        prompt="upload test",
        mode="upload",
        responder=lambda text: (responses.append(text), done.set()),
        operation=lambda _task, _cancel_event: "uploaded",
    )

    assert "task_id:" in ack
    assert done.wait(2)
    task = execution_store.list_tasks(db_path=db_path)[0]
    assert task["status"] == "completed"
    assert execution_store.get_task(task["id"], db_path=db_path)["executions"][0]["status"] == "succeeded"


def test_bridge_answer_returns_plan_for_unapproved_file_mutation(tmp_path, monkeypatch, fixture_worker):
    from nyanya_agent.operation_worker import Worker

    (tmp_path / "README.md").write_text("before")
    original = Worker.__init__

    def init(worker, *args, **kwargs):
        original(worker, *args, **kwargs)
        original_invoke = worker.invoke

        def model(profile, prompt, *rest):
            if prompt.startswith("Return only JSON"):
                return original_invoke(profile, prompt, *rest)
            return json.dumps(
                {
                    "summary": "승인 필요",
                    "changes": [{"path": "README.md", "action": "modify", "content": "after", "reason": "requested"}],
                }
            )

        worker.invoke = model

    monkeypatch.setattr(Worker, "__init__", init)
    store = NyaNyaConversationStore({})
    answer = store.answer("discord-user:test", "README.md 파일을 수정해줘")
    assert "approve plan_" in answer and "검토 hash:" in answer
    assert (tmp_path / "README.md").read_text() == "before"
    store.close()
