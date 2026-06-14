from __future__ import annotations

import threading

from nyanya_agent import dashboard_store
from nyanya_agent.bridge_store import NyaNyaConversationStore


def test_bridge_submit_records_async_completion(tmp_path, monkeypatch):
    db_path = tmp_path / "dashboard.db"
    monkeypatch.setenv("NYANYA_DASHBOARD_DB_PATH", str(db_path))

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
    store = NyaNyaConversationStore({"provider": "test-provider", "model": "test-model"})
    ack = store.submit(
        owner_key="discord-user:test",
        conversation_key="discord:test",
        prompt="do work",
        mode="auto",
        responder=lambda text: (responses.append(text), done.set()),
        request_id=request_id,
    )

    assert "요청을 접수했습니다" in ack
    assert done.wait(2)
    assert responses == ["done"]
    request = dashboard_store.get_request(request_id)
    assert request is not None
    assert request["status"] == "completed"
    assert request["result_summary"] == "done"
    assert any(event["event_type"] == "task_completed" for event in request["events"])
