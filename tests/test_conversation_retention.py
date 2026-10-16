"""Persistent channel recall without granting new file scope or permissions."""

from datetime import UTC, datetime, timedelta
import json

import pytest

from nyanya_agent import conversation_store as history, database as db
from nyanya_agent import operation_store as store, work_queue
from nyanya_agent.operation_spec import OperationSpec
from nyanya_agent.task_outcomes import TaskOutcome


@pytest.fixture
def state(tmp_path, monkeypatch):
    root = tmp_path / 'workspace'
    root.mkdir()
    monkeypatch.setenv('NYANYA_WORKSPACE_ROOTS', str(root))
    path = tmp_path / 'state.db'
    store.register_worker(path, 'worker')
    return path, root


def add(state, prompt, channel='channel-one', owner='operator'):
    path, root = state
    return store.submit(path, OperationSpec(prompt=prompt, workspace=str(root)), owner, 'worker',
                        conversation_key=channel)


def done(state, response):
    record = store.claim(state[0], 'worker')
    work_queue.finish(state[0], record, TaskOutcome('succeeded', response))


def context(state, current):
    return json.loads(history.worker_context(state[0], current['id'], 'operator', state[1]))


def test_old_matching_turn_is_recalled_beyond_latest_eight_and_twenty_four_hours(state):
    old = add(state, '캐시 정책을 정하자')
    done(state, '캐시 보존 기간은 일주일이다.')
    with db.connect(state[0]) as conn:
        expired = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        conn.execute('UPDATE conversation_turns SET created_at=?', (expired,))
        conn.execute('UPDATE conversation_sessions SET updated_at=?', (expired,))
    for index in range(80):
        add(state, f'별도 내용 {index}')
        done(state, '확인했다')
    current = add(state, '캐시 정책 기억나?')
    value = context(state, current)
    recalled = [item for item in value['turns'] if item['task_id'] == old['id']]
    assert recalled[0]['response'] == '캐시 보존 기간은 일주일이다.'
    assert recalled[0]['context_source'] == 'related_earlier_turn'
    assert len(value['turns']) <= history.MAX_TOTAL_TURNS


@pytest.mark.parametrize('response', ['api_key="synthetic-secret-value"', '한' * 25000])
def test_older_recall_still_omits_sensitive_or_oversized_turns(state, response):
    old = add(state, 'cache old answer')
    done(state, response)
    for index in range(9):
        add(state, f'별도 내용 {index}')
        done(state, '확인했다')
    current = add(state, 'cache 다시 확인')
    value = context(state, current)
    assert all(turn['task_id'] != old['id'] for turn in value['turns'])
    assert len(json.dumps(value, ensure_ascii=False).encode()) < history.MAX_CONTEXT_BYTES


def test_recall_excludes_other_channel_owner_and_reset_boundary(state):
    for channel, owner in [('channel-two', 'operator'), ('channel-one', 'other-owner')]:
        add(state, 'cache excluded', channel, owner)
        done(state, 'private other scope')
    old = add(state, 'cache before reset')
    done(state, 'old decision')
    history.reset(state[0], 'operator', 'channel-one', state[1])
    current = add(state, 'cache now')
    assert context(state, current) == {}
    with db.connect(state[0]) as conn:
        assert conn.execute('SELECT 1 FROM agent_tasks WHERE id=?', (old['id'],)).fetchone()


def test_legacy_idle_generations_remain_recallable_but_explicit_reset_does_not(state):
    old = add(state, 'cache old idle generation')
    done(state, 'old answer')
    with db.connect(state[0]) as conn:
        conn.execute('UPDATE conversation_sessions SET generation=2,next_sequence=1')
    current = add(state, 'cache followup')
    assert context(state, current)['turns'][0]['task_id'] == old['id']
    history.reset(state[0], 'operator', 'channel-one', state[1])
    fresh = add(state, 'cache after explicit reset')
    assert context(state, fresh) == {}


def test_terminal_submits_current_prompt_and_uses_separate_private_history(state, monkeypatch):
    from nyanya_agent import core, operation_service, bridge_policy
    from nyanya_agent.operation_worker import Worker

    path, root = state
    service = operation_service.OperationService(path, generation='worker')
    def model(_profile, prompt, *_):
        return json.dumps({'importance': 1, 'impact': 1, 'complexity': 1}) if prompt.startswith('Return only JSON') else json.dumps({'summary': 'done', 'changes': []})
    worker = Worker(path, generation='terminal-worker', invoke=model)
    service.generation = worker.generation
    monkeypatch.setattr(service, 'ensure_worker', lambda: worker.generation)
    real_wait = service.wait
    monkeypatch.setattr(service, 'wait', lambda task_id, owner: (worker.run_once(), real_wait(task_id, owner))[1])
    monkeypatch.setattr(operation_service, 'OperationService', lambda: service)
    monkeypatch.setattr(bridge_policy, 'default_codex_workdir', lambda: root)
    inputs = iter(['old-note.md 검토', '파일 읽기 없이 간단히 답변', '/save', '/reset', '/exit'])
    monkeypatch.setattr('builtins.input', lambda _: next(inputs))
    assert core.run_repl({'save_transcripts': True, 'sessions_dir': str(root / 'exports')}) == 0
    worker.close()
    with db.connect(path) as conn:
        prompts = [json.loads(row[0])['prompt'] for row in conn.execute('SELECT spec_json FROM task_operations ORDER BY rowid')]
        assert prompts == ['old-note.md 검토', '파일 읽기 없이 간단히 답변']
        assert conn.execute('SELECT COUNT(*) FROM conversation_turns').fetchone()[0] == 2
        assert conn.execute('SELECT generation FROM conversation_sessions').fetchone()[0] == 2
    exports = [file.read_text() for file in (root / 'exports').iterdir()]
    assert any('old-note.md' in value for value in exports)
    assert '{}' in exports
