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
FILE_SAFETY_REQUEST = (
    "등록된 작업공간 안의 synthetic-live-check/note.txt 새 파일 하나를 만들어줘. "
    "파일 내용은 정확히 첫 줄 SyntheticWikiCheck, 둘째 줄 retry=3으로 하고 마지막에 줄바꿈을 넣어줘. "
    "기존 파일은 수정하거나 삭제하지 마. 실제 파일 생성 결과를 짧게 알려줘."
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
)
MIXED_LIST_QUERIES = (
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
        ("코드를 분석해줘. 전체 파일은 수정하거나 삭제하지 마.", "work_request"),
        ("기존 파일은 삭제하지 마. worker.py 코드를 분석해줘.", "work_request"),
        ("새 파일을 생성해줘. 기존 파일들은 수정/삭제하지 마세요.", "work_request"),
        ("Create a new file. 기존 파일은 변경하거나 삭제하지 말아줘.", "work_request"),
        ("TODO 문서의 미완료 항목을 분석해줘. 기존 파일은 수정하거나 삭제하지 마.", "work_request"),
        ("새 파일을 만들어줘. 기존 파일은 수정하거나 삭제하지 마. 미완료 작업 목록도 보여줘.", "work_request"),
        *[(text, "clarify") for text in AMBIGUOUS_FILE_SAFETY],
        (READ_ONLY_SAFETY_QUERY, "task_list"),
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


def test_complete_file_safety_enters_normal_intake_with_original_constraints(tmp_path, monkeypatch, fixture_worker):
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(root))
    service = OperationService(tmp_path / "ledger.db")
    _insert_task(service.path, "task_held", "operator")
    task = service.submit(FILE_SAFETY_REQUEST, root, "operator", conversation_key="fixture-channel")
    assert service.wait(task["id"], "operator", timeout=5).status == "succeeded"
    with db.connect(service.path) as conn:
        row = conn.execute("SELECT prompt FROM agent_tasks WHERE id=?", (task["id"],)).fetchone()
        assert row["prompt"] == FILE_SAFETY_REQUEST
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


def test_confirmed_selection_dismisses_only_seen_owner_tasks(tmp_path):
    path = tmp_path / "ledger.db"
    service = OperationService(path)
    owner = "discord-user:a"
    _insert_task(path, "task_first", owner)
    _insert_task(path, "task_other", "discord-user:b")
    service.handle_intent("작업목록", owner, conversation_key="channel:a")
    result = service.handle_intent("이전 목록 모두 취소", owner, conversation_key="channel:a")
    assert "task_first" in result and "task_other" not in result
    assert "task_first" not in service.handle_intent("작업목록", owner, conversation_key="channel:a")
    assert _status(path, "task_first") == "failed"
    with pytest.raises(PermissionError):
        service.handle_intent("cancel task_other", owner, conversation_key="channel:a")
    service.close()


def test_control_never_enters_operation_submit(tmp_path, monkeypatch):
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(tmp_path))
    service = OperationService(tmp_path / "ledger.db")
    for text in (
        "남은 작업은 무엇인가?", "취소하지 마", "실행 제한시간",
        "cancel task_x extra", "why task_x extra", "/cancel task_x extra",
        READ_ONLY_SAFETY_QUERY, *MIXED_LIST_QUERIES, *AMBIGUOUS_FILE_SAFETY,
    ):
        with pytest.raises(ValueError):
            service.submit(text, tmp_path, "operator")
    with db.connect(service.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM agent_tasks").fetchone()[0] == 0
    service.close()


def test_safe_list_preserves_tasks_and_mixed_commands_cannot_use_selection(tmp_path, monkeypatch):
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
    with db.connect(path) as conn:
        original_tasks = [tuple(row) for row in conn.execute("SELECT * FROM agent_tasks ORDER BY id")]
    listing = service.handle_intent(READ_ONLY_SAFETY_QUERY, owner, conversation_key="channel:a")
    assert "task_first" in listing and "task_owned_failed" in listing
    assert "task_other" not in listing and "task_completed" not in listing
    for text in MIXED_LIST_QUERIES:
        assert "의도를 확정" in service.handle_intent(text, owner, conversation_key="channel:a")
    with db.connect(path) as conn:
        assert [tuple(row) for row in conn.execute("SELECT * FROM agent_tasks ORDER BY id")] == original_tasks
        assert conn.execute("SELECT COUNT(*) FROM task_operations").fetchone()[0] == 0
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


@pytest.mark.parametrize("content", ["남은 작업은 무엇인가?", "!nyanya " + READ_ONLY_SAFETY_QUERY])
def test_discord_query_uses_ledger_without_creating_operation(tmp_path, monkeypatch, content):
    from nyanya_agent import discord_bridge

    path = tmp_path / "ledger.db"
    monkeypatch.setenv("NYANYA_DASHBOARD_DB_PATH", str(path))
    monkeypatch.setenv("NYANYA_DISCORD_BOT_TOKEN", "fixture")
    monkeypatch.setenv("NYANYA_ALLOW_UNLISTED", "true")
    service = OperationService(path)
    _insert_task(path, "task_owned", "discord-user:123")
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
    assert any("task_owned" in item for item in sent)
    with db.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM agent_tasks").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM task_operations").fetchone()[0] == 0
        assert conn.execute("SELECT mode FROM agent_requests").fetchone()[0] == "control"
        assert _status(path, "task_owned") == "failed"


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
