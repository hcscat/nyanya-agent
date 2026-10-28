"""Conversation ingress, private exports and truthful local control responses."""

import json
import stat
import sys
from types import SimpleNamespace

import pytest

from nyanya_agent import conversation_store, database as db, execution_store as ledger
from nyanya_agent.bridge_store import NyaNyaConversationStore
from nyanya_agent.operation_worker import Worker


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(root))
    monkeypatch.setenv("NYANYA_DASHBOARD_DB_PATH", str(root / "state.db"))
    store = NyaNyaConversationStore({"sessions_dir": str(root / "exports"), "base_url": "private-config-value"})
    monkeypatch.setattr(store, "execution_workspace", lambda owner: root)
    worker = Worker(store.operations.path, invoke=lambda *_: "{}")
    monkeypatch.setattr(store.operations, "ensure_worker", lambda: worker.generation)
    yield store, worker, root
    worker.close()
    store.close()


def submit(store, channel="channel:a", prompt="Explain the example", owner="operator"):
    return store.submit(owner_key=owner, conversation_key=channel, prompt=prompt, mode="auto", responder=lambda _: None)


def test_bridge_receipt_and_facade_bind_channel_scope(bridge):
    store, _, root = bridge
    ack = submit(store)
    assert len(ack.splitlines()) == 1 and "접수" in ack
    with db.connect(store.operations.path) as conn:
        row = conn.execute("SELECT task_id FROM conversation_turns").fetchone()
        assert row["task_id"] in ack
        spec = json.loads(conn.execute("SELECT spec_json FROM task_operations").fetchone()["spec_json"])
        assert spec["version"] == 1 and "conversation_key" not in spec
    current = json.loads(conversation_store.snapshot(store.operations.path, "operator", "channel:a", root))
    assert current["turns"][0]["request"] == "Explain the example"
    assert conversation_store.snapshot(store.operations.path, "operator", "channel:b", root) == "{}"
    assert conversation_store.snapshot(store.operations.path, "other", "channel:a", root) == "{}"


def test_reset_persists_scope_without_cancelling_or_erasing_tasks(bridge):
    store, _, root = bridge
    submit(store)
    submit(store, "channel:b", "Explain a second example")
    with db.connect(store.operations.path) as conn:
        baseline = [tuple(row) for row in conn.execute("SELECT * FROM agent_tasks ORDER BY id")]
    store.reset("channel:a", owner_key="operator")
    assert conversation_store.snapshot(store.operations.path, "operator", "channel:a", root) == "{}"
    assert "second example" in conversation_store.snapshot(store.operations.path, "operator", "channel:b", root)
    with db.connect(store.operations.path) as conn:
        assert [tuple(row) for row in conn.execute("SELECT * FROM agent_tasks ORDER BY id")] == baseline
        assert conn.execute("SELECT COUNT(*) FROM conversation_turns").fetchone()[0] == 2


def test_save_exports_only_bounded_scoped_screened_durable_history(bridge):
    store, _, _ = bridge
    submit(store, prompt="Explain a public example")
    submit(store, "channel:b", "Other channel private note")
    # Legacy memory and configuration must never become the new durable export.
    store._messages_by_key = {"channel:a": [{"role": "system", "content": 'api_key="synthetic-secret"'}]}
    first = store.save("channel:a", owner_key="operator")
    second = store.save("channel:a", owner_key="operator")
    assert first != second and first.exists()
    content = first.read_text()
    assert len(content.encode()) <= 24576
    assert "public example" in content
    assert "Other channel" not in content and "synthetic-secret" not in content
    assert "private-config-value" not in content and "base_url" not in content
    assert stat.S_IMODE(first.stat().st_mode) == 0o600 and first.stat().st_nlink == 1


def test_save_filters_sensitive_durable_result(bridge):
    store, _, _ = bridge
    submit(store)
    with db.connect(store.operations.path) as conn:
        conn.execute("UPDATE agent_tasks SET prompt=?", ('api_key="synthetic-secret-value"',))
    assert store.save("channel:a", owner_key="operator").read_text() == "{}"


def test_save_disabled_or_symlink_directory_is_not_written(bridge):
    store, _, root = bridge
    store.config["save_transcripts"] = False
    assert store.save("channel:a", owner_key="operator") is None
    store.config["save_transcripts"] = True
    real = root / "real"
    real.mkdir()
    linked = root / "linked"
    linked.symlink_to(real, target_is_directory=True)
    store.config["sessions_dir"] = str(linked)
    with pytest.raises(OSError):
        store.save("channel:a", owner_key="operator")
    assert list(real.iterdir()) == []


def insert_task(path, task_id, status, owner="operator"):
    with db.connect(path) as conn:
        conn.execute("INSERT INTO agent_tasks(id,title,prompt,requested_by,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                     (task_id, "Example", "Explain the example", owner, status, "2026-10-07", "2026-10-07"))


@pytest.mark.parametrize(("status", "expected"), [
    ("failed", "다시 진행하지"), ("completed", "이미 완료"), ("cancelled", "취소된 상태"), ("queued", "취소된 상태"),
])
def test_cancel_truth_depends_on_ledger_status(bridge, status, expected):
    store, _, _ = bridge
    insert_task(store.operations.path, "task_example", status)
    response = store.operations.handle_intent("cancel task_example", "operator")
    if status == "failed":
        assert "다시 진행하지" in response and "실패 이력" in response
        assert ledger.get_task("task_example", db_path=store.operations.path)["status"] == "failed"
    else:
        assert expected in response
    assert "종료 확인" not in response


def test_completed_cancel_explains_lost_history_without_resolving_it(bridge):
    store, _, _ = bridge
    path = store.operations.path
    insert_task(path, "task_example", "completed")
    with db.connect(path) as conn:
        conn.execute("INSERT INTO executions(id,task_id,adapter_type,status,created_at,updated_at) VALUES ('exec_old','task_example','operation','lost','2026-10-07','2026-10-07')")
        baseline = [tuple(row) for row in conn.execute("SELECT * FROM executions")]
    response = store.operations.handle_intent("cancel task_example", "operator")
    assert "현재 작업은 완료" in response and "이전 실행" in response and "확인되지" in response
    assert "SafeOperationError" not in response
    with db.connect(path) as conn:
        assert [tuple(row) for row in conn.execute("SELECT * FROM executions")] == baseline
    assert ledger.get_task("task_example", db_path=path)["status"] == "completed"


def test_active_cancel_waits_for_termination_and_blocked_effects_stay_held(bridge):
    from nyanya_agent import operation_store
    store, worker, _ = bridge
    submit(store)
    record = operation_store.claim(store.operations.path, worker.generation)
    response = store.operations.handle_intent(f"cancel {record['task_id']}", "operator")
    assert "중단을 요청" in response and "종료 확인" in response
    insert_task(store.operations.path, "task_held", "blocked")
    with db.connect(store.operations.path) as conn:
        conn.execute("INSERT INTO executions(id,task_id,adapter_type,status,created_at,updated_at) VALUES ('exec_held','task_held','operation','lost','2026-10-07','2026-10-07')")
    response = store.operations.handle_intent("cancel task_held", "operator")
    assert "확정할 수 없어 보류" in response
    assert ledger.get_task("task_held", db_path=store.operations.path)["status"] == "blocked"


def test_cancel_control_keeps_owner_and_clarification_boundaries(bridge):
    store, _, _ = bridge
    insert_task(store.operations.path, "task_other", "failed", "other")
    with pytest.raises(PermissionError):
        store.operations.handle_intent("cancel task_other", "operator")
    response = store.operations.handle_intent("취소할지 알려줘", "operator")
    assert "알려주세요" in response and "cancel 작업ID" not in response
    with db.connect(store.operations.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM task_operations").fetchone()[0] == 0


def test_dismiss_responses_keep_terminal_history_and_active_work(bridge):
    store, _, _ = bridge
    insert_task(store.operations.path, "task_done", "completed")
    insert_task(store.operations.path, "task_queued", "queued")
    assert "이미 완료" in store.operations.handle_intent("dismiss task_done", "operator")
    assert "실패한 작업에만" in store.operations.handle_intent("dismiss task_queued", "operator")
    assert ledger.get_task("task_queued", db_path=store.operations.path)["status"] == "queued"


def test_simple_confirmation_cannot_apply_existing_file_plan(bridge):
    store, _, _ = bridge
    response = submit(store, prompt="응 진행해")
    assert "접수" in response
    with db.connect(store.operations.path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM change_plans").fetchone()[0] == 0
        spec = json.loads(conn.execute("SELECT spec_json FROM task_operations").fetchone()["spec_json"])
        assert spec["kind"] == "request" and not spec["plan_id"]


def test_discord_reset_and_save_use_authenticated_channel_scope(tmp_path, monkeypatch):
    from nyanya_agent import discord_bridge
    root = tmp_path.resolve()
    monkeypatch.setenv("NYANYA_DASHBOARD_DB_PATH", str(root / "state.db"))
    monkeypatch.setenv("NYANYA_DISCORD_BOT_TOKEN", "fixture")
    monkeypatch.setenv("NYANYA_ALLOW_UNLISTED", "true")
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(root))
    config = root / "workspaces.json"
    config.write_text(json.dumps({"version": 1, "users": {"discord-user:123": {"workspace": str(root)}}}))
    monkeypatch.setenv("NYANYA_USER_WORKSPACES_FILE", str(config))
    monkeypatch.setattr(NyaNyaConversationStore, "execution_workspace", lambda self, owner: root)
    observed = []
    original_reset, original_save = NyaNyaConversationStore.reset, NyaNyaConversationStore.save

    def reset(self, key, **kwargs):
        observed.append(("reset", key, kwargs["owner_key"]))
        return original_reset(self, key, **kwargs)

    def save(self, key, **kwargs):
        observed.append(("save", key, kwargs["owner_key"]))
        return original_save(self, key, **kwargs)

    monkeypatch.setattr(NyaNyaConversationStore, "reset", reset)
    monkeypatch.setattr(NyaNyaConversationStore, "save", save)
    sent = []

    class DMChannel:
        id = 456
        name = "fixture"

        async def send(self, text):
            sent.append(text)

    class Client:
        user = None

        def __init__(self, **kwargs):
            pass

        def event(self, callback):
            setattr(self, callback.__name__, callback)
            return callback

    monkeypatch.setitem(sys.modules, "discord", SimpleNamespace(
        Intents=SimpleNamespace(default=lambda: SimpleNamespace()),
        AllowedMentions=SimpleNamespace(none=lambda: None), Client=Client, DMChannel=DMChannel,
        utils=SimpleNamespace(setup_logging=lambda: None),
    ))
    monkeypatch.setattr(discord_bridge, "parse_args", lambda: SimpleNamespace(config=None, check_config=False))
    monkeypatch.setattr(discord_bridge, "load_runtime_config", lambda _: {"sessions_dir": str(root / "exports")})

    async def run_client(client, token, store):
        for message_id, content in enumerate(("reset", "save"), start=1):
            message = SimpleNamespace(id=message_id, author=SimpleNamespace(id=123, bot=False, name="fixture"),
                                      channel=DMChannel(), content=content, guild=None, mentions=[], attachments=[])
            await client.on_message(message)
        store.close()

    monkeypatch.setattr(discord_bridge, "run_client", run_client)
    assert discord_bridge.main() == 0
    assert observed == [("reset", "discord:456:user:123", "discord-user:123"),
                        ("save", "discord:456:user:123", "discord-user:123")]
    assert any("초기화" in text for text in sent)
    assert len(list((root / "exports").iterdir())) == 1
    with db.connect(root / "state.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM task_operations").fetchone()[0] == 0
