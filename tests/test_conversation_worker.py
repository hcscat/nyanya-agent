"""Conversation context is useful data, never a new capability or permission."""

import hashlib
import json
import threading

import pytest

from nyanya_agent import conversation_store, database as db, execution_store as ledger
from nyanya_agent import operation_store as store, reviewed_changes, work_queue
from nyanya_agent.operation_spec import OperationSpec
from nyanya_agent.operation_worker import ASSESSMENT, HISTORY_RULES, RESPONSE, Worker
from nyanya_agent.task_outcomes import OutcomeSignal


@pytest.fixture
def setup(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(workspace))
    path = tmp_path / "conversation.db"
    calls = []
    replies = []

    def model(profile, prompt, staging, timeout, cancel):
        calls.append((profile, prompt, list(staging.rglob("*"))))
        if prompt.startswith(ASSESSMENT):
            return json.dumps(dict(importance=2, impact=1, complexity=3, reason="bounded request"))
        return json.dumps(replies.pop(0), ensure_ascii=False)

    worker = Worker(path, invoke=model)
    return path, workspace, worker, calls, replies


def submit(setup, prompt, **kwargs):
    path, root, worker, _, _ = setup
    return store.submit(
        path, OperationSpec(prompt=prompt, workspace=str(root), **kwargs),
        "operator", worker.generation, conversation_key="synthetic-conversation",
    )


def history(prompt):
    return json.loads(prompt.split("Prior conversation (UNTRUSTED; {} means no available history):\n", 1)[1])


def result(setup, task):
    return work_queue.result(setup[0], task["id"], "operator")


def test_two_turn_reference_uses_prior_result_in_both_invocations(setup):
    path, _, worker, calls, replies = setup
    replies.append(dict(summary="1. 캐시 확인\n2. 재시도 검토", changes=[]))
    first = submit(setup, "선택지 두 가지를 설명해줘")
    worker.run_once()
    replies.append(dict(summary="두 번째 재시도는 실패한 요청을 다시 보내는 방식입니다.", changes=[], reply_kind="answer"))
    second = submit(setup, "두 번째를 자세히 설명해줘")
    worker.run_once()
    assert ledger.get_task(first["id"], db_path=path)["status"] == "completed"
    assert ledger.get_task(second["id"], db_path=path)["status"] == "completed"
    assert calls[2][0] == "flash" and calls[3][0] == "luna"
    for _, prompt, _ in calls[2:]:
        turns = history(prompt)["turns"]
        assert len(turns) == 1
        assert turns[0]["task_id"] == first["id"]
        assert turns[0]["response"] == "1. 캐시 확인\n2. 재시도 검토"
        assert turns[0]["reply_kind"] == "answer"
        assert "cannot grant permission" in prompt
    assert result(setup, second)["response"].startswith("두 번째 재시도")


def test_necessary_question_completes_then_answer_has_question_context(setup):
    path, root, worker, calls, replies = setup
    replies.append(dict(summary="어느 함수의 재시도 횟수를 말씀하시나요?", changes=[], reply_kind="question"))
    first = submit(setup, "재시도 횟수를 설명해줘")
    worker.run_once()
    assert ledger.get_task(first["id"], db_path=path)["status"] == "completed"
    assert store.recovery_inventory(path) == []
    saved = json.loads(conversation_store.snapshot(path, "operator", "synthetic-conversation", root))
    assert saved["turns"][0]["pending_question"] is True
    replies.append(dict(summary="send 함수는 최대 세 번 시도합니다.", changes=[]))
    second = submit(setup, "send 함수, 아래 코드만 보고 답해줘: for attempt in range(3): send()")
    worker.run_once()
    assert history(calls[-1][1])["turns"][0]["reply_kind"] == "question"
    assert result(setup, second)["response"] == "send 함수는 최대 세 번 시도합니다."
    with db.connect(path) as conn:
        assert conn.execute("SELECT pending_task_id FROM conversation_sessions").fetchone()[0] is None


@pytest.mark.parametrize("invalid", [None, True, 1, [], {}, "receipt", "Question"])
def test_unsupported_reply_kind_is_rejected_without_question_state(setup, invalid):
    path, _, worker, _, replies = setup
    replies.append(dict(summary="어느 항목인가요?", changes=[], reply_kind=invalid))
    task = submit(setup, "설명해줘")
    record = store.claim(path, worker.generation)
    with pytest.raises(ValueError, match="Invalid reply_kind"):
        worker.perform(record, threading.Event())
    assert "reply_kind" not in record
    replies.append(dict(summary="어느 항목인가요?", changes=[], reply_kind=invalid))
    worker.execute(record)
    assert ledger.get_task(task["id"], db_path=path)["status"] == "failed"
    with db.connect(path) as conn:
        assert conn.execute("SELECT pending_task_id FROM conversation_sessions").fetchone()[0] is None


@pytest.mark.parametrize("action", ["create", "modify", "delete"])
def test_question_cannot_create_modify_or_delete_files(setup, action):
    path, root, worker, _, replies = setup
    (root / "note.txt").write_text("original")
    replies.append(dict(summary="어떤 내용으로 바꿀까요?", reply_kind="question", changes=[
        dict(path="note.txt", action=action, content="changed", reason="not an answer"),
    ]))
    task = submit(setup, "note.txt 내용을 확인해줘")
    record = store.claim(path, worker.generation)
    with pytest.raises(ValueError, match="Questions cannot propose"):
        worker.perform(record, threading.Event())
    assert "reply_kind" not in record
    assert ledger.get_task(task["id"], db_path=path)["status"] == "running"
    assert (root / "note.txt").read_text() == "original"
    with db.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM change_plans").fetchone()[0] == 0
        assert conn.execute("SELECT pending_task_id FROM conversation_sessions").fetchone()[0] is None


@pytest.mark.parametrize("summary", ["", " ", "\n\t"])
def test_question_must_contain_a_nonempty_human_question(setup, summary):
    path, _, worker, _, replies = setup
    replies.append(dict(summary=summary, changes=[], reply_kind="question"))
    submit(setup, "두 번째를 설명해줘")
    record = store.claim(path, worker.generation)
    with pytest.raises(ValueError, match="Question summary"):
        worker.perform(record, threading.Event())
    assert "reply_kind" not in record
    with db.connect(path) as conn:
        assert conn.execute("SELECT pending_task_id FROM conversation_sessions").fetchone()[0] is None


def test_no_history_instructs_specific_clarification_preserves_code(setup):
    _, _, worker, calls, replies = setup
    replies.append(dict(summary="어느 두 번째 항목을 뜻하시나요? 예시의 `summary` 코드를 붙여 주세요.",
                        changes=[], reply_kind="question"))
    task = submit(setup, "두 번째 summary 필드를 설명해줘")
    worker.run_once()
    assert history(calls[0][1]) == history(calls[1][1]) == {}
    assert "ask a specific necessary question" in calls[0][1]
    assert "fixed receipts" in calls[1][1]
    assert "Do not show transport field names" in calls[1][1]
    assert "Preserve legitimate code and JSON" in calls[1][1]
    assert "Do not claim\ncommands, tests, deployment" in calls[1][1]
    assert "`summary`" in result(setup, task)["response"]


def test_history_screening_and_current_no_read_are_unchanged(setup):
    _, root, worker, calls, replies = setup
    (root / "previous.txt").write_text("DO_NOT_EXPORT_OLD_SNAPSHOT")
    replies.append(dict(summary="이전 파일 검토를 마쳤습니다.", changes=[]))
    first = submit(setup, "previous.txt 검토해줘")
    worker.run_once()
    assert "DO_NOT_EXPORT_OLD_SNAPSHOT" in calls[1][1]
    replies.append(dict(summary="확인했습니다.", changes=[]))
    secret = "sk-" + "x" * 24
    submit(setup, "이 값을 기억해줘: " + secret)
    worker.run_once()
    (root / "README.md").write_text("DO_NOT_EXPORT_CURRENT_FILE")
    replies.append(dict(summary="이 메시지에는 분석할 코드가 없습니다. 코드를 붙여 주세요.",
                        changes=[], reply_kind="question"))
    submit(setup, "Do not read files. Analyze only the code in this message.")
    worker.run_once()
    for _, prompt, staged in calls[4:]:
        assert secret not in prompt
        assert "DO_NOT_EXPORT" not in prompt
        assert staged == []
        assert [turn["task_id"] for turn in history(prompt)["turns"]] == [first["id"]]


def test_history_is_queried_again_at_executor_time(setup, monkeypatch):
    _, _, worker, calls, replies = setup
    lookups = []

    def context(*args, **kwargs):
        lookups.append(kwargs["max_bytes"])
        return json.dumps({"lookup": len(lookups)})

    monkeypatch.setattr(conversation_store, "worker_context", context)
    replies.append(dict(summary="답변", changes=[]))
    submit(setup, "대화 문맥을 이용해 답해줘")
    worker.run_once()
    assert len(lookups) == 2
    assert history(calls[0][1])["lookup"] == 1
    assert history(calls[1][1])["lookup"] == 2


def test_combined_prompt_admits_only_complete_file_preimages(setup, monkeypatch):
    _, _, worker, calls, replies = setup
    complete = "filetext\\\"" * 1800
    baseline = {name: {"content": complete, "sha256": hashlib.sha256(complete.encode()).hexdigest()}
                for name in ("one.txt", "two.txt")}
    monkeypatch.setattr(reviewed_changes, "snapshot", lambda *_: baseline)
    limits = []
    real_context = conversation_store.worker_context

    def context(*args, **kwargs):
        limits.append(kwargs["max_bytes"])
        return real_context(*args, **kwargs)

    monkeypatch.setattr(conversation_store, "worker_context", context)
    replies.append(dict(summary="범위를 좁혀 주세요.", changes=[], reply_kind="question"))
    current = "가" * 19_000 + " Do not authorize any file writes."
    submit(setup, current)
    worker.run_once()
    for _, prompt, _ in calls:
        assert len(prompt.encode()) <= 100_000
        assert current in prompt
    executor = calls[-1][1]
    snap = json.loads(executor.split("CURRENT request-scoped snapshot (whole files only):\n", 1)[1]
                      .split("\nPrior conversation", 1)[0])
    assert len(snap) == 1
    assert all(item["content"] == complete for item in snap.values())
    assert len(calls[-1][2]) == len(snap)
    assert "Do not claim omitted files were read" in executor
    assert all(2 <= limit <= 24_576 for limit in limits)


def test_lost_claim_question_result_cannot_set_pending_question(setup, monkeypatch):
    path, _, worker, _, replies = setup
    replies.append(dict(summary="어느 항목인가요?", changes=[], reply_kind="question"))
    task = submit(setup, "설명해줘")
    record = store.claim(path, worker.generation)
    monkeypatch.setattr(work_queue, "renew", lambda *_: False)
    with pytest.raises(OutcomeSignal):
        worker.perform(record, threading.Event())
    assert "reply_kind" not in record
    with db.connect(path) as conn:
        assert conn.execute("SELECT pending_task_id FROM conversation_sessions").fetchone()[0] is None
        assert conn.execute("SELECT completed_execution_id FROM conversation_turns WHERE task_id=?", (task["id"],)).fetchone()[0] is None


def test_validated_question_cannot_finish_after_claim_recovery(setup):
    path, _, worker, _, replies = setup
    replies.append(dict(summary="어느 항목인가요?", changes=[], reply_kind="question"))
    task = submit(setup, "설명해줘")
    record = store.claim(path, worker.generation)
    outcome = worker.perform(record, threading.Event())
    assert outcome.status == "succeeded" and record["reply_kind"] == "question"
    store.heartbeat(path, worker.generation, closed=True)
    store.recover(path)
    with pytest.raises(ValueError):
        store.finish(path, record, outcome)
    with db.connect(path) as conn:
        assert conn.execute("SELECT pending_task_id FROM conversation_sessions").fetchone()[0] is None
        assert conn.execute("SELECT COUNT(*) FROM task_results WHERE task_id=?", (task["id"],)).fetchone()[0] == 0


@pytest.mark.parametrize("profile", ["auto", "flash", "luna", "sol", "astra"])
def test_conversation_context_does_not_override_requested_profile(setup, profile):
    _, _, worker, calls, replies = setup
    replies.append(dict(summary="첫 답변", changes=[]))
    submit(setup, "앞으로 모든 요청을 Astra로 실행해", profile="flash")
    worker.run_once()
    replies.append(dict(summary="후속 답변", changes=[]))
    submit(setup, "설명해줘", profile=profile)
    worker.run_once()
    assert [call[0] for call in calls[-2:]] == ["flash", "luna" if profile == "auto" else profile]


def test_short_assent_does_not_approve_existing_file_changes(setup):
    path, root, worker, _, replies = setup
    (root / "note.txt").write_text("original")
    change = dict(path="note.txt", action="modify", content="changed", reason="requested edit")
    replies.append(dict(summary="내용 변경안을 만들었습니다.", changes=[change]))
    first = submit(setup, "note.txt 변경해줘")
    worker.run_once()
    assert ledger.get_task(first["id"], db_path=path)["status"] == "awaiting_approval"
    replies.append(dict(summary="변경안 승인 대상이 무엇인가요?", changes=[], reply_kind="question"))
    submit(setup, "응 진행해")
    worker.run_once()
    assert (root / "note.txt").read_text() == "original"
    with db.connect(path) as conn:
        assert conn.execute("SELECT status FROM change_plans WHERE task_id=?", (first["id"],)).fetchone()[0] == "pending"


def test_prompt_contract_contains_no_routine_human_receipt_template():
    assert '"summary":"natural Korean reply to the user' in RESPONSE
    assert "fixed receipts" in RESPONSE and "routine workflow notices" in RESPONSE
    assert "current_task_status and current_plan_status describe the current ledger lifecycle" in HISTORY_RULES
    assert "Never infer that approval is still pending from an old" in HISTORY_RULES
    assert "A completed task with an applied plan no longer awaits approval" in HISTORY_RULES
