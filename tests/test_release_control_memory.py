"""Release regressions for safety-clause intake and consistent recall opt-out."""

import json

import pytest

from nyanya_agent import conversation_store, execution_store as ledger
from nyanya_agent import operation_store as store, work_memory as memory, work_queue, wiki_store
from nyanya_agent.control_intents import classify
from nyanya_agent.operation_spec import OperationSpec
from nyanya_agent.operation_worker import ASSESSMENT, HISTORY_LABEL, RESPONSE, _with_history
from nyanya_agent.task_outcomes import TaskOutcome


ACTUAL_A = (
    "[SYNTHETIC-READ-ONLY] 읽기 전용 기능 테스트입니다. "
    "파일·설정의 생성/수정/삭제와 명령 실행은 하지 마세요. "
    "HTTP GET과 POST의 차이를 두 문장으로 설명해 주세요."
)
RESOURCE_SAFETY = "파일·설정의 생성/수정/삭제와 명령 실행은 하지 마세요."


@pytest.mark.parametrize("text", [
    ACTUAL_A,
    RESOURCE_SAFETY + " HTTP GET과 POST의 차이를 설명해 주세요.",
    "HTTP GET과 POST의 차이를 설명해 주세요. " + RESOURCE_SAFETY,
    "파일과 설정을 변경하지 마세요. 명령도 실행하지 마세요. HTTP GET은 무엇인가요?",
    "기존 파일은 수정하거나 삭제하지 마. HTTP GET과 POST의 차이를 설명해 주세요.",
    "등록된 작업공간의 README.md 한 파일만 읽어줘. " + RESOURCE_SAFETY,
])
def test_complete_resource_safety_does_not_turn_questions_into_task_controls(text):
    assert classify(text).kind == "work_request"


@pytest.mark.parametrize(("text", "kind"), [
    (RESOURCE_SAFETY, "clarify"),
    (RESOURCE_SAFETY + " 취소", "clarify"),
    ("기존 파일은 삭제하지 마. 취소", "clarify"),
    ("기존 파일은 수정하거나 삭제하지 마.", "clarify"),
    ("취소하지 마", "clarify"),
    ("취소할지 알려줘", "clarify"),
    (RESOURCE_SAFETY + " task_previous는 취소해줘.", "clarify"),
    (RESOURCE_SAFETY + " 모두 취소해줘.", "clarify"),
    (RESOURCE_SAFETY + " cancel task_previous extra", "clarify"),
    (RESOURCE_SAFETY + ' "미완료 작업 취소"', "clarify"),
    ('"' + RESOURCE_SAFETY + '" HTTP GET을 설명해줘.', "clarify"),
    ("새 파일을 만들어줘. 기존 파일은 수정하거나 삭제하지 마라는 문구를 넣어줘.", "clarify"),
    ("cancel task_previous", "task_cancel"),
    ("미완료 모두 취소", "task_cancel_selection"),
    ("미완료 작업 목록만 보여줘. 기존 작업은 변경하거나 취소하지 마.", "task_list"),
])
def test_resource_safety_keeps_ambiguous_and_explicit_task_control_boundaries(text, kind):
    assert classify(text).kind == kind


@pytest.fixture
def context_state(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    path = tmp_path / "release-memory.db"
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(root))
    monkeypatch.setenv("NYANYA_WORK_MEMORY_ENABLED", "true")
    worker = "release-memory-worker"
    store.register_worker(path, worker)
    source = store.submit(path, OperationSpec(prompt="cache decision", workspace=str(root)),
                          "operator", worker, conversation_key="release-channel")
    record = store.claim(path, worker)
    record["reply_kind"] = "answer"
    record["wiki_candidates"] = [{"topic": "cache decision", "summary": "Historical cache decision was three attempts."}]
    work_queue.finish(path, record, TaskOutcome("succeeded", "cache recall sentinel"))
    return path, root, worker, source


def current_record(state, prompt):
    path, root, worker, _ = state
    store.submit(path, OperationSpec(prompt=prompt, workspace=str(root)),
                 "operator", worker, conversation_key="release-channel")
    return store.claim(path, worker)


@pytest.mark.parametrize("prompt", [
    "Don't use memory. Explain cache.",
    "기억을 쓰지 말고 cache 설명",
    "메모리를 사용하지 말고 cache 설명",
    "기억 없이 cache 설명",
    "대화 기록 없이 cache 설명",
    "이전 대화 기록은 무시하고 cache 설명",
    "Without memories, explain cache.",
    "Ignore memory and explain cache.",
    "Do not consult memories. Explain cache.",
])
def test_generic_no_memory_blocks_every_recall_path_without_reset_or_no_store(context_state, monkeypatch, prompt):
    path, root, _, _ = context_state
    record = current_record(context_state, prompt)
    # The same channel really has recallable history; this cannot pass through cross-channel isolation.
    assert "cache recall sentinel" in conversation_store.worker_context(path, record["task_id"], "operator", root)
    before = conversation_store.snapshot(path, "operator", "release-channel", root)
    assert not memory._storage_disabled(prompt)
    assert memory.worker_context(path, record["task_id"], "operator", root, prompt) == "{}"
    assert wiki_store.worker_context(path, record["task_id"], "operator", root, prompt) == "{}"

    def denied(*args, **kwargs):
        raise AssertionError("Generic no-memory must not retrieve conversation history")

    monkeypatch.setattr(conversation_store, "worker_context", denied)
    for contract in (ASSESSMENT, RESPONSE):
        value = _with_history(path, record, contract + "\nCURRENT request:\n" + prompt)
        assert json.loads(value.split(HISTORY_LABEL)[1]) == {}
        assert memory.CONTEXT_LABEL not in value
        assert wiki_store.CONTEXT_LABEL not in value
        assert prompt in value
    assert conversation_store.snapshot(path, "operator", "release-channel", root) == before


def test_storage_refusal_keeps_current_recall_but_excludes_the_new_turn_from_future_memory(context_state):
    path, root, _, _ = context_state
    prompt = "Do not store this cache explanation."
    record = current_record(context_state, prompt)
    assert memory._storage_disabled(prompt)
    assert not memory.history_input_disabled(prompt)
    assert not memory.input_disabled(prompt)
    value = _with_history(path, record, RESPONSE + "\nCURRENT request:\n" + prompt)
    assert "cache recall sentinel" in value
    work_queue.finish(path, record, TaskOutcome("succeeded", "private new response"))
    future = current_record(context_state, "cache follow-up")
    assert "private new response" not in conversation_store.worker_context(path, future["task_id"], "operator", root)
    assert all(item["task_id"] != record["task_id"] for item in memory.list_records(path, "operator", root))


def test_file_read_ban_remains_separate_from_conversation_recall(context_state):
    path, _, _, _ = context_state
    prompt = "Do not read files. Explain cache."
    record = current_record(context_state, prompt)
    assert memory.input_disabled(prompt)
    assert not memory.history_input_disabled(prompt)
    value = _with_history(path, record, RESPONSE + "\nCURRENT request:\n" + prompt)
    assert "cache recall sentinel" in value
    assert memory.CONTEXT_LABEL not in value
    assert wiki_store.CONTEXT_LABEL not in value


def test_reset_is_an_explicit_boundary_and_preserves_original_work(context_state):
    path, root, _, source = context_state
    conversation_store.reset(path, "operator", "release-channel", root)
    prompt = "Explain cache."
    record = current_record(context_state, prompt)
    assert not memory.history_input_disabled(prompt)
    value = _with_history(path, record, RESPONSE + "\nCURRENT request:\n" + prompt)
    assert json.loads(value.split(HISTORY_LABEL)[1]) == {}
    assert memory.CONTEXT_LABEL not in value
    assert wiki_store.CONTEXT_LABEL not in value
    assert ledger.get_task(source["id"], db_path=path)["status"] == "completed"
