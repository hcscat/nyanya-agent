"""Successful attempt evidence remains scoped, bounded, and non-authoritative."""

from datetime import UTC, datetime, timedelta
import json

import pytest

from nyanya_agent import conversation_store, database as db, execution_store as ledger
from nyanya_agent import operation_store as store, reviewed_changes, work_memory as memory, work_queue, wiki_store
from nyanya_agent.operation_spec import OperationSpec
from nyanya_agent.operation_worker import ASSESSMENT, HISTORY_LABEL, RESPONSE, Worker, _with_history
from nyanya_agent.task_outcomes import SafeOperationError, TaskOutcome


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    path = tmp_path / "memory.db"
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(root))
    monkeypatch.setenv("NYANYA_WORK_MEMORY_ENABLED", "true")
    worker = "synthetic-worker"
    store.register_worker(path, worker)
    return path, root, worker


def add(setup, prompt="cache inspection", owner="operator", key="conversation-one", project_id=None):
    path, root, worker = setup
    return store.submit(path, OperationSpec(prompt=prompt, workspace=str(root)), owner, worker,
                        conversation_key=key, project_id=project_id)


def complete(setup, answer="cache inspected", status="succeeded", kind="answer"):
    path, _, worker = setup
    record = store.claim(path, worker)
    record["reply_kind"] = kind
    work_queue.finish(path, record, TaskOutcome(status, answer))
    return record


def rows(setup, **kwargs):
    return memory.list_records(setup[0], "operator", setup[1], **kwargs)


def test_fenced_success_has_one_record_and_live_delivery_state(setup):
    task = add(setup)
    record = complete(setup)
    item = rows(setup)[0]
    assert item["task_id"] == item["source_task_id"] == task["id"]
    assert item["execution_id"] == record["execution_id"]
    assert item["provenance_kind"] == "model_result"
    assert item["current_task_status"] == "completed"
    assert item["delivery_status"] == "pending"
    with db.connect(setup[0]) as conn:
        memory.complete_conn(conn, record, TaskOutcome("succeeded", "changed duplicate"))
    assert len(rows(setup)) == 1
    assert rows(setup)[0]["result_summary"] == "cache inspected"
    assert store.claim_delivery(setup[0], task["id"], "operator", record["execution_id"], 1)
    store.settle_delivery(setup[0], record["execution_id"], delivered=False, error="synthetic-send")
    assert rows(setup)[0]["delivery_status"] == "uncertain"


@pytest.mark.parametrize("status", ["failed", "cancelled", "blocked", "timed_out"])
def test_non_success_is_not_work_memory(setup, status):
    add(setup)
    complete(setup, status=status)
    assert rows(setup) == []


def test_question_is_visible_but_never_retrieved_as_completed_knowledge(setup):
    add(setup)
    complete(setup, "Which cache?", kind="question")
    assert rows(setup)[0]["reply_kind"] == "question"
    assert memory.search_records(setup[0], "operator", setup[1], "cache") == []


def test_stale_claim_and_memory_error_rollback_the_whole_result(setup, monkeypatch):
    path, _, worker = setup
    task = add(setup)
    record = store.claim(path, worker)
    with db.connect(path) as conn:
        conn.execute("UPDATE task_claims SET expires_at='2000'")
    with pytest.raises(ValueError, match="Stale"):
        work_queue.finish(path, record, TaskOutcome("succeeded", "late answer"))
    assert rows(setup) == []
    with db.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM task_results").fetchone()[0] == 0
        conn.execute("UPDATE task_claims SET expires_at=?", ((datetime.now(UTC) + timedelta(minutes=1)).isoformat(),))
    def reject(*_):
        raise ValueError("synthetic record failure")
    monkeypatch.setattr(memory, "complete_conn", reject)
    with pytest.raises(ValueError, match="synthetic"):
        work_queue.finish(path, record, TaskOutcome("succeeded", "not committed"))
    assert ledger.get_task(task["id"], db_path=path)["status"] == "running"
    with db.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM task_results").fetchone()[0] == 0
        assert conn.execute("SELECT released FROM task_claims").fetchone()[0] == 0


def test_cancelling_success_is_held_without_a_success_memory(setup):
    path, _, worker = setup
    task = add(setup)
    record = store.claim(path, worker)
    store.cancel(path, task["id"], "operator")
    work_queue.finish(path, record, TaskOutcome("succeeded", "late model conclusion"))
    assert ledger.get_task(task["id"], db_path=path)["status"] == "blocked"
    assert rows(setup) == []


def test_sensitive_and_oversized_sources_leave_no_searchable_narrative(setup, monkeypatch):
    add(setup, "cache password=" + "synthetic-private-value")
    complete(setup)
    add(setup, "cache inspection")
    complete(setup, "unmarked-synthetic-provider-value")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-provider-value")
    # Existing records are screened again at retrieval with current known secrets.
    assert len(rows(setup)) == 1
    monkeypatch.delenv("OPENAI_API_KEY")
    add(setup, "cache oversized answer")
    complete(setup, "한" * 40_000)
    items = rows(setup)
    assert {item["text_status"] for item in items} == {"screened", "omitted_sensitive", "omitted_size"}
    omitted = [item for item in items if item["text_status"] != "screened"]
    assert all(not item["request_summary"] and not item["result_summary"] for item in omitted)
    assert len(memory.search_records(setup[0], "operator", setup[1], "cache")) == 1


def test_utf8_storage_query_and_output_bounds(setup):
    for index in range(4):
        add(setup, "cache " + "요" * 800 + str(index))
        complete(setup, "결" * 1500)
    items = rows(setup)
    assert all(len(item["request_summary"].encode()) <= memory.MAX_REQUEST_BYTES for item in items)
    assert all(len(item["result_summary"].encode()) <= memory.MAX_RESULT_BYTES for item in items)
    bounded = rows(setup, max_bytes=4500, limit=2)
    assert len(bounded) <= 2 and len(memory._json(bounded).encode()) <= 4500
    with pytest.raises(SafeOperationError, match="query"):
        memory.search_records(setup[0], "operator", setup[1], "요" * 1000)
    with pytest.raises(SafeOperationError, match="count"):
        rows(setup, limit=memory.MAX_RECORDS + 1)


def test_exact_owner_workspace_project_scope_and_registration_refresh(setup, tmp_path, monkeypatch):
    path, root, worker = setup
    project = ledger.create_project(name="synthetic project", owner="operator", workspace_root=str(root), db_path=path)
    add(setup, project_id=project["id"])
    complete(setup)
    add(setup)
    complete(setup)
    assert len(rows(setup)) == len(rows(setup, project_id=project["id"])) == 1
    assert memory.list_records(path, "other-owner", root) == []
    with pytest.raises(PermissionError, match="project"):
        memory.list_records(path, "other-owner", root, project_id=project["id"])
    other_root = tmp_path / "other-root"
    other_root.mkdir()
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", f"{root},{other_root}")
    assert memory.list_records(path, "operator", other_root) == []
    task = add(setup, key="another-channel")
    with pytest.raises(PermissionError, match="current task"):
        memory.worker_context(path, task["id"], "other-owner", root, "cache")
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(other_root))
    with pytest.raises(SafeOperationError, match="allowed"):
        rows(setup)
    assert memory.list_scopes(path)[0]["record_count"] == 1


def test_apply_records_parent_request_and_verified_journal_without_promoting_preview(setup):
    path, root, worker = setup
    (root / "note.txt").write_text("before")
    parent = add(setup, "modify note.txt cache explanation")
    record = store.claim(path, worker)
    plan = reviewed_changes.propose(path, parent["id"], "operator", root,
        [dict(path="note.txt", action="modify", content="after", reason="requested change")],
        reviewed_changes.snapshot(root))
    work_queue.finish(path, record, TaskOutcome("awaiting_approval", "model proposed a change"))
    assert rows(setup) == [] and (root / "note.txt").read_text() == "before"
    reviewed_changes.decide(path, plan["id"], "operator", plan["plan_hash"])
    child = store.submit(path, OperationSpec(kind="apply", workspace=str(root), plan_id=plan["id"]), "operator", worker)
    claim = store.claim(path, worker)
    answer = reviewed_changes.apply(path, plan["id"], "operator", record=claim)
    work_queue.finish(path, claim, TaskOutcome("succeeded", answer))
    item = rows(setup)[0]
    assert item["task_id"] == child["id"] and item["source_task_id"] == parent["id"]
    assert item["provenance_kind"] == "reviewed_apply" and item["current_plan_status"] == "applied"
    assert item["evidence"]["plan_hash"] == plan["plan_hash"]
    assert item["evidence"]["applied_journal_entries"] == 1
    assert item["request_summary"] == "modify note.txt cache explanation"
    assert "after" not in json.dumps(item)
    assert ledger.get_task(parent["id"], db_path=path)["status"] == "completed"
    assert work_queue.result(path, parent["id"], "operator")["outcome"] == "awaiting_approval"


def test_apply_inherits_verified_parent_project_and_rechecks_current_scope(setup):
    path, root, worker = setup
    project = ledger.create_project(name="synthetic project", owner="operator", workspace_root=str(root), db_path=path)
    (root / "note.txt").write_text("before")
    parent = add(setup, "modify note.txt cache", project_id=project["id"])
    claim = store.claim(path, worker)
    plan = reviewed_changes.propose(path, parent["id"], "operator", root,
        [dict(path="note.txt", action="modify", content="after", reason="requested")], reviewed_changes.snapshot(root))
    work_queue.finish(path, claim, TaskOutcome("awaiting_approval", "proposed"))
    reviewed_changes.decide(path, plan["id"], "operator", plan["plan_hash"])
    child = store.submit(path, OperationSpec(kind="apply", workspace=str(root), plan_id=plan["id"]), "operator", worker)
    claim = store.claim(path, worker)
    reviewed_changes.apply(path, plan["id"], "operator", record=claim)
    work_queue.finish(path, claim, TaskOutcome("succeeded", "apply completed"))
    assert ledger.get_task(child["id"], db_path=path)["project_id"] is None
    assert rows(setup) == []
    assert rows(setup, project_id=project["id"])[0]["source_task_id"] == parent["id"]
    with db.connect(path) as conn:
        conn.execute("UPDATE agent_tasks SET project_id=NULL WHERE id=?", (parent["id"],))
    assert rows(setup, project_id=project["id"]) == []
    with db.connect(path) as conn:
        conn.execute("UPDATE agent_tasks SET project_id=? WHERE id=?", (project["id"], parent["id"]))
        conn.execute("UPDATE change_journal SET state='prepared' WHERE plan_id=?", (plan["id"],))
    assert rows(setup, project_id=project["id"]) == []


def test_retry_records_only_new_success_and_rejects_late_old_attempt(setup):
    path, _, worker = setup
    task = add(setup)
    failed = complete(setup, "clean failure", status="failed")
    store.resume(path, task["id"], "operator", worker)
    succeeded = complete(setup)
    assert rows(setup)[0]["execution_id"] == succeeded["execution_id"] != failed["execution_id"]
    with pytest.raises(ValueError, match="Stale"):
        work_queue.finish(path, failed, TaskOutcome("succeeded", "late old result"))
    assert len(rows(setup)) == 1


def test_old_same_generation_work_is_reused_but_history_duplicates_and_reset_are_excluded(setup):
    path, root, _ = setup
    tasks = []
    for index in range(10):
        tasks.append(add(setup, f"cache review {index}"))
        complete(setup, f"cache conclusion {index}")
    current = add(setup, "cache review again")
    history = json.loads(conversation_store.worker_context(path, current["id"], "operator", root))
    duplicates = [turn["task_id"] for turn in history["turns"]]
    value = json.loads(memory.worker_context(path, current["id"], "operator", root, "cache",
                                           exclude_task_ids=duplicates))
    assert value == {}
    assert set(duplicates) == {task["id"] for task in tasks}
    conversation_store.reset(path, "operator", "conversation-one", root)
    assert memory.worker_context(path, current["id"], "operator", root, "cache") == "{}"
    fresh = add(setup, "cache after reset")
    assert memory.worker_context(path, fresh["id"], "operator", root, "cache") == "{}"
    independent = add(setup, "cache other conversation", key="conversation-two")
    assert memory.worker_context(path, independent["id"], "operator", root, "cache") == "{}"


def test_idle_keeps_same_channel_history_and_work_available_next_day(setup):
    path, root, _ = setup
    previous = add(setup, "cache inspection before idle")
    complete(setup, "cache conclusion before idle")
    expired = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
    with db.connect(path) as conn:
        conn.execute("UPDATE conversation_turns SET created_at=?", (expired,))
        conn.execute("UPDATE conversation_sessions SET updated_at=?", (expired,))
    current = add(setup, "cache investigation next day")
    assert previous["id"] in conversation_store.worker_context(path, current["id"], "operator", root)
    value = json.loads(memory.worker_context(path, current["id"], "operator", root, "cache"))
    assert [item["task_id"] for item in value["records"]] == [previous["id"]]
    with db.connect(path) as conn:
        assert tuple(conn.execute("SELECT generation,memory_reset_generation FROM conversation_sessions").fetchone()) == (1, 0)


def test_explicit_reset_excludes_earlier_work_even_after_another_idle_rollover(setup):
    path, root, _ = setup
    previous = add(setup, "cache investigation before reset")
    complete(setup, "cache conclusion before reset")
    assert conversation_store.reset(path, "operator", "conversation-one", root) == 2
    with db.connect(path) as conn:
        expired = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
        conn.execute("UPDATE conversation_sessions SET updated_at=?", (expired,))
    current = add(setup, "cache investigation after reset and idle")
    assert memory.worker_context(path, current["id"], "operator", root, "cache") == "{}"
    with db.connect(path) as conn:
        assert tuple(conn.execute("SELECT generation,memory_reset_generation FROM conversation_sessions").fetchone()) == (2, 2)
    assert rows(setup)[0]["task_id"] == previous["id"]
    assert ledger.get_task(previous["id"], db_path=path)["status"] == "completed"


@pytest.mark.parametrize("prompt", ["이전 기억 없이 cache 설명", "기억을 쓰지 말고 cache 설명", "이번 메시지만 보고 cache 설명",
                                  "Don't use memory. Explain cache", "Use only this message: cache", "아래 코드만 분석: cache"])
def test_explicit_input_boundary_excludes_work_memory(setup, prompt):
    add(setup)
    complete(setup)
    task = add(setup, prompt, key="another-channel")
    assert memory.worker_context(setup[0], task["id"], "operator", setup[1], prompt) == "{}"


@pytest.mark.parametrize("prompt", ["이번 메시지만 보고 cache 설명", "이전 대화 무시하고 cache 설명",
                                  "Ignore history. Explain cache", "Use only this message: cache"])
def test_explicit_no_history_input_skips_both_context_sources(setup, monkeypatch, prompt):
    path, _, worker = setup
    add(setup)
    complete(setup)
    add(setup, prompt)
    record = store.claim(path, worker)
    def deny(*_, **__):
        raise AssertionError("History must not be queried for explicit current-only input")
    monkeypatch.setattr(conversation_store, "worker_context", deny)
    for contract in (ASSESSMENT, RESPONSE):
        value = _with_history(path, record, contract + "\nCURRENT request:\n" + prompt)
        assert json.loads(value.split(HISTORY_LABEL)[1]) == {}
        assert memory.CONTEXT_LABEL not in value
    assert not memory.history_input_disabled("Do not read files. Explain cache")


def test_forget_expiry_and_storage_opt_out_preserve_task_evidence(setup, monkeypatch):
    task = add(setup)
    record = complete(setup)
    assert not memory.forget_record(setup[0], "other-owner", setup[1], record["execution_id"])
    assert memory.forget_record(setup[0], "operator", setup[1], record["execution_id"])
    with db.connect(setup[0]) as conn:
        memory.complete_conn(conn, record, TaskOutcome("succeeded", "do not recreate"))
        item = conn.execute("SELECT status,request_summary,result_summary FROM task_work_records").fetchone()
        assert tuple(item) == ("forgotten", "", "")
    assert rows(setup) == []
    assert ledger.get_task(task["id"], db_path=setup[0])["status"] == "completed"
    assert work_queue.result(setup[0], task["id"], "operator")["response"] == "cache inspected"
    add(setup, "cache 설명, 저장하지 마")
    complete(setup)
    assert rows(setup) == []
    add(setup)
    complete(setup)
    with db.connect(setup[0]) as conn:
        conn.execute("UPDATE task_work_records SET expires_at='2000'")
    assert rows(setup) == []
    monkeypatch.setenv("NYANYA_WORK_MEMORY_ENABLED", "false")
    add(setup)
    complete(setup)
    with db.connect(setup[0]) as conn:
        assert conn.execute("SELECT count(*) FROM task_work_records").fetchone()[0] == 2


def test_worker_keeps_snapshot_history_budget_and_excludes_memory_from_assessment(setup, monkeypatch):
    path, root, worker = setup
    add(setup)
    complete(setup)
    current = add(setup, "cache review again")
    monkeypatch.setattr(conversation_store, "worker_context", lambda *_, **__: "{}")
    monkeypatch.setattr(wiki_store, "worker_context", lambda *_, **__: "{}")
    record = store.claim(path, worker)
    current_text = RESPONSE + "\nCURRENT request:\ncache review again\nCURRENT request-scoped snapshot (whole files only):\n{}"
    prompt = _with_history(path, record, current_text)
    assert memory.CONTEXT_LABEL in prompt and prompt.index(memory.CONTEXT_LABEL) < prompt.index("\nCURRENT request:")
    assert json.loads(prompt.split(HISTORY_LABEL)[1]) == {}
    assert prompt.split("CURRENT request-scoped snapshot (whole files only):\n")[1].split(HISTORY_LABEL)[0] == "{}"
    assert memory.CONTEXT_LABEL not in _with_history(path, record, ASSESSMENT + "\nCURRENT request:\ncache")
    huge = current_text + "x" * (100_000 - len((current_text + HISTORY_LABEL + "{}").encode()))
    bounded = _with_history(path, record, huge)
    assert len(bounded.encode()) == 100_000 and huge in bounded
    assert memory.CONTEXT_LABEL not in bounded
    assert ledger.get_task(current["id"], db_path=path)["status"] == "running"


def test_memory_never_expands_current_file_snapshot_or_adds_model_calls(setup):
    path, root, _ = setup
    (root / "secret-history.txt").write_text("HISTORICAL_FILE_SHOULD_NOT_BE_READ")
    add(setup, "cache secret-history.txt inspected previously")
    complete(setup, "cache conclusion with historical file")
    calls = []
    def model(profile, prompt, staging, timeout, cancel):
        calls.append((profile, prompt, list(staging.rglob("*"))))
        if prompt.startswith(ASSESSMENT):
            return json.dumps(dict(importance=1, impact=1, complexity=2, reason="synthetic"))
        return json.dumps(dict(summary="cache explanation", changes=[]))
    worker = Worker(path, generation="context-worker", invoke=model)
    store.submit(path, OperationSpec(prompt="cache explanation", workspace=str(root)), "operator", worker.generation,
                 conversation_key="conversation-one")
    worker.run_once()
    assert len(calls) == 2 and [call[0] for call in calls] == ["flash", "flash"]
    assert all(not call[2] for call in calls)
    assert "HISTORICAL_FILE_SHOULD_NOT_BE_READ" not in calls[-1][1]
    assert wiki_store.CONTEXT_LABEL in calls[-1][1]
    assert "cannot expand the CURRENT request" in calls[-1][1]


def test_migration_eight_is_additive_and_previous_code_can_read_old_tables(tmp_path, monkeypatch):
    path = tmp_path / "upgrade.db"
    migrations = ledger.MIGRATIONS
    with monkeypatch.context() as patch:
        patch.setattr(ledger, "MIGRATIONS", migrations[:7])
        task = ledger.create_task(title="preserved", prompt="original", db_path=path)
    with db.connect(path) as conn:
        timestamp = datetime.now(UTC).isoformat()
        conn.execute("INSERT INTO conversation_sessions(id,owner_key,conversation_hash,workspace_root,created_at,updated_at) "
                     "VALUES ('synthetic-session','operator','synthetic-hash',?,?,?)", (str(tmp_path), timestamp, timestamp))
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'") if row[0] != 'schema_migrations']
        columns = {name: ','.join(f'"{row[1]}"' for row in conn.execute(f'PRAGMA table_info("{name}")')) for name in tables}
        before = {name: [tuple(row) for row in conn.execute(f'SELECT {columns[name]} FROM "{name}"')] for name in tables}
    assert ledger.apply_migrations(path) == 9
    with db.connect(path) as conn:
        after = {name: [tuple(row) for row in conn.execute(f'SELECT {columns[name]} FROM "{name}"')] for name in tables}
        assert conn.execute("SELECT memory_reset_generation FROM conversation_sessions").fetchone()[0] == 0
    assert before == after
    with monkeypatch.context() as patch:
        patch.setattr(ledger, "MIGRATIONS", migrations[:7])
        assert ledger.get_task(task["id"], db_path=path)["prompt"] == "original"
