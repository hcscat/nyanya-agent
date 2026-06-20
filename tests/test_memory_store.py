from __future__ import annotations

from nyanya_agent import dashboard_store as store


def test_extract_memory_candidates_and_graph(tmp_path):
    db_path = tmp_path / "dashboard.db"
    request_id = store.create_agent_request(
        source="discord",
        trigger="prefix",
        command="message",
        mode="auto",
        provider="gemini_cli",
        model="gemini-cli-default",
        prompt="앞으로 작업 결과는 md, html 보고서로 정리하고 파일공유 채널에 올려줘.",
        db_path=db_path,
    )
    store.mark_request_status(
        request_id,
        "completed",
        result_summary="HTML 보고서를 생성하고 파일공유 채널에 업로드했습니다.",
        db_path=db_path,
    )

    result = store.extract_memory_candidates_from_requests(limit=10, db_path=db_path)

    assert result["created"] == 1
    memories = store.list_memories(db_path=db_path)
    assert len(memories) == 1
    assert memories[0]["memory_type"] in {"report_style", "safety_rule"}
    assert memories[0]["status"] == "pending"
    assert memories[0]["importance"] >= 40

    graph = store.memory_graph(db_path=db_path)
    assert graph["stats"]["memories"] == 1
    memory_nodes = [node for node in graph["nodes"] if node["kind"] == "memory"]
    assert memory_nodes
    assert len(memory_nodes[0]["label"]) < len(memories[0]["title"])
    assert any(edge["label"] == "contains" for edge in graph["edges"])


def test_update_memory_status(tmp_path):
    db_path = tmp_path / "dashboard.db"
    request_id = store.create_agent_request(prompt="중요하다. 앞으로 짧게 보고해줘.", db_path=db_path)
    store.mark_request_status(request_id, "completed", result_summary="알겠습니다.", db_path=db_path)
    created = store.extract_memory_candidates_from_requests(limit=10, db_path=db_path)

    memory = store.update_memory(created["memory_ids"][0], status="approved", importance=90, db_path=db_path)

    assert memory is not None
    assert memory["status"] == "approved"
    assert memory["importance"] == 90


def test_search_approved_memories_returns_only_approved(tmp_path):
    db_path = tmp_path / "dashboard.db"
    request_id = store.create_agent_request(
        prompt="파일공유 채널에서는 일반 대화에 답하지 말고 파일 업로드만 처리해야 한다.",
        db_path=db_path,
    )
    store.mark_request_status(request_id, "completed", result_summary="파일공유 정책을 반영했습니다.", db_path=db_path)
    created = store.extract_memory_candidates_from_requests(limit=10, db_path=db_path)
    pending = store.search_approved_memories("파일공유 파일 업로드 정책", db_path=db_path)
    assert pending == []

    store.update_memory(created["memory_ids"][0], status="approved", db_path=db_path)
    approved = store.search_approved_memories("파일공유 파일 업로드 정책", db_path=db_path)

    assert len(approved) == 1
    assert approved[0]["status"] == "approved"
    assert "파일공유" in store.format_memory_context(approved)


def test_tech_stack_graph_extracts_known_technologies(tmp_path):
    db_path = tmp_path / "dashboard.db"
    request_id = store.create_agent_request(
        prompt="FastAPI, SQLite, Cytoscape.js 기반으로 메모리 마인드맵을 구현해줘.",
        db_path=db_path,
    )
    store.mark_request_status(request_id, "completed", result_summary="FastAPI API와 SQLite 저장소를 추가했습니다.", db_path=db_path)
    store.extract_memory_candidates_from_requests(limit=10, db_path=db_path)

    graph = store.tech_stack_graph(db_path=db_path)
    labels = {node["label"] for node in graph["nodes"]}

    assert "관심사 기술스택" in labels
    assert "FastAPI" in labels
    assert "SQLite" in labels
    assert "Cytoscape.js" in labels
    assert graph["stats"]["technologies"] >= 3
