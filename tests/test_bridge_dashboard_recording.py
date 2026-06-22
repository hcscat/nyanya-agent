from __future__ import annotations

import threading
import time

from nyanya_agent import dashboard_store
from nyanya_agent.bridge_store import NyaNyaConversationStore


def test_bridge_submit_records_async_completion(tmp_path, monkeypatch):
    db_path = tmp_path / "dashboard.db"
    monkeypatch.setenv("NYANYA_DASHBOARD_DB_PATH", str(db_path))
    monkeypatch.setenv("NYANYA_TASK_PROGRESS_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("NYANYA_TASK_START_DELAY_SECONDS", "0")

    request_id = dashboard_store.create_agent_request(
        source="discord",
        trigger="prefix",
        command="message",
        mode="auto",
        provider="test-provider",
        model="test-model",
        prompt="do work",
    )

    def fake_answer(self, task, *, auto_route):  # noqa: ANN001
        assert auto_route is True
        return "done"

    monkeypatch.setattr(NyaNyaConversationStore, "_answer_sync", fake_answer)

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
    assert "처리 계획" in ack
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
    assert any(event["event_type"] == "task_completed" for event in request["events"])


def test_bridge_task_status_lists_running_and_queued(monkeypatch):
    monkeypatch.setenv("NYANYA_DASHBOARD_RECORDING_ENABLED", "false")
    monkeypatch.setenv("NYANYA_TASK_PROGRESS_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("NYANYA_TASK_START_DELAY_SECONDS", "0")

    started = threading.Event()
    release = threading.Event()

    def fake_answer(self, task, *, auto_route):  # noqa: ANN001
        started.set()
        release.wait(2)
        return f"done: {task.prompt}"

    monkeypatch.setattr(NyaNyaConversationStore, "_answer_sync", fake_answer)

    responses: list[str] = []
    store = NyaNyaConversationStore({"provider": "test-provider", "model": "test-model"})
    first_ack = store.submit(
        owner_key="discord-user:test",
        conversation_key="discord:test",
        prompt="first long task",
        mode="auto",
        responder=responses.append,
    )
    assert "처리 계획" in first_ack
    assert started.wait(2)

    second_ack = store.submit(
        owner_key="discord-user:test",
        conversation_key="discord:test",
        prompt="second queued task",
        mode="auto",
        responder=responses.append,
    )

    assert "대기열" in second_ack
    status = store.task_status_text("discord-user:test")
    assert "진행 중: 1개" in status
    assert "대기열: 1개" in status
    assert "first long task" in status
    assert "second queued task" in status

    release.set()


def test_bridge_answer_returns_plan_for_unapproved_file_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(tmp_path))
    monkeypatch.setenv("NYANYA_TRUSTED_WORKSPACE_ROOTS", str(tmp_path))
    monkeypatch.setenv("NYANYA_CODEX_AUTO_ENABLED", "false")
    monkeypatch.setenv("NYANYA_MEMORY_RETRIEVAL_ENABLED", "false")
    system_path = tmp_path / "system.md"
    memory_path = tmp_path / "memory.md"
    system_path.write_text("System", encoding="utf-8")
    memory_path.write_text("", encoding="utf-8")
    store = NyaNyaConversationStore(
        {
            "provider": "gemini_cli",
            "model": "test",
            "system_prompt_path": str(system_path),
            "agent_memory_path": str(memory_path),
        }
    )

    answer = store.answer("discord:test", "README.md 파일을 수정해줘")

    assert "바로 실행하지 않고 계획만 제시합니다" in answer
    assert "승인" in answer
