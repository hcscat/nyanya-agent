"""Discord ingress claims; synthetic SQLite and fake connector only."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import sys
import threading

import pytest

from nyanya_agent import dashboard_store as store, database as db, discord_bridge


def claim(path, **changes):
    values = dict(source="discord", channel_id="channel", user_id="owner", message_id="message",
                  prompt="original request", metadata={"attachment_count": 1}, db_path=path)
    values.update(changes)
    return store.claim_agent_request(**values)


def test_repeated_ingress_preserves_first_request_and_one_receipt(tmp_path):
    path = tmp_path / "state.db"
    first, created = claim(path)
    repeated, duplicate_created = claim(path, prompt="edited payload must not replace original")
    assert created and not duplicate_created and first == repeated
    with db.connect(path) as conn:
        rows = conn.execute("SELECT * FROM agent_requests").fetchall()
        assert len(rows) == 1 and rows[0]["prompt"] == "original request"
        assert conn.execute("SELECT COUNT(*) FROM request_events").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action='request.received'").fetchone()[0] == 1


def test_concurrent_ingress_has_one_winner(tmp_path):
    path = tmp_path / "state.db"
    store.init_db(path)
    barrier = threading.Barrier(8)

    def intake(_):
        barrier.wait()
        return claim(path)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(intake, range(8)))
    assert len({request for request, _created in results}) == 1
    assert sum(created for _request, created in results) == 1
    with db.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM agent_requests").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM request_events").fetchone()[0] == 1


@pytest.mark.parametrize("change", [{"source": "telegram"}, {"channel_id": "other-channel"},
                                    {"user_id": "other-owner"}, {"message_id": "other-message"}])
def test_ingress_identity_is_scoped_and_new_message_is_independent(tmp_path, change):
    path = tmp_path / "state.db"
    first, _ = claim(path)
    second, created = claim(path, **change)
    assert created and second != first


def test_existing_recorded_message_is_not_adopted_as_fresh_work(tmp_path):
    path = tmp_path / "state.db"
    old = store.create_agent_request(source="discord", channel_id="channel", user_id="owner",
                                     prompt="old original", metadata={"message_id": "message"}, db_path=path)
    assert claim(path) == (old, False)


@pytest.mark.parametrize("field", ["source", "channel_id", "user_id", "message_id"])
def test_ingress_rejects_missing_identity_before_creating_state(tmp_path, field):
    path = tmp_path / "absent.db"
    with pytest.raises(ValueError):
        claim(path, **{field: ""})
    assert not path.exists()


def test_unrecorded_claims_are_scoped_bounded_and_process_local():
    cache = discord_bridge._UnrecordedMessageClaims(limit=2)
    first = ("discord", "channel", "owner", "first")
    other_scope = ("discord", "other", "owner", "first")
    assert cache.claim(first) and not cache.claim(first)
    assert cache.claim(other_scope)
    assert cache.claim(("discord", "channel", "owner", "second"))
    assert cache.claim(first)  # Deliberate oldest-entry eviction limitation.
    assert discord_bridge._UnrecordedMessageClaims().claim(first)  # Restart is not durable.
    with pytest.raises(ValueError):
        discord_bridge._UnrecordedMessageClaims(limit=0)


def test_unrecorded_lookup_does_not_create_database(tmp_path):
    path = tmp_path / "absent.db"
    assert store.find_agent_request_by_message(
        source="discord", channel_id="channel", user_id="owner", message_id="message", db_path=path,
    ) is None
    assert not path.exists()


def run_bridge(tmp_path, monkeypatch, *, recording=True, concurrent=False, attached=False,
               content="Explain GET and POST", claim_failure=False, existing_recorded=False):
    path = tmp_path / "state.db"
    calls, sent, downloads, controls = [], [], [], []
    monkeypatch.setenv("NYANYA_DASHBOARD_DB_PATH", str(path))
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(tmp_path))
    store.init_db(path)
    if existing_recorded:
        claim(path)
    monkeypatch.setenv("NYANYA_DISCORD_BOT_TOKEN", "synthetic-fixture")
    monkeypatch.setenv("NYANYA_DISCORD_PREFIX", "!nyanya")
    monkeypatch.setenv("NYANYA_ALLOW_UNLISTED", "true")
    monkeypatch.setenv("NYANYA_DISCORD_FILE_SHARE_CHANNEL_IDS", "")
    monkeypatch.setenv("NYANYA_DISCORD_FILE_SHARE_CHANNEL_NAMES", "")
    monkeypatch.setenv("NYANYA_DASHBOARD_RECORDING_ENABLED", str(recording).lower())

    class Channel:
        id, name = "channel", "fixture"
        guild = SimpleNamespace(id="synthetic-guild", filesize_limit=8 * 1024 * 1024)

        async def send(self, text):
            sent.append(text)

    class DMChannel(Channel):
        pass

    class Attachment:
        filename, size = "fixture.txt", 7

        async def save(self, output):
            downloads.append(self.filename)
            await asyncio.sleep(0)
            output.write(b"fixture")

    class Client:
        user = None

        def __init__(self, **_kwargs):
            pass

        def event(self, function):
            setattr(self, function.__name__, function)
            return function

    def handle_intent(*args, **_kwargs):
        controls.append(args)
        return "one control response"

    class ConversationStore:
        def __init__(self, _config):
            store.init_db(path)
            self.operations = SimpleNamespace(path=path, handle_intent=handle_intent)

        def execution_workspace(self, _owner):
            return tmp_path

        def submit(self, **kwargs):
            calls.append(kwargs)
            return "accepted task_fixture"

        def close(self):
            pass

    fake_discord = SimpleNamespace(
        Intents=SimpleNamespace(default=lambda: SimpleNamespace()),
        AllowedMentions=SimpleNamespace(none=lambda: None), Client=Client, DMChannel=DMChannel,
        utils=SimpleNamespace(setup_logging=lambda: None),
    )
    monkeypatch.setitem(sys.modules, "discord", fake_discord)
    monkeypatch.setattr(discord_bridge, "parse_args", lambda: SimpleNamespace(config=None, check_config=False))
    monkeypatch.setattr(discord_bridge, "load_runtime_config", lambda _: {})
    monkeypatch.setattr(discord_bridge, "NyaNyaConversationStore", ConversationStore)
    if claim_failure:
        def unavailable(**_kwargs):
            raise OSError("synthetic receipt failure")
        monkeypatch.setattr(store, "claim_agent_request" if recording else "find_agent_request_by_message", unavailable)

    async def run_client(client, _token, _store):
        message = SimpleNamespace(id="message", author=SimpleNamespace(id="owner", bot=False, name="fixture"),
                                  channel=Channel(), content="!nyanya " + content, guild=None, mentions=[],
                                  attachments=[Attachment()] if attached else [])
        if concurrent:
            await asyncio.gather(client.on_message(message), client.on_message(message))
        else:
            await client.on_message(message)
            await client.on_message(message)

    monkeypatch.setattr(discord_bridge, "run_client", run_client)
    assert discord_bridge.main() == 0
    return path, calls, sent, downloads, controls


@pytest.mark.parametrize("text", ["What is the timeout in worker.py?", "Explain how timeout works in process_runner.py"])
def test_technical_timeout_question_reaches_model_intake(tmp_path, monkeypatch, text):
    _path, calls, sent, _downloads, controls = run_bridge(tmp_path, monkeypatch, content=text)
    assert len(calls) == 1 and calls[0]["prompt"] == text
    assert sent == ["accepted task_fixture"] and not controls


@pytest.mark.parametrize("recording", [True, False])
@pytest.mark.parametrize("concurrent", [True, False])
@pytest.mark.parametrize("attached", [True, False])
def test_duplicate_bridge_intake_does_not_repeat_attachment_submit_or_ack(
    tmp_path, monkeypatch, recording, concurrent, attached,
):
    path, calls, sent, downloads, controls = run_bridge(
        tmp_path, monkeypatch, recording=recording, concurrent=concurrent, attached=attached,
    )
    assert len(calls) == 1 and sent == ["accepted task_fixture"] and not controls
    assert downloads == (["fixture.txt"] if attached else [])
    with db.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM agent_requests").fetchone()[0] == int(recording)
        receipt = conn.execute("SELECT id FROM agent_requests").fetchone()
    assert calls[0]["request_id"] == (receipt[0] if recording else None)


def test_duplicate_upload_command_schedules_one_external_operation(tmp_path, monkeypatch):
    (tmp_path / "fixture.txt").write_text("synthetic upload fixture")
    _path, calls, sent, downloads, controls = run_bridge(
        tmp_path, monkeypatch, concurrent=True, content="upload fixture.txt",
    )
    assert len(calls) == 1 and calls[0]["mode"] == "upload"
    assert callable(calls[0]["operation"]) and sent == ["accepted task_fixture"]
    assert not downloads and not controls


@pytest.mark.parametrize("recording", [True, False])
def test_duplicate_control_is_not_mutated_or_resent(tmp_path, monkeypatch, recording):
    _path, calls, sent, downloads, controls = run_bridge(tmp_path, monkeypatch, recording=recording, concurrent=True, content="작업목록")
    assert len(controls) == 1 and sent == ["one control response"]
    assert not calls and not downloads


@pytest.mark.parametrize("recording", [True, False])
def test_receipt_failure_fails_closed_before_attachments_and_work(tmp_path, monkeypatch, recording):
    _path, calls, sent, downloads, controls = run_bridge(
        tmp_path, monkeypatch, recording=recording, attached=True, claim_failure=True,
    )
    assert not calls and not downloads and not controls
    assert len(sent) == 2 and all("접수" in text for text in sent)


def test_disabling_recording_does_not_replay_previously_recorded_message(tmp_path, monkeypatch):
    path, calls, sent, downloads, controls = run_bridge(
        tmp_path, monkeypatch, recording=False, existing_recorded=True, attached=True,
    )
    assert not calls and not sent and not downloads and not controls
    with db.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM agent_requests").fetchone()[0] == 1


@pytest.mark.parametrize("fails", [False, True])
def test_unrecorded_lookup_closes_connection_on_success_and_error(tmp_path, monkeypatch, fails):
    path = tmp_path / "existing.db"
    path.write_bytes(b"synthetic fixture")
    class Connection:
        closed = False
        def execute(self, *_args):
            if fails:
                raise OSError("synthetic lookup error")
            return SimpleNamespace(fetchone=lambda: ("req_existing",))
        def close(self):
            self.closed = True
    connection = Connection()
    def readonly(database_uri, **kwargs):
        assert database_uri.endswith("?mode=ro") and kwargs["uri"]
        return connection
    monkeypatch.setattr(store.sqlite3, "connect", readonly)
    values = dict(source="discord", channel_id="channel", user_id="owner", message_id="message", db_path=path)
    if fails:
        with pytest.raises(OSError):
            store.find_agent_request_by_message(**values)
    else:
        assert store.find_agent_request_by_message(**values) == "req_existing"
    assert connection.closed
