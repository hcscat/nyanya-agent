from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import threading

from fastapi.testclient import TestClient
import pytest

from nyanya_agent import dashboard_store as store
from nyanya_agent import bridge_policy, conversation_store, database, memory_worker, operation_store, work_memory, work_queue, wiki_store
from nyanya_agent.dashboard_api import create_app
from nyanya_agent.operation_spec import OperationSpec
from nyanya_agent.task_outcomes import TaskOutcome


def test_extract_memory_candidates(tmp_path):
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


def completed_source(tmp_path, monkeypatch, prompt="Remember needleword fixture policy", status="succeeded"):
    root = tmp_path / "workspace"
    root.mkdir(exist_ok=True)
    path = tmp_path / "memory.db"
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(root))
    mapping = tmp_path / "fixture-workspaces.json"
    mapping.write_text(json.dumps({"users": {"discord-user:fixture": {"workspace": str(root)}}}))
    monkeypatch.setattr(bridge_policy, "workspace_config_path", lambda: mapping)
    operation_store.register_worker(path, "fixture-worker")
    request = store.create_agent_request(source="discord", user_id="fixture", prompt=prompt, db_path=path)
    task = operation_store.submit(path, OperationSpec(prompt=prompt, workspace=str(root)),
                                  "discord-user:fixture", "fixture-worker", source_request_id=request,
                                  conversation_key="fixture-channel")
    record = operation_store.claim(path, "fixture-worker")
    record["wiki_candidates"] = [{"topic": "Fixture policy", "summary": "needleword synthetic policy"}]
    work_queue.finish(path, record, TaskOutcome(status, "needleword synthetic result"))
    return path, root, request, task, record


def seed_legacy(path, request, *, owner="discord-user:fixture", memory_id="legacy_fixture"):
    with database.connect(path) as conn:
        conn.execute(
            "INSERT INTO memory_items(id,owner_key,memory_type,title,content,status,source_request_id,created_at,updated_at) "
            "VALUES (?,?,'preference',?,'needleword retained legacy excerpt','approved',?,'2026-01-01','2026-01-01')",
            (memory_id, owner, memory_id, request),
        )
    return memory_id


@pytest.mark.parametrize("refusal", ["기억 저장하지 마", "do not remember or store this"])
def test_optout_source_is_hidden_unreviewable_unrefinable_and_cleared_without_recreation(tmp_path, monkeypatch, refusal):
    path, _, request, _, _ = completed_source(tmp_path, monkeypatch, f"현재 메시지만 보고 답해. {refusal}")
    memory_id = seed_legacy(path, request)
    assert store.list_memories(db_path=path) == []
    assert store.search_approved_memories("needleword", owner_key="discord-user:fixture", db_path=path) == []
    assert store.update_memory(memory_id, status="approved", content="resurrection", db_path=path) is None
    monkeypatch.setenv("NYANYA_MEMORY_WORKER_LLM_REFINEMENT", "true")
    def should_not_refine(*_, **__):
        raise AssertionError("Disallowed legacy source reached refinement")
    monkeypatch.setattr(memory_worker, "refine_memory_with_llm", should_not_refine)
    assert memory_worker.refine_created_memories([memory_id], config={}, db_path=str(path))["skipped"] == 1
    monkeypatch.setenv("NYANYA_DASHBOARD_CONTROL_TOKEN", "fixture-legacy-review-token")
    headers = {"Authorization": "Bearer fixture-legacy-review-token"}
    with TestClient(create_app(path), base_url="http://127.0.0.1") as client:
        assert client.get("/v1/memories", headers=headers).json() == []
        assert client.patch(f"/v1/memories/{memory_id}", headers=headers,
                            json={"status": "approved"}).status_code == 404
    assert store.extract_memory_candidates_from_requests(db_path=path)["created"] == 0
    with database.connect(path) as conn:
        erased = dict(conn.execute("SELECT * FROM memory_items WHERE id=?", (memory_id,)).fetchone())
        assert (erased["status"], erased["title"], erased["content"]) == ("archived", f"Forgotten memory: {memory_id}", "")
    assert store.extract_memory_candidates_from_requests(db_path=path)["created"] == 0
    with database.connect(path) as conn:
        assert dict(conn.execute("SELECT * FROM memory_items WHERE id=?", (memory_id,)).fetchone()) == erased


@pytest.mark.parametrize("entrypoint", ["work", "wiki"])
def test_source_forget_erases_only_same_owned_legacy_source_and_cannot_resurrect(tmp_path, monkeypatch, entrypoint):
    path, root, request, _, record = completed_source(tmp_path, monkeypatch)
    created = store.extract_memory_candidates_from_requests(db_path=path)
    memory_id = created["memory_ids"][0]
    other_request = store.create_agent_request(prompt="Keep unrelated source", db_path=path)
    unrelated = seed_legacy(path, other_request, owner="operator:local", memory_id="legacy_unrelated")
    forged_owner = seed_legacy(path, request, owner="other-owner", memory_id="legacy_other_owner")
    manual = seed_legacy(path, None, owner="operator:local", memory_id="legacy_manual")
    with database.connect(path) as conn:
        protected = {key: dict(conn.execute("SELECT * FROM memory_items WHERE id=?", (key,)).fetchone())
                     for key in [unrelated, forged_owner, manual]}
        ledger_before = {table: [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]
                         for table in ["agent_requests", "agent_tasks", "task_results"]}
    assert not work_memory.forget_record(path, "other-owner", root, record["execution_id"])
    if entrypoint == "work":
        assert work_memory.forget_record(path, "discord-user:fixture", root, record["execution_id"])
    else:
        scope = wiki_store.list_scopes(path)[0]
        note = wiki_store.list_entries(path, scope["owner"], root, scope["session_id"])[0]
        wiki_store.review_entry(path, scope["owner"], root, scope["session_id"],
                                note["id"], "forgotten", note["review_version"])
    assert store.extract_memory_candidates_from_requests(db_path=path)["created"] == 0
    assert store.search_approved_memories("needleword", owner_key="discord-user:fixture", db_path=path) == []
    assert store.update_memory(memory_id, status="approved", content="resurrection", db_path=path) is None
    with database.connect(path) as conn:
        erased = dict(conn.execute("SELECT * FROM memory_items WHERE id=?", (memory_id,)).fetchone())
        assert erased["status"] == "archived" and erased["content"] == ""
        for key, row in protected.items():
            assert dict(conn.execute("SELECT * FROM memory_items WHERE id=?", (key,)).fetchone()) == row
        assert {table: [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]
                for table in ledger_before} == ledger_before
        assert conn.execute("SELECT count(*) FROM memory_items_fts WHERE memory_items_fts MATCH 'needleword' "
                            "AND rowid=(SELECT rowid FROM memory_items WHERE id=?)", (memory_id,)).fetchone()[0] == 0
    assert work_memory.forget_record(path, "discord-user:fixture", root, record["execution_id"])
    with database.connect(path) as conn:
        assert dict(conn.execute("SELECT * FROM memory_items WHERE id=?", (memory_id,)).fetchone()) == erased


@pytest.mark.parametrize("entrypoint", ["work", "wiki"])
def test_source_legacy_forget_and_wiki_work_changes_roll_back_atomically(tmp_path, monkeypatch, entrypoint):
    path, root, request, _, record = completed_source(tmp_path, monkeypatch)
    memory_id = seed_legacy(path, request)
    with database.connect(path) as conn:
        before = {table: [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]
                  for table in ["memory_items", "task_work_records", "wiki_entries"]}
        conn.execute("CREATE TRIGGER fixture_legacy_refusal BEFORE UPDATE ON memory_items "
                     "BEGIN SELECT RAISE(ABORT,'fixture legacy refusal'); END")
    with pytest.raises(sqlite3.IntegrityError, match="legacy refusal"):
        if entrypoint == "work":
            work_memory.forget_record(path, "discord-user:fixture", root, record["execution_id"])
        else:
            scope = wiki_store.list_scopes(path)[0]
            note = wiki_store.list_entries(path, scope["owner"], root, scope["session_id"])[0]
            wiki_store.review_entry(path, scope["owner"], root, scope["session_id"],
                                    note["id"], "forgotten", note["review_version"])
    with database.connect(path) as conn:
        assert {table: [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]
                for table in before} == before
    assert store.list_memories(db_path=path)[0]["id"] == memory_id


@pytest.mark.parametrize("mutation", ["omitted", "stale", "failed"])
def test_legacy_operation_candidates_require_current_screened_success_source(tmp_path, monkeypatch, mutation):
    path, _, request, task, record = completed_source(tmp_path, monkeypatch)
    memory_id = seed_legacy(path, request)
    with database.connect(path) as conn:
        if mutation == "omitted":
            conn.execute("UPDATE task_work_records SET text_status='omitted_sensitive'")
        elif mutation == "stale":
            conn.execute("UPDATE agent_tasks SET current_execution_id=NULL WHERE id=?", (task["id"],))
        else:
            conn.execute("UPDATE executions SET status='failed' WHERE id=?", (record["execution_id"],))
    assert store.list_memories(db_path=path) == []
    assert store.update_memory(memory_id, status="approved", db_path=path) is None
    assert store.extract_memory_candidates_from_requests(db_path=path)["created"] == 0
    with database.connect(path) as conn:
        # Missing proof hides older legacy data; it is not a general cleanup authorization.
        assert conn.execute("SELECT content FROM memory_items WHERE id=?", (memory_id,)).fetchone()[0]


def test_legacy_read_rechecks_current_raw_known_secret_without_marking_retrieved(tmp_path, monkeypatch):
    path, _, request, _, _ = completed_source(tmp_path, monkeypatch)
    memory_id = seed_legacy(path, request)
    secret = 'synthetic-escaped-legacy-"value\\path\nline'
    with database.connect(path) as conn:
        conn.execute("UPDATE memory_items SET content=? WHERE id=?", (secret, memory_id))
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    assert store.list_memories(db_path=path) == []
    assert store.search_approved_memories("synthetic", owner_key="discord-user:fixture", db_path=path) == []
    assert store.update_memory(memory_id, status="approved", db_path=path) is None
    with database.connect(path) as conn:
        assert conn.execute("SELECT retrieval_score,last_used_at FROM memory_items WHERE id=?",
                            (memory_id,)).fetchone()[:] == (0, None)


def test_extraction_writer_fence_prevents_concurrent_forget_from_recreating_legacy_text(tmp_path, monkeypatch):
    path, root, request, _, record = completed_source(tmp_path, monkeypatch)
    original = store._memory_source_state_conn
    started = threading.Event()
    pending = []
    with ThreadPoolExecutor(max_workers=1) as pool:
        def forget():
            started.set()
            return work_memory.forget_record(path, "discord-user:fixture", root, record["execution_id"])

        def pause_after_source_check(conn, request_id, owner_key=None):
            state = original(conn, request_id, owner_key)
            if request_id == request and not pending:
                assert state[1]
                # A second writer cannot enter between eligibility and candidate INSERT.
                with sqlite3.connect(path, timeout=0) as other:
                    with pytest.raises(sqlite3.OperationalError, match="locked"):
                        other.execute("BEGIN IMMEDIATE")
                pending.append(pool.submit(forget))
                assert started.wait(timeout=2)
                assert not pending[0].done()
            return state

        monkeypatch.setattr(store, "_memory_source_state_conn", pause_after_source_check)
        extracted = store.extract_memory_candidates_from_requests(db_path=path)
        assert extracted["created"] == 1 and pending[0].result(timeout=10)
    with database.connect(path) as conn:
        row = conn.execute("SELECT status,title,content FROM memory_items WHERE id=?",
                           (extracted["memory_ids"][0],)).fetchone()
        assert tuple(row) == ("archived", f"Forgotten memory: {extracted['memory_ids'][0]}", "")
    assert store.extract_memory_candidates_from_requests(db_path=path)["created"] == 0


@pytest.mark.parametrize("entrypoint", ["work", "wiki"])
@pytest.mark.parametrize("status", ["pending", "approved", "rejected", "archived"])
def test_same_source_type_multiple_legacy_titles_can_all_be_forgotten(tmp_path, monkeypatch, entrypoint, status):
    path, root, request, _, record = completed_source(tmp_path, monkeypatch)
    ids = [seed_legacy(path, request, memory_id=f"legacy_same_type_{index}") for index in range(2)]
    with database.connect(path) as conn:
        conn.execute("UPDATE memory_items SET status=?", (status,))
    if entrypoint == "work":
        assert work_memory.forget_record(path, "discord-user:fixture", root, record["execution_id"])
    else:
        scope = wiki_store.list_scopes(path)[0]
        note = wiki_store.list_entries(path, scope["owner"], root, scope["session_id"])[0]
        wiki_store.review_entry(path, scope["owner"], root, scope["session_id"],
                                note["id"], "forgotten", note["review_version"])
    with database.connect(path) as conn:
        assert [tuple(row) for row in conn.execute("SELECT id,status,title,content FROM memory_items ORDER BY id")] == [
            (memory_id, "archived", f"Forgotten memory: {memory_id}", "") for memory_id in ids
        ]


@pytest.mark.parametrize("older", [False, True])
@pytest.mark.parametrize("refusal", ["기억 저장하지 마", "do not remember this", ""])
def test_storage_refusal_turn_is_not_future_recent_lexical_or_export_context(tmp_path, monkeypatch, older, refusal):
    prompt = f"현재 메시지만 답해. hiddenneedleword 규칙은 보라색. {refusal}"
    path, root, _, source, _ = completed_source(tmp_path, monkeypatch, prompt)
    for index in range(9 if older else 0):
        operation_store.submit(path, OperationSpec(prompt=f"Ordinary filler {index}", workspace=str(root)),
                               "discord-user:fixture", "fixture-worker", conversation_key="fixture-channel")
        record = operation_store.claim(path, "fixture-worker")
        record["wiki_candidates"] = []
        work_queue.finish(path, record, TaskOutcome("succeeded", "Ordinary response"))
    current = operation_store.submit(path, OperationSpec(prompt="What was hiddenneedleword?", workspace=str(root)),
                                     "discord-user:fixture", "fixture-worker", conversation_key="fixture-channel")
    context = json.loads(conversation_store.worker_context(path, current["id"], "discord-user:fixture", root))
    ids = {turn["task_id"] for turn in context.get("turns", [])}
    assert (source["id"] in ids) is (not bool(refusal))
    export = json.loads(conversation_store.snapshot(path, "discord-user:fixture", "fixture-channel", root))
    if refusal:
        assert source["id"] not in {turn["task_id"] for turn in export.get("turns", [])}
    with database.connect(path) as conn:
        # Privacy controls affect transfer; the canonical workflow request is retained.
        assert conn.execute("SELECT prompt FROM agent_tasks WHERE id=?", (source["id"],)).fetchone()[0] == prompt
