from __future__ import annotations

from nyanya_agent import core
from nyanya_agent import dashboard_store as store


def test_build_messages_includes_agent_memory(tmp_path):
    system_path = tmp_path / "system.md"
    memory_path = tmp_path / "agent_memory.md"
    system_path.write_text("System base", encoding="utf-8")
    memory_path.write_text("Agent knows dashboard basics", encoding="utf-8")

    messages = core.build_messages(
        {
            "system_prompt_path": str(system_path),
            "agent_memory_path": str(memory_path),
        }
    )

    content = messages[0]["content"]
    assert "System base" in content
    assert "# NyaNya Agent Memory" in content
    assert "Agent knows dashboard basics" in content


def test_build_messages_allows_missing_agent_memory(tmp_path):
    system_path = tmp_path / "system.md"
    system_path.write_text("System only", encoding="utf-8")

    messages = core.build_messages(
        {
            "system_prompt_path": str(system_path),
            "agent_memory_path": str(tmp_path / "missing.md"),
        }
    )

    assert messages == [{"role": "system", "content": "System only"}]


def test_dynamic_memory_context_includes_approved_memory(tmp_path, monkeypatch):
    db_path = tmp_path / "dashboard.db"
    monkeypatch.setenv("NYANYA_DASHBOARD_DB_PATH", str(db_path))
    request_id = store.create_agent_request(
        prompt="항상 파일공유 채널 일반 대화는 무시하고 업로드 명령만 처리한다.",
        db_path=db_path,
    )
    store.mark_request_status(request_id, "completed", result_summary="정책 반영", db_path=db_path)
    created = store.extract_memory_candidates_from_requests(limit=10, db_path=db_path)
    store.update_memory(created["memory_ids"][0], status="approved", db_path=db_path)

    context = core.build_dynamic_memory_context("파일공유 채널에서는 어떻게 동작해야 해?", owner_key="discord-user:test")

    assert "Retrieved approved long-term memories" in context
    assert "파일공유" in context
