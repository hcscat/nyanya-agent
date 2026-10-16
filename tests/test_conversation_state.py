from datetime import UTC, datetime, timedelta
import json

import pytest

from nyanya_agent import conversation_store as conversations, database as db
from nyanya_agent import execution_store as ledger, operation_store as store, work_queue
from nyanya_agent.operation_spec import OperationSpec
from nyanya_agent.task_outcomes import TaskOutcome


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / 'workspace'
    root.mkdir()
    monkeypatch.setenv('NYANYA_WORKSPACE_ROOTS', str(root))
    path = tmp_path / 'conversation.db'
    worker = 'fixture-worker'
    store.register_worker(path, worker)
    return path, root, worker


def add(setup, prompt='request', *, key='channel-one', owner='operator', source=None):
    path, root, worker = setup
    return store.submit(path, OperationSpec(prompt=prompt, workspace=str(root)), owner, worker,
                        conversation_key=key, source_request_id=source)


def complete(setup, text='answer', *, kind='answer', status='succeeded'):
    path, _, worker = setup
    record = store.claim(path, worker)
    assert record
    record['reply_kind'] = kind
    work_queue.finish(path, record, TaskOutcome(status, text))
    return record


def context(setup, task, owner='operator'):
    path, root, _ = setup
    return json.loads(conversations.worker_context(path, task['id'], owner, str(root)))


def test_transactional_bind_duplicate_and_legacy_compatibility(setup):
    path, root, _ = setup
    with db.connect(path) as conn:
        conn.execute("INSERT INTO agent_requests(id,created_at,updated_at) VALUES ('request-one','2026','2026')")
    first = add(setup, 'first', source='request-one')
    duplicate = add(setup, 'first', source='request-one')
    assert duplicate['id'] == first['id']
    with db.connect(path) as conn:
        assert conn.execute('SELECT count(*) FROM conversation_turns').fetchone()[0] == 1
        assert conn.execute('SELECT conversation_hash FROM conversation_sessions').fetchone()[0] != 'channel-one'
        assert conn.execute('SELECT parent_task_id FROM task_operations').fetchone()[0] is None
    with pytest.raises(PermissionError):
        add(setup, source='request-one', key='another-channel')
    legacy = add(setup, key=None)
    assert conversations.worker_context(path, legacy['id'], 'operator', str(root)) == '{}'


def test_failed_bind_rolls_back_task_and_operation(setup, monkeypatch):
    path, _, _ = setup
    def fail(*args, **kwargs):
        raise RuntimeError('fixture')
    monkeypatch.setattr(conversations, 'bind_conn', fail)
    with pytest.raises(RuntimeError):
        add(setup)
    with db.connect(path) as conn:
        assert conn.execute('SELECT count(*) FROM agent_tasks').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM task_operations').fetchone()[0] == 0


def test_same_session_order_and_other_conversation_parallel(setup):
    path, _, worker = setup
    first = add(setup, 'first')
    second = add(setup, 'second')
    other = add(setup, 'another conversation', key='channel-two')
    record = store.claim(path, worker)
    assert record['task_id'] == first['id']
    parallel = store.claim(path, worker)
    assert parallel['task_id'] == other['id']
    assert store.claim(path, worker, slots=3) is None
    work_queue.finish(path, record, TaskOutcome('succeeded', 'first answer'))
    assert store.claim(path, worker, slots=3)['task_id'] == second['id']
    assert context(setup, second)['turns'][0]['response'] == 'first answer'


def test_held_prior_never_resumes_or_blocks_followup(setup):
    path, _, worker = setup
    old = add(setup, 'held original')
    complete(setup, 'requires review', status='blocked')
    new = add(setup, 'new feedback')
    assert store.claim(path, worker)['task_id'] == new['id']
    assert ledger.get_task(old['id'], db_path=path)['status'] == 'blocked'
    assert context(setup, new)['turns'][0]['outcome'] == 'blocked'


def test_owner_channel_workspace_isolation(setup, tmp_path, monkeypatch):
    path, root, worker = setup
    first = add(setup, 'owner-one')
    complete(setup, 'answer-one')
    other = add(setup, owner='other-owner')
    channel = add(setup, key='channel-two')
    assert context(setup, other, owner='other-owner') == {}
    assert context(setup, channel) == {}
    with pytest.raises(PermissionError):
        conversations.worker_context(path, first['id'], 'other-owner', str(root))
    second_root = tmp_path / 'second'
    second_root.mkdir()
    monkeypatch.setenv('NYANYA_WORKSPACE_ROOTS', f'{root},{second_root}')
    separate = store.submit(path, OperationSpec(prompt='separate', workspace=str(second_root)),
                            'operator', worker, conversation_key='channel-one')
    assert conversations.worker_context(path, separate['id'], 'operator', str(second_root)) == '{}'
    with pytest.raises(PermissionError):
        conversations.worker_context(path, first['id'], 'operator', str(second_root))


def test_question_pending_delivery_labels_and_restart(setup):
    path, root, _ = setup
    first = add(setup)
    record = complete(setup, 'Which option?', kind='question')
    saved = json.loads(conversations.snapshot(path, 'operator', 'channel-one', str(root)))
    turn = saved['turns'][0]
    assert turn['reply_kind'] == 'question' and turn['pending_question']
    assert turn['delivery_status'] == 'pending'
    assert store.claim_delivery(path, first['id'], 'operator', record['execution_id'], 1)
    store.settle_delivery(path, record['execution_id'], delivered=False, error='fixture')
    store.register_worker(path, 'restarted-worker')
    saved = json.loads(conversations.snapshot(path, 'operator', 'channel-one', str(root)))
    assert saved['turns'][0]['delivery_status'] == 'uncertain'
    new = add(setup, 'second option')
    assert not context(setup, new)['turns'][0]['pending_question']
    with db.connect(path) as conn:
        related = conn.execute('SELECT related_task_id FROM conversation_turns WHERE task_id=?', (new['id'],)).fetchone()[0]
        assert related == first['id']


def test_reset_while_running_fences_question_without_cancelling(setup):
    path, root, worker = setup
    old = add(setup)
    record = store.claim(path, worker)
    assert conversations.reset(path, 'operator', 'channel-one', str(root)) == 2
    assert ledger.get_task(old['id'], db_path=path)['status'] == 'running'
    new = add(setup, 'fresh conversation')
    assert store.claim(path, worker)['task_id'] == new['id']
    record['reply_kind'] = 'question'
    work_queue.finish(path, record, TaskOutcome('succeeded', 'old question'))
    assert context(setup, new) == {}
    with db.connect(path) as conn:
        row = conn.execute('SELECT * FROM conversation_sessions').fetchone()
        assert row['pending_task_id'] is None
        assert conn.execute('SELECT count(*) FROM task_results').fetchone()[0] == 1


@pytest.mark.parametrize('status', ['cancelled', 'failed', 'blocked'])
def test_only_success_question_can_set_pending(setup, status):
    path, _, _ = setup
    add(setup)
    complete(setup, 'question?', kind='question', status=status)
    with db.connect(path) as conn:
        assert conn.execute('SELECT pending_task_id FROM conversation_sessions').fetchone()[0] is None


def test_stale_completion_rejected_without_conversation_change(setup):
    path, _, worker = setup
    add(setup)
    record = store.claim(path, worker)
    record['reply_kind'] = 'question'
    with db.connect(path) as conn:
        conn.execute("UPDATE task_claims SET expires_at='2000'")
    with pytest.raises(ValueError, match='Stale'):
        work_queue.finish(path, record, TaskOutcome('succeeded', 'late question'))
    with db.connect(path) as conn:
        assert conn.execute('SELECT completed_execution_id FROM conversation_turns').fetchone()[0] is None
        assert conn.execute('SELECT pending_task_id FROM conversation_sessions').fetchone()[0] is None


def test_idle_keeps_channel_history_and_generation(setup):
    path, _, _ = setup
    first = add(setup)
    complete(setup)
    expired = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
    with db.connect(path) as conn:
        conn.execute('UPDATE conversation_turns SET created_at=?', (expired,))
    second = add(setup)
    assert context(setup, second)['turns'][0]['task_id'] == first['id']
    with db.connect(path) as conn:
        conn.execute('UPDATE conversation_sessions SET updated_at=?', (expired,))
    third = add(setup)
    with db.connect(path) as conn:
        row = conn.execute('SELECT generation,sequence,related_task_id FROM conversation_turns WHERE task_id=?', (third['id'],)).fetchone()
        assert tuple(row) == (1, 3, second['id'])
    assert ledger.get_task(first['id'], db_path=path)['status'] == 'completed'


def test_history_latest_eight_bytes_and_sensitive_omission(setup):
    path, root, _ = setup
    for index in range(10):
        add(setup, f'request-{index}')
        complete(setup, f'answer-{index}')
    new = add(setup, 'unrelated followup')
    history = context(setup, new)
    assert len(history['turns']) == 8
    assert history['turns'][0]['request'] == 'request-2'
    assert history['turns'][-1]['response'] == 'answer-9'
    bounded = conversations.worker_context(path, new['id'], 'operator', str(root), max_bytes=500)
    assert len(bounded.encode()) <= 500
    for turn in json.loads(bounded).get('turns', []):
        assert turn['request'].startswith('request-') and turn['response'].startswith('answer-')
    with db.connect(path) as conn:
        conn.execute("UPDATE agent_tasks SET prompt='password=synthetic-private-fixture' WHERE prompt='request-9'")
    assert 'synthetic-private-fixture' not in conversations.worker_context(path, new['id'], 'operator', str(root))
    with db.connect(path) as conn:
        conn.execute('UPDATE task_results SET response=?', ('한' * 20000,))
    assert conversations.worker_context(path, new['id'], 'operator', str(root)) == '{}'


def test_migration_seven_preserves_all_preexisting_rows(setup, monkeypatch, tmp_path):
    path = tmp_path / 'upgrade.db'
    migrations = ledger.MIGRATIONS
    monkeypatch.setattr(ledger, 'MIGRATIONS', migrations[:6])
    task = ledger.create_task(title='preserved', prompt='original', db_path=path)
    with db.connect(path) as conn:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                  if row[0] != 'schema_migrations']
        before = {table: [tuple(row) for row in conn.execute(f'SELECT * FROM "{table}"')] for table in tables}
    monkeypatch.setattr(ledger, 'MIGRATIONS', migrations)
    assert ledger.apply_migrations(path) == ledger.MIGRATIONS[-1][0]
    with db.connect(path) as conn:
        after = {table: [tuple(row) for row in conn.execute(f'SELECT * FROM "{table}"')] for table in tables}
    assert after == before
    assert ledger.get_task(task['id'], db_path=path)['prompt'] == 'original'


def test_cancelling_claim_cannot_publish_pending_question(setup):
    path, _, worker = setup
    task = add(setup)
    record = store.claim(path, worker)
    store.cancel(path, task['id'], 'operator')
    record['reply_kind'] = 'question'
    work_queue.finish(path, record, TaskOutcome('succeeded', 'provider returned a question'))
    assert ledger.get_task(task['id'], db_path=path)['status'] == 'blocked'
    with db.connect(path) as conn:
        assert conn.execute('SELECT pending_task_id FROM conversation_sessions').fetchone()[0] is None


def test_idle_during_running_preserves_order_and_never_replays(setup):
    path, _, worker = setup
    old = add(setup)
    record = store.claim(path, worker)
    expired = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
    with db.connect(path) as conn:
        conn.execute('UPDATE conversation_sessions SET updated_at=?', (expired,))
    new = add(setup, 'after expiry')
    assert store.claim(path, worker) is None
    record['reply_kind'] = 'question'
    work_queue.finish(path, record, TaskOutcome('succeeded', 'expired question'))
    assert ledger.get_task(old['id'], db_path=path)['status'] == 'completed'
    assert context(setup, new)['turns'][0]['response'] == 'expired question'
    assert store.claim(path, worker)['task_id'] == new['id']
    with db.connect(path) as conn:
        assert conn.execute('SELECT pending_task_id FROM conversation_sessions').fetchone()[0] is None


def test_known_secret_and_serialized_context_filter_are_never_disabled(setup, monkeypatch):
    path, root, _ = setup
    add(setup, 'safe request')
    complete(setup, 'unmarked synthetic-provider-value')
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-provider-value')
    task = add(setup, 'feedback')
    assert context(setup, task) == {}
    monkeypatch.delenv('OPENAI_API_KEY')
    original = conversations.sensitive_content
    def final_only(value):
        return value.startswith('{"kind":') or original(value)
    monkeypatch.setattr(conversations, 'sensitive_content', final_only)
    assert conversations.worker_context(path, task['id'], 'operator', str(root)) == '{}'


def test_workspace_registration_checked_again_at_context_read(setup, tmp_path, monkeypatch):
    from nyanya_agent import bridge_policy
    path, root, worker = setup
    config_path = tmp_path / 'registration.json'
    owner = 'discord-user:fixture-owner'
    config_path.write_text(json.dumps({'users': {owner: {'workspace': str(root)}}}))
    monkeypatch.setattr(bridge_policy, 'workspace_config_path', lambda: config_path)
    store.submit(path, OperationSpec(prompt='registered request', workspace=str(root)), owner, worker,
                 conversation_key='fixture-channel')
    complete(setup, 'registered answer')
    task = store.submit(path, OperationSpec(prompt='feedback', workspace=str(root)), owner, worker,
                        conversation_key='fixture-channel')
    assert json.loads(conversations.worker_context(path, task['id'], owner, str(root)))['turns']
    config_path.write_text(json.dumps({'users': {}}))
    with pytest.raises(PermissionError, match='registration'):
        conversations.worker_context(path, task['id'], owner, str(root))


def test_resumed_earlier_turn_waits_for_later_active_turn(setup):
    path, _, worker = setup
    first = add(setup, 'first attempt')
    complete(setup, 'clean failure', status='failed')
    second = add(setup, 'new feedback')
    running = store.claim(path, worker)
    assert running['task_id'] == second['id']
    store.resume(path, first['id'], 'operator', worker)
    assert store.claim(path, worker, slots=3) is None
    other = add(setup, 'independent conversation', key='channel-two')
    parallel = store.claim(path, worker, slots=3)
    assert parallel['task_id'] == other['id']
    assert store.claim(path, worker, slots=3) is None
    work_queue.finish(path, running, TaskOutcome('succeeded', 'feedback answer'))
    assert store.claim(path, worker, slots=3)['task_id'] == first['id']


def test_history_distinguishes_saved_approval_response_from_applied_task(setup):
    from nyanya_agent import reviewed_changes as files
    path, root, worker = setup
    (root / 'note.txt').write_text('before')
    parent = add(setup, 'modify note.txt')
    record = store.claim(path, worker)
    plan = files.propose(
        path, parent['id'], 'operator', root,
        [{'path': 'note.txt', 'action': 'modify', 'content': 'after', 'reason': 'requested change'}],
        files.snapshot(root),
    )
    work_queue.finish(path, record, TaskOutcome('awaiting_approval', files.preview(path, plan['id'], 'operator')))
    files.decide(path, plan['id'], 'operator', plan['plan_hash'])
    applied = store.submit(path, OperationSpec(kind='apply', workspace=str(root), plan_id=plan['id']),
                           'operator', worker)
    claim = store.claim(path, worker)
    assert claim['task_id'] == applied['id']
    files.apply(path, plan['id'], 'operator', record=claim)
    work_queue.finish(path, claim, TaskOutcome('succeeded', 'approved file apply completed'))
    assert (root / 'note.txt').read_text() == 'after'
    feedback = add(setup, 'follow-up after applying')
    turn = context(setup, feedback)['turns'][0]
    assert turn['task_id'] == parent['id']
    assert turn['outcome'] == 'awaiting_approval'
    assert turn['current_task_status'] == 'completed'
    assert turn['current_plan_status'] == 'applied'
    assert turn['delivery_status'] == 'pending'
