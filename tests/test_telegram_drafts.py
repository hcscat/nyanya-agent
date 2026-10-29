"""Telegram's authenticated file controls share the existing operation authority."""

import json

import pytest

from nyanya_agent import database as db, execution_store as ledger
from nyanya_agent.bridge_store import NyaNyaConversationStore
from nyanya_agent.operation_worker import ASSESSMENT, Worker
from nyanya_agent.telegram_bridge import TelegramBridge


@pytest.fixture
def telegram(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "note.txt").write_text("before\n")
    registration = tmp_path / "workspaces.json"
    registration.write_text(json.dumps({"users": {f"telegram-user:{i}": {"workspace": str(root)} for i in (41, 42)}}))
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(root))
    monkeypatch.setenv("NYANYA_USER_WORKSPACES_FILE", str(registration))
    monkeypatch.setenv("NYANYA_DASHBOARD_DB_PATH", str(tmp_path / "state.db"))
    monkeypatch.setenv("NYANYA_TELEGRAM_ALLOWED_CHAT_IDS", "7,8")
    monkeypatch.setenv("NYANYA_ALLOW_UNLISTED", "false")
    store = NyaNyaConversationStore({})
    replies, messages = [], []

    def model(profile, prompt, *_):
        if prompt.startswith(ASSESSMENT):
            return json.dumps(dict(importance=1, impact=1, complexity=1, task_kind="document", reason="fixture"))
        return json.dumps(replies.pop(0))

    worker = Worker(store.operations.path, invoke=model)
    monkeypatch.setattr(store.operations, "ensure_worker", lambda: worker.generation)
    bridge = TelegramBridge("fixture", store)
    monkeypatch.setattr(bridge, "send", lambda chat, text: messages.append((chat, text)))

    def send(text, *, user=41, chat=7):
        bridge.handle_update({"message": {"chat": {"id": chat}, "from": {"id": user}, "text": text}})

    yield root, store, worker, replies, messages, send
    worker.close()
    store.close()


def latest_draft(store):
    with db.connect(store.operations.path) as conn:
        return dict(conn.execute("SELECT * FROM operation_drafts ORDER BY created_at DESC LIMIT 1").fetchone())


@pytest.mark.parametrize("command", ["approve", "/approve", "/approve@FixtureBot"])
def test_telegram_creates_new_file_only_after_exact_approval(telegram, command):
    root, store, worker, replies, _, send = telegram
    replies.append(dict(summary="Draft output", changes=[dict(path="new.txt", action="create", content="approved\n", reason="requested")]))
    send("Prepare a new text file")
    assert worker.run_once()
    draft = latest_draft(store)
    with db.connect(store.operations.path) as conn:
        plan = conn.execute("SELECT * FROM change_plans WHERE id=?", (draft["plan_id"],)).fetchone()
    target = root / json.loads(plan["changes_json"])[0]["path"]
    assert not target.exists()
    send(f"{command} {plan['id']} {plan['plan_hash']}")
    assert worker.run_once()
    assert target.read_text() == "approved\n"
    send(f"{command} {plan['id']} {plan['plan_hash']}")
    with db.connect(store.operations.path) as conn:
        assert conn.execute("SELECT count(*) FROM task_operations WHERE json_extract(spec_json,'$.kind')='request'").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM task_operations WHERE json_extract(spec_json,'$.kind')='apply'").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM change_journal WHERE plan_id=?", (plan["id"],)).fetchone()[0] == 1


def test_telegram_read_scope_feedback_show_and_close_are_controls(telegram):
    root, store, worker, replies, _, send = telegram
    replies.append(dict(summary="Need input", changes=[], read_files=["note.txt"]))
    send("Prepare a change to note.txt")
    assert worker.run_once()
    draft = latest_draft(store)
    assert draft["snapshot_json"] == "{}"
    replies.append(dict(summary="Change draft", changes=[dict(path="note.txt", action="modify", content="after\n", reason="requested")]))
    send(f"/open-draft@FixtureBot {draft['id']} {draft['scope_hash']}")
    assert worker.run_once()
    send(f"draft-show {draft['id']}")
    replies.append(dict(summary="Keep the current draft", changes=[]))
    send(f"/draft-feedback {draft['id']} Keep the current draft")
    assert worker.run_once()
    send(f"draft-close {draft['id']}")
    assert latest_draft(store)["status"] == "closed"
    assert (root / "note.txt").read_text() == "before\n"
    with db.connect(store.operations.path) as conn:
        assert conn.execute("SELECT count(*) FROM agent_tasks").fetchone()[0] == 3
        assert conn.execute("SELECT count(*) FROM change_journal").fetchone()[0] == 0


@pytest.mark.parametrize("case", ["owner", "channel", "hash", "unlisted"])
def test_telegram_cannot_broaden_read_approval_scope(telegram, case):
    root, store, worker, replies, messages, send = telegram
    replies.append(dict(summary="Need input", changes=[], read_files=["note.txt"]))
    send("Prepare a change to note.txt")
    assert worker.run_once()
    draft = latest_draft(store)
    checksum = "wrong" if case == "hash" else draft["scope_hash"]
    send(f"open-draft {draft['id']} {checksum}", user=42 if case == "owner" else 41,
         chat=8 if case == "channel" else 9 if case == "unlisted" else 7)
    assert latest_draft(store)["snapshot_json"] == "{}"
    assert (root / "note.txt").read_text() == "before\n"
    with db.connect(store.operations.path) as conn:
        assert conn.execute("SELECT count(*) FROM agent_tasks").fetchone()[0] == 1
    assert messages


def test_telegram_help_lists_supported_file_controls_without_runtime_prefix(telegram):
    _, store, _, _, messages, send = telegram
    send("/help")
    help_text = messages[-1][1]
    assert "open-draft" in help_text and "draft-feedback" in help_text and "approve" in help_text
    with db.connect(store.operations.path) as conn:
        assert conn.execute("SELECT count(*) FROM agent_tasks").fetchone()[0] == 0


def test_telegram_wrong_final_hash_has_no_apply_task(telegram):
    _, store, worker, replies, _, send = telegram
    replies.append(dict(summary="Draft output", changes=[dict(path="new.txt", action="create", content="pending", reason="requested")]))
    send("Prepare a new text file")
    assert worker.run_once()
    draft = latest_draft(store)
    send(f"approve {draft['plan_id']} wrong")
    with db.connect(store.operations.path) as conn:
        assert conn.execute("SELECT count(*) FROM task_operations WHERE json_extract(spec_json,'$.kind')='apply'").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM change_journal").fetchone()[0] == 0
    assert ledger.get_task(draft["source_task_id"], db_path=store.operations.path)["status"] == "awaiting_approval"
