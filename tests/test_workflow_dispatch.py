"""Control requests stay in the ledger path and bind cancellation to a seen list."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import sys

import pytest

from nyanya_agent import database as db
from nyanya_agent.control_intents import classify
from nyanya_agent.operation_service import OperationService


READ_ONLY_SAFETY_QUERY = "미완료 작업 목록만 보여줘. 기존 작업은 변경하거나 취소하지 마."
NO_REEXECUTION_QUERIES = (
    "미완료 작업 목록만 보여줘. 기존 작업은 변경하거나 취소하거나 다시 실행하지 마.",
    "미완료 작업 목록만 보여줘. 재실행하지 마.",
    "미완료 작업 목록만 보여줘. 다시실행하지 마.",
    "미완료 작업 목록만 보여줘. 재개하지 마.",
    "현재 미완료 작업들 목록만 보여주세요. 작업들은 다시 실행하거나 취소하지 마세요.",
    "남은 작업 목록을 알려줘, 이전 작업은 재개/삭제/재실행하지 말아줘.",
    "미완료 작업 목록만 보여줘 기존 작업은 취소 및 재개 또는 다시 실행하지 말아주세요!",
)
NON_LEDGER_CANCEL_REQUESTS = (
    "이 폴더의 파일을 모두 제거해줘",
    "파일을 전부 제거해줘.",
    "전체 파일을 제거해줘.",
    "남은 임시파일을 모두 제거해줘.",
    "프로젝트 작업 파일을 모두 제거해줘.",
    "기존 작업 파일을 모두 제거해줘.",
    "이전 목록의 파일을 모두 제거해줘.",
    "전체 목록을 모두 제거해줘.",
    "이전 목록 모두 취소하고 파일을 제거해줘.",
    "파일을 제거하고 이전 목록 모두 취소해줘.",
    "모두 취소해줘.",
    "전부 제거해줘.",
    "취소?", "cancel?", "이전 목록 모두 취소?", "미완료 모두 취소？",
    "미완료 작업을 취소하지 않고 파일을 모두 제거해줘.",
)
FILE_SAFETY_REQUEST = (
    "등록된 작업공간 안의 synthetic-live-check/note.txt 새 파일 하나를 만들어줘. "
    "파일 내용은 정확히 첫 줄 SyntheticWikiCheck, 둘째 줄 retry=3으로 하고 마지막에 줄바꿈을 넣어줘. "
    "기존 파일은 수정하거나 삭제하지 마. 실제 파일 생성 결과를 짧게 알려줘."
)
READ_FILE_SAFETY_REQUEST = (
    "현재 요청만 처리해줘. 기존 파일을 읽거나 수정하거나 삭제하지 마. "
    "새 파일 acceptance-new-20261029.txt를 만들고 SYNTHETIC NEW FILE 한 줄을 넣어줘. "
    "명령 실행은 하지 마."
)
AMBIGUOUS_FILE_SAFETY = (
    "기존 파일은 수정하거나 삭제하지 마.",
    "전체 파일은 수정하지 마.",
    "새 파일을 만들어줘. 기존 파일은 수정하거나 삭제하지 마라는 문구를 넣어줘.",
    '새 파일을 만들어줘. "기존 파일은 수정하거나 삭제하지 마."',
    "새 파일을 만들어줘. 기존 파일은 수정하거나 삭제하지 마. task_first는 취소해줘.",
    "새 파일을 만들어줘. 기존 파일은 수정하거나 삭제하지 마. 모두 취소해줘.",
    "새 파일을 만들어줘. 기존 파일은 수정하거나 삭제하지 마. 미완료 작업들을 모두 취소해줘.",
    "새 파일을 만들어줘. 기존 파일은 수정하거나 삭제하지 마. cancel task_first extra",
    "새 파일을 만들어줘. 기존 파일은 수정하거나 삭제하지 마. cancel all",
    "취소하지 마. 기존 파일은 수정하거나 삭제하지 마. worker.py 코드를 분석해줘.",
    "새 파일을 만들어줘. 기존 파일을 읽거나 수정하거나 삭제하지 마. task_first는 취소해줘.",
    "새 파일을 만들어줘. 기존 파일을 읽거나 수정하거나 삭제하지 마. 모두 취소해줘.",
    '새 파일을 만들어줘. "기존 파일을 읽거나 수정하거나 삭제하지 마."',
    "새 파일에 기존 파일을 읽거나 수정하거나 삭제하지 마라는 문구를 작성해줘.",
)
MIXED_LIST_QUERIES = (
    "미완료 작업 목록만 보여줘. 기존 작업은 다시 실행해줘.",
    "미완료 작업 목록만 보여줘. 재실행해줘.",
    "미완료 작업 목록만 보여줘. 재개해줘.",
    "미완료 작업 목록만 보여줘. 재실행하지 마. task_first는 재개해줘.",
    "미완료 작업 목록만 보여줘. 취소하고 다시 실행하지 마.",
    "미완료 작업 목록만 보여줘. 다시 실행하지 마라는 문구를 작성해줘.",
    "미완료 작업 목록만 보여줘. 다시 실행하지 마세요?",
    "미완료 작업 목록만 보여줘. 기존 작업은 취소해줘.",
    "미완료 작업 목록만 보여줘. 기존 작업은 변경하지 마. 모두 취소해줘.",
    "미완료 작업 목록만 보여줘. 기존 작업은 변경하거나 취소하지 마. task_first는 취소해줘.",
    "미완료 작업 목록만 보여줘. 기존 작업은 취소하지 마, 하지만 task_first는 취소해줘.",
    "미완료 작업 목록만 보여줘. 기존 작업은 취소하고 삭제하지 마.",
    "미완료 작업 목록만 보여줘. 취소하지 마세요?",
    "미완료 작업 목록만 보여줘. cancel task_first extra",
    "미완료 작업 목록만 보여줘. 파일을 삭제하고 기존 작업 취소해줘.",
    "미완료 작업 목록만 보여줘. 기존 작업은 변경하지 마. 파일을 수정해줘.",
    '미완료 작업 목록만 보여줘. "취소하지 마"',
    "cancel task_first extra. " + READ_ONLY_SAFETY_QUERY,
)


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("남은 작업은 무엇인가?", "task_list"),
        ("다른 미완료 작업들 존재하나 목록만", "task_list"),
        ("미완료 작업들은 하지 않겠다 취소/제거 해라", "task_cancel_selection"),
        ("현재 실행 제한시간은?", "runtime_status"),
        ("취소하지 마", "clarify"),
        ("취소할지 알려줘", "clarify"),
        ('"미완료 작업 취소"', "clarify"),
        ("문서의 미완료 작업 찾아줘", "work_request"),
        ("cancel task_x extra", "clarify"),
        ("why task_x extra", "clarify"),
        ("/cancel task_x extra", "clarify"),
        ("/cancel task_x", "task_cancel"),
        ("tasks all", "work_request"),
        (FILE_SAFETY_REQUEST, "work_request"),
        (READ_FILE_SAFETY_REQUEST, "work_request"),
        ("코드를 분석해줘. 전체 파일은 수정하거나 삭제하지 마.", "work_request"),
        ("기존 파일은 삭제하지 마. worker.py 코드를 분석해줘.", "work_request"),
        ("새 파일을 생성해줘. 기존 파일들은 수정/삭제하지 마세요.", "work_request"),
        ("Create a new file. 기존 파일은 변경하거나 삭제하지 말아줘.", "work_request"),
        ("TODO 문서의 미완료 항목을 분석해줘. 기존 파일은 수정하거나 삭제하지 마.", "work_request"),
        ("새 파일을 만들어줘. 기존 파일은 수정하거나 삭제하지 마. 미완료 작업 목록도 보여줘.", "work_request"),
        *[(text, "clarify") for text in AMBIGUOUS_FILE_SAFETY],
        (READ_ONLY_SAFETY_QUERY, "task_list"),
        *[(text, "task_list") for text in NO_REEXECUTION_QUERIES],
        ("미완료 작업 목록만 보여줘. 취소하지 마", "task_list"),
        ("미완료 작업 목록만 보여줘. 삭제하지 마", "task_list"),
        ("미완료 작업 목록만 보여줘. 변경하지 마", "task_list"),
        ("미완료 작업 목록만 보여줘. 기존 작업은 취소/삭제/변경하지 마.", "task_list"),
        ("현재 미완료 작업들 목록만 보여주세요. 작업들은 취소하거나 삭제하지 마세요.", "task_list"),
        ("남은 작업 목록을 알려줘, 기존 작업은 변경하지 말아줘.", "task_list"),
        ("미완료 작업 목록만 보여줘 기존 작업은 변경하거나 취소하지 마", "task_list"),
        ('"' + READ_ONLY_SAFETY_QUERY + '"', "clarify"),
        ("미완료 작업 목록만 보여줘. 취소할지 알려줘", "clarify"),
        ("미완료 작업 목록만 보여줘. 취소하지 마라는 문구를 작성해줘", "clarify"),
        *[(text, "clarify") for text in MIXED_LIST_QUERIES],
    ],
)
def test_bounded_intents(text, kind):
    assert classify(text).kind == kind


@pytest.mark.parametrize("prompt", [FILE_SAFETY_REQUEST, READ_FILE_SAFETY_REQUEST])
def test_complete_file_safety_enters_normal_intake_with_original_constraints(tmp_path, monkeypatch, fixture_worker, prompt):
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(root))
    service = OperationService(tmp_path / "ledger.db")
    _insert_task(service.path, "task_held", "operator")
    task = service.submit(prompt, root, "operator", conversation_key="fixture-channel")
    assert service.wait(task["id"], "operator", timeout=5).status == "succeeded"
    with db.connect(service.path) as conn:
        row = conn.execute("SELECT prompt FROM agent_tasks WHERE id=?", (task["id"],)).fetchone()
        assert row["prompt"] == prompt
        assert conn.execute("SELECT count(*) FROM task_operations").fetchone()[0] == 1
    assert _status(service.path, "task_held") == "failed"
    assert not list(root.iterdir())  # The fixture answer does not claim or apply a filesystem effect.
    service.close()


def _insert_task(path, task_id, owner, status="failed"):
    timestamp = datetime.now(timezone.utc).isoformat()
    with db.connect(path) as conn:
        conn.execute(
            "INSERT INTO agent_tasks (id,title,prompt,status,requested_by,metadata_json,created_at,updated_at) "
            "VALUES (?,?,?,?,?,'{}',?,?)",
            (task_id, task_id, "original request", status, owner, timestamp, timestamp),
        )


def _status(path, task_id):
    with db.connect(path) as conn:
        return conn.execute("SELECT status FROM agent_tasks WHERE id=?", (task_id,)).fetchone()["status"]


def test_list_selection_is_durable_and_rejects_new_tasks(tmp_path):
    path = tmp_path / "ledger.db"
    service = OperationService(path)
    owner = "discord-user:a"
    _insert_task(path, "task_first", owner)
    _insert_task(path, "task_other", "discord-user:b")
    listing = service.handle_intent("남은 작업은 무엇인가?", owner, conversation_key="channel:a")
    assert "task_first" in listing and "task_other" not in listing
    with db.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM agent_tasks").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM request_events WHERE event_type='control.selection'").fetchone()[0] == 1

    _insert_task(path, "task_new", owner)
    result = service.handle_intent("미완료 작업들은 하지 않겠다 취소/제거 해라", owner, conversation_key="channel:a")
    assert "다시 조회" in result
    assert _status(path, "task_first") == "failed"
    assert _status(path, "task_new") == "failed"
    service.close()


@pytest.mark.parametrize("command", [
    "이전 목록 모두 취소", "미완료 작업들을 모두 취소해줘.", "남은 작업 전부 종결해라!",
    "방금 목록을 모두 취소해주세요", "현재 작업 목록을 전부 제거해줘",
    "미완료 작업들은 하지 않겠다 취소/제거 해라",
])
def test_confirmed_selection_dismisses_only_seen_owner_tasks(tmp_path, command):
    path = tmp_path / "ledger.db"
    service = OperationService(path)
    owner = "discord-user:a"
    _insert_task(path, "task_first", owner)
    _insert_task(path, "task_other", "discord-user:b")
    service.handle_intent("작업목록", owner, conversation_key="channel:a")
    result = service.handle_intent(command, owner, conversation_key="channel:a")
    assert "task_first" in result and "task_other" not in result
    assert "task_first" not in service.handle_intent("작업목록", owner, conversation_key="channel:a")
    assert _status(path, "task_first") == "failed"
    with pytest.raises(PermissionError):
        service.handle_intent("cancel task_other", owner, conversation_key="channel:a")
    service.close()


@pytest.mark.parametrize("text", NON_LEDGER_CANCEL_REQUESTS)
def test_nonledger_or_mixed_target_cannot_cancel_saved_selection(tmp_path, monkeypatch, text):
    path = tmp_path / "ledger.db"
    service = OperationService(path)
    owner = "discord-user:a"
    _insert_task(path, "task_unrelated", owner, "queued")
    service.handle_intent("작업목록", owner, conversation_key="channel:a")
    with db.connect(path) as conn:
        before = [tuple(row) for row in conn.execute("SELECT * FROM agent_tasks")]
    assert classify(text).kind in {"clarify", "work_request"}
    service.handle_intent(text, owner, conversation_key="channel:a")
    with db.connect(path) as conn:
        assert [tuple(row) for row in conn.execute("SELECT * FROM agent_tasks")] == before
        assert conn.execute("SELECT COUNT(*) FROM task_operations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0
    service.close()


def test_api_file_removal_cannot_cancel_previously_listed_task(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from nyanya_agent.dashboard_api import create_app

    path = tmp_path / "ledger.db"
    monkeypatch.setenv("NYANYA_DASHBOARD_CONTROL_TOKEN", "fixture-token")
    service = OperationService(path)
    _insert_task(path, "task_unrelated", "operator", "queued")
    service.handle_intent("작업목록", "operator", conversation_key="operator")
    client = TestClient(create_app(path), base_url="http://127.0.0.1")
    response = client.post("/v1/operations", headers={"X-Nyanya-Control-Token": "fixture-token"},
                           json={"prompt": NON_LEDGER_CANCEL_REQUESTS[0], "workspace": str(tmp_path)})
    assert response.status_code == 201 and response.json()["kind"] == "control"
    assert _status(path, "task_unrelated") == "queued"
    service.close()


def test_control_never_enters_operation_submit(tmp_path, monkeypatch):
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(tmp_path))
    service = OperationService(tmp_path / "ledger.db")
    for text in (
        "남은 작업은 무엇인가?", "취소하지 마", "실행 제한시간",
        "cancel task_x extra", "why task_x extra", "/cancel task_x extra",
        READ_ONLY_SAFETY_QUERY, *NO_REEXECUTION_QUERIES, *MIXED_LIST_QUERIES, *AMBIGUOUS_FILE_SAFETY,
    ):
        with pytest.raises(ValueError):
            service.submit(text, tmp_path, "operator")
    with db.connect(service.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM agent_tasks").fetchone()[0] == 0
    service.close()


@pytest.mark.parametrize("query", (READ_ONLY_SAFETY_QUERY, *NO_REEXECUTION_QUERIES))
def test_safe_list_preserves_tasks_and_mixed_commands_cannot_use_selection(tmp_path, monkeypatch, query):
    path = tmp_path / "ledger.db"
    service = OperationService(path)
    owner = "discord-user:a"
    _insert_task(path, "task_first", owner, "blocked")
    _insert_task(path, "task_owned_failed", owner)
    _insert_task(path, "task_other", "discord-user:b", "blocked")
    _insert_task(path, "task_completed", owner, "completed")

    def denied(*_args, **_kwargs):
        pytest.fail("A list query or ambiguous qualifier must not submit or mutate work")

    from nyanya_agent import operation_service
    monkeypatch.setattr(service, "submit", denied)
    monkeypatch.setattr(operation_service.store, "cancel", denied)
    monkeypatch.setattr(operation_service.store, "dismiss", denied)
    monkeypatch.setattr(operation_service.store, "resume", denied)
    with db.connect(path) as conn:
        original_tasks = [tuple(row) for row in conn.execute("SELECT * FROM agent_tasks ORDER BY id")]
    listing = service.handle_intent(query, owner, conversation_key="channel:a")
    assert "task_first" in listing and "task_owned_failed" in listing
    assert "task_other" not in listing and "task_completed" not in listing
    for text in MIXED_LIST_QUERIES:
        assert "의도를 확정" in service.handle_intent(text, owner, conversation_key="channel:a")
    with db.connect(path) as conn:
        assert [tuple(row) for row in conn.execute("SELECT * FROM agent_tasks ORDER BY id")] == original_tasks
        assert conn.execute("SELECT COUNT(*) FROM task_operations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM request_events WHERE event_type='control.selection'").fetchone()[0] == 1
    # The normal list still fences later cancellation by conversation and revision.
    assert "대상이 확정되지" in service.handle_intent("이전 목록 모두 취소", owner, conversation_key="channel:b")
    _insert_task(path, "task_new", owner, "blocked")
    assert "다시 조회" in service.handle_intent("이전 목록 모두 취소", owner, conversation_key="channel:a")
    assert _status(path, "task_first") == "blocked"
    assert _status(path, "task_new") == "blocked"
    service.close()


def test_malformed_explicit_cancel_cannot_use_recent_selection(tmp_path):
    path = tmp_path / "ledger.db"
    service = OperationService(path)
    owner = "discord-user:a"
    _insert_task(path, "task_first", owner)
    service.handle_intent("작업목록", owner, conversation_key="channel:a")
    for malformed in ("cancel task_first extra", "/cancel task_first extra", "취소 task_first extra"):
        assert "의도를 확정" in service.handle_intent(malformed, owner, conversation_key="channel:a")
        assert _status(path, "task_first") == "failed"
    service.close()


def test_wait_reports_blocked_retry_when_only_prior_result_exists(tmp_path, monkeypatch):
    from nyanya_agent import operation_service

    service = OperationService(tmp_path / "ledger.db")
    monkeypatch.setattr(operation_service.work_queue, "result", lambda *_: {
        "execution_id": "exec_old", "outcome": "succeeded", "response": "old success",
    })
    monkeypatch.setattr(operation_service.ledger, "get_task", lambda *_args, **_kwargs: {
        "status": "blocked", "current_execution_id": "exec_new",
    })
    monkeypatch.setattr(operation_service.store, "explain", lambda *_: "retry held")
    result = service.wait("task_retry", "operator", timeout=0.1)
    assert result.status == "blocked"
    assert result.text == "retry held"
    service.close()


@pytest.mark.parametrize(("content", "admin", "global_scope"), [
    ("남은 작업은 무엇인가?", False, False), ("!nyanya " + READ_ONLY_SAFETY_QUERY, False, False),
    *[("!nyanya " + text, False, False) for text in NO_REEXECUTION_QUERIES],
    *[("!nyanya " + alias, False, False) for alias in ("/tasks", "/task", "/queue", "/작업목록")],
    *[("!nyanya " + alias + " all", admin, True)
      for alias in ("tasks", "/tasks", "/task", "/queue", "/작업목록") for admin in (False, True)],
])
def test_discord_query_uses_ledger_without_creating_operation(tmp_path, monkeypatch, content, admin, global_scope):
    from nyanya_agent import discord_bridge

    path = tmp_path / "ledger.db"
    monkeypatch.setenv("NYANYA_DASHBOARD_DB_PATH", str(path))
    monkeypatch.setenv("NYANYA_DISCORD_BOT_TOKEN", "fixture")
    monkeypatch.setenv("NYANYA_ALLOW_UNLISTED", "true")
    monkeypatch.setenv("NYANYA_OWNER_USER_IDS", "123" if admin else "")
    service = OperationService(path)
    _insert_task(path, "task_owned", "discord-user:123", "queued")
    _insert_task(path, "task_other_owner", "discord-user:987", "queued")
    service.close()
    sent = []

    def denied(*_args, **_kwargs):
        pytest.fail("Discord task queries must never submit model work")

    monkeypatch.setattr(OperationService, "submit", denied)

    class Channel:
        id = 456
        name = "fixture"

        async def send(self, text):
            sent.append(text)

    class DMChannel(Channel):
        pass

    class FakeClient:
        user = None

        def __init__(self, **_kwargs):
            self.on_message = None

        def event(self, function):
            setattr(self, function.__name__, function)
            return function

    fake_discord = SimpleNamespace(
        Intents=SimpleNamespace(default=lambda: SimpleNamespace()),
        AllowedMentions=SimpleNamespace(none=lambda: None),
        Client=FakeClient,
        DMChannel=DMChannel,
        utils=SimpleNamespace(setup_logging=lambda: None),
    )
    monkeypatch.setitem(sys.modules, "discord", fake_discord)
    monkeypatch.setattr(discord_bridge, "parse_args", lambda: SimpleNamespace(config=None, check_config=False))
    monkeypatch.setattr(discord_bridge, "load_runtime_config", lambda _: {})

    async def fake_run_client(client, _token, store):
        message = SimpleNamespace(
            id=789, author=SimpleNamespace(id=123, bot=False, name="fixture"),
            channel=Channel() if content.startswith("!nyanya") else DMChannel(), content=content, guild=None,
            mentions=[], attachments=[],
        )
        await client.on_message(message)
        store.close()

    monkeypatch.setattr(discord_bridge, "run_client", fake_run_client)
    assert discord_bridge.main() == 0
    assert any("task_owned" in item for item in sent) == (not global_scope or admin)
    assert any("task_other_owner" in item for item in sent) == (global_scope and admin)
    if global_scope and not admin:
        assert any("관리자만" in item for item in sent)
    with db.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM agent_tasks").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM task_operations").fetchone()[0] == 0
        assert conn.execute("SELECT mode FROM agent_requests").fetchone()[0] == "control"
        assert _status(path, "task_owned") == "queued"


@pytest.mark.parametrize("text", [
    "What is the timeout in worker.py?",
    "Explain how timeout works in process_runner.py",
    "HTTP timeout은 무엇인가?",
    "다른 서버의 실행 제한시간은 몇 초인가?",
    "worker.py의 타임아웃을 설명해줘.",
    "What is the timeout for an HTTP request?",
    "Explain how timeout works in `process_runner.py`",
])
def test_technical_timeout_questions_remain_work_requests(text):
    assert classify(text).kind == "work_request"


@pytest.mark.parametrize("text", [
    "현재 실행 제한시간은?", "현재 실행 제한시간은 몇초로 되어있는가?",
    "냐냐의 타임아웃은 얼마인가?", "실행 제한 시간을 알려주세요.",
    "What is your timeout?", "What is the agent's execution time limit?",
])
def test_bounded_agent_timeout_questions_remain_local_controls(text):
    assert classify(text).kind == "runtime_status"


def test_cancel_selection_rejects_target_changed_after_list(tmp_path, monkeypatch):
    from nyanya_agent import operation_service

    path = tmp_path / "ledger.db"
    service = OperationService(path)
    owner = "discord-user:a"
    _insert_task(path, "task_first", owner)
    service.handle_intent("작업목록", owner, conversation_key="channel:a")
    original = operation_service.store.dismiss

    def concurrent_change(db_path, task_id, actor, **kwargs):
        with db.connect(db_path) as conn:
            conn.execute("UPDATE agent_tasks SET updated_at=? WHERE id=?", ("later revision", task_id))
        return original(db_path, task_id, actor, **kwargs)

    monkeypatch.setattr(operation_service.store, "dismiss", concurrent_change)
    result = service.handle_intent("이전 목록 모두 취소", owner, conversation_key="channel:a")
    assert "처리 보류" in result
    assert "task_first" in service.handle_intent("작업목록", owner, conversation_key="channel:a")
    service.close()
