from __future__ import annotations

from nyanya_agent import dashboard_store as store
from nyanya_agent import memory_worker


def test_memory_worker_run_once_creates_pending_candidate(tmp_path, monkeypatch):
    db_path = tmp_path / "dashboard.db"
    monkeypatch.setenv("NYANYA_DASHBOARD_DB_PATH", str(db_path))
    monkeypatch.setenv("NYANYA_MEMORY_WORKER_LLM_REFINEMENT", "false")
    request_id = store.create_agent_request(
        prompt="앞으로 시스템 설정 변경은 바로 실행하지 말고 먼저 계획만 제시해줘.",
        db_path=db_path,
    )
    store.mark_request_status(request_id, "completed", result_summary="안전 정책을 반영했습니다.", db_path=db_path)

    result = memory_worker.run_once(limit=10, db_path=str(db_path))
    memories = store.list_memories(db_path=db_path)

    assert result["created"] == 1
    assert result["refinement"]["skipped"] == 1
    assert len(memories) == 1
    assert memories[0]["status"] == "pending"
    assert memories[0]["sensitivity"] == "normal"
