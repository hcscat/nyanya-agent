"""Synthetic end-to-end upload callback: fake SDK, no network or models."""
import asyncio
import re
import sys
import threading
from types import SimpleNamespace
import pytest
from nyanya_agent import discord_bridge, dashboard_store as db

def bridge(tmp_path, monkeypatch, scenario, *, content='Synthetic ordinary document', filename='reports/note.txt'):
    target = tmp_path / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    path = tmp_path / 'state.db'
    db.init_db(path)
    monkeypatch.setenv('NYANYA_DISCORD_BOT_TOKEN', 'synthetic-fixture')
    monkeypatch.setenv('NYANYA_DISCORD_PREFIX', '!nyanya')
    monkeypatch.setenv('NYANYA_ALLOW_UNLISTED', 'true')
    monkeypatch.setenv('NYANYA_DISCORD_FILE_SHARE_CHANNEL_IDS', '')
    monkeypatch.setenv('NYANYA_DISCORD_FILE_SHARE_CHANNEL_NAMES', '')
    monkeypatch.setenv('NYANYA_DASHBOARD_DB_PATH', str(path))
    monkeypatch.setenv('NYANYA_WORKSPACE_ROOTS', str(tmp_path))
    sent = []
    files = []
    calls = []
    events = []
    results = []
    workspace_errors = []

    class Channel:
        id = '100'
        name = 'synthetic'
        guild = SimpleNamespace(id='10', filesize_limit=8 * 1024 * 1024)

        async def send(self, text=None, *, content=None, file=None):
            if file is not None:
                files.append((file.filename, file.fp.read()))
            else:
                sent.append(text if text is not None else content)
    channel = Channel()

    class File:

        def __init__(self, fp, filename):
            self.fp = fp
            self.filename = filename

    class Client:
        user = None

        def __init__(self, **kwargs):
            pass

        def event(self, f):
            setattr(self, f.__name__, f)
            return f

    class Store:

        def __init__(self, config):
            self.operations = SimpleNamespace(path=path, handle_intent=lambda *a, **k: 'generic control')

        def execution_workspace(self, owner):
            if workspace_errors:
                from nyanya_agent.task_outcomes import OutcomeSignal
                raise OutcomeSignal("blocked", workspace_errors[-1])
            return tmp_path

        def submit(self, **kwargs):
            calls.append(kwargs)
            return 'accepted synthetic task'

        def _dashboard_event(self, *a, **k):
            events.append((a, k))

        def close(self):
            pass
    fake = SimpleNamespace(Intents=SimpleNamespace(default=lambda: SimpleNamespace()), AllowedMentions=SimpleNamespace(none=lambda: None), Client=Client, DMChannel=type('DM', (), {}), File=File, utils=SimpleNamespace(setup_logging=lambda: None))
    monkeypatch.setitem(sys.modules, 'discord', fake)
    monkeypatch.setattr(discord_bridge, 'parse_args', lambda: SimpleNamespace(config=None, check_config=False))
    monkeypatch.setattr(discord_bridge, 'load_runtime_config', lambda _: {})
    monkeypatch.setattr(discord_bridge, 'NyaNyaConversationStore', Store)

    async def run(client, token, store):
        counter = 0
        done = 0

        async def execute():
            nonlocal done
            while done < len(calls):
                op = calls[done]['operation']
                done += 1
                try:
                    results.append(await asyncio.to_thread(op, SimpleNamespace(id='synthetic'), threading.Event()))
                except Exception as e:
                    results.append(type(e).__name__)

        async def request(text, owner='owner', execute_now=True):
            nonlocal counter
            counter += 1
            m = SimpleNamespace(id=str(counter), author=SimpleNamespace(id=owner, bot=False, name='fixture'), channel=channel, content='!nyanya ' + text, guild=channel.guild, mentions=[], attachments=[])
            await client.on_message(m)
            if execute_now:
                await execute()

        def approval():
            text = '\n'.join((str(x) for x in sent))
            match = re.search('upload-approve\\s+(\\S+)\\s+([0-9a-f]{64})', text)
            assert match, text
            return (match.group(1), match.group(2))
        state = SimpleNamespace(request=request, execute=execute, approval=approval, sent=sent, files=files, calls=calls, results=results, target=target, channel=channel, path=path, workspace_errors=workspace_errors)
        await scenario(state)
    monkeypatch.setattr(discord_bridge, 'run_client', run)
    assert discord_bridge.main() == 0
    return (sent, files, calls, results)

def test_document_without_pii_is_inspected_and_sent(tmp_path, monkeypatch):

    async def scenario(s):
        await s.request('upload reports/note.txt')
        assert s.files == [('note.txt', b'Synthetic ordinary document')]
    bridge(tmp_path, monkeypatch, scenario)

def test_pii_requires_exact_original_requester_confirmation_once(tmp_path, monkeypatch):

    async def scenario(s):
        await s.request('upload reports/note.txt')
        assert not s.files
        ident, digest = s.approval()
        assert 'fixture.person@example.invalid' not in '\n'.join(s.sent)
        await s.request(f'upload-approve {ident} {digest}', owner='other')
        assert not s.files
        await s.request(f'upload-approve {ident} {digest}')
        assert len(s.files) == 1
        await s.request(f'upload-approve {ident} {digest}')
        assert len(s.files) == 1
    bridge(tmp_path, monkeypatch, scenario, content='Email: fixture.person@example.invalid')


@pytest.mark.parametrize("phase", ["inspection", "confirmation"])
@pytest.mark.parametrize("reason", [
    "등록된 사용자 작업공간이 없습니다. 관리자가 홈워크스페이스를 등록한 뒤 다시 요청하세요.",
    "등록된 작업공간이 없거나 디렉터리가 아닙니다.",
])
def test_workspace_prerequisite_failure_is_reported_and_recorded(tmp_path, monkeypatch, phase, reason):
    async def scenario(s):
        if phase == "confirmation":
            await s.request('upload reports/note.txt')
            ident, digest = s.approval()
        s.workspace_errors.append(reason)
        command = f'upload-approve {ident} {digest}' if phase == "confirmation" else 'upload reports/note.txt'
        await s.request(command)
        assert s.sent[-1] == reason
        assert not s.files and not s.calls
        with db.connect(s.path) as conn:
            row = conn.execute("SELECT status,mode FROM agent_requests ORDER BY rowid DESC LIMIT 1").fetchone()
            assert row["status"] == "blocked"
            assert row["mode"] == ("control" if phase == "confirmation" else "upload")
            if phase == "confirmation":
                assert conn.execute("SELECT status FROM approvals WHERE id=?", (ident,)).fetchone()[0] == "pending"

    bridge(tmp_path, monkeypatch, scenario, content='Email: fixture.person@example.invalid')

@pytest.mark.parametrize('decision', ['upload-reject', 'upload-cancel'])
def test_decline_or_cancel_prevents_queued_confirmation_send(tmp_path, monkeypatch, decision):

    async def scenario(s):
        await s.request('upload reports/note.txt')
        ident, digest = s.approval()
        await s.request(f'upload-approve {ident} {digest}', execute_now=False)
        await s.request(f'{decision} {ident}')
        await s.execute()
        assert not s.files
    bridge(tmp_path, monkeypatch, scenario, content='Email: fixture.person@example.invalid')

@pytest.mark.parametrize('change', ['bytes', 'replace', 'destination', 'hash'])
def test_confirmation_binding_changes_send_nothing(tmp_path, monkeypatch, change):

    async def scenario(s):
        await s.request('upload reports/note.txt')
        ident, digest = s.approval()
        if change == 'bytes':
            s.target.write_text('changed public content')
        elif change == 'replace':
            content = s.target.read_bytes()
            s.target.unlink()
            s.target.write_bytes(content)
        elif change == 'destination':
            s.channel.guild = SimpleNamespace(id='11', filesize_limit=8 * 1024 * 1024)
        else:
            digest = '0' * 64
        await s.request(f'upload-approve {ident} {digest}')
        assert not s.files
    bridge(tmp_path, monkeypatch, scenario, content='Email: fixture.person@example.invalid')

def test_credential_does_not_offer_pii_override(tmp_path, monkeypatch):

    async def scenario(s):
        await s.request('upload reports/note.txt')
        assert not s.files
        assert 'upload-approve' not in '\n'.join(s.sent)
        assert 'synthetic-private' not in '\n'.join(s.sent)
    bridge(tmp_path, monkeypatch, scenario, content='API_KEY=synthetic-private-value')

def test_expired_confirmation_sends_nothing(tmp_path, monkeypatch):

    async def scenario(s):
        await s.request('upload reports/note.txt')
        ident, digest = s.approval()
        with db.connect(s.path) as conn:
            conn.execute("UPDATE approvals SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?", (ident,))
        await s.request(f'upload-approve {ident} {digest}')
        assert not s.files
    bridge(tmp_path, monkeypatch, scenario, content='Email: fixture.person@example.invalid')
