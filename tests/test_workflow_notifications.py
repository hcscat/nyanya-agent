"""Notices describe live state without poisoning saved results or restarting work."""

import pytest

from nyanya_agent import database as db, execution_store as ledger, operation_store as store
from nyanya_agent import workflow_notifications as notices, work_queue
from nyanya_agent.operation_spec import OperationSpec
from nyanya_agent.task_outcomes import TaskOutcome
from nyanya_agent import reviewed_changes as files


def failed_task(tmp_path, monkeypatch):
    root = tmp_path / 'workspace'
    root.mkdir()
    path = tmp_path / 'state.db'
    monkeypatch.setenv('NYANYA_WORKSPACE_ROOTS', str(root))
    store.register_worker(path, 'worker')
    task = store.submit(path, OperationSpec(workspace=str(root), prompt='inspect'), 'operator', 'worker')
    record = store.claim(path, 'worker')
    store.finish(path, record, TaskOutcome('failed', 'provider unavailable'))
    return path, root, task


def test_receipt_survives_new_preparation_and_does_not_hide_explicit_list(tmp_path, monkeypatch):
    path, _, task = failed_task(tmp_path, monkeypatch)
    first = notices.prepare(path, 'operator')
    assert first and task['id'] in first.text
    # Preparing alone must not acknowledge a failed/unsent notification.
    assert notices.prepare(path, 'operator') == first
    notices.delivered(path, first)
    assert notices.prepare(path, 'operator') is None
    assert store.incomplete(path, 'operator')[0]['id'] == task['id']
    assert notices.prepare(path, 'other') is None
    assert work_queue.result(path, task['id'], 'operator')['response'] == 'provider unavailable'
    with db.connect(path) as conn:
        conn.execute("UPDATE task_operations SET attempts=attempts+1 WHERE task_id=?", (task['id'],))
    assert notices.prepare(path, 'operator') is not None


def test_control_audit_never_becomes_legacy_task_on_restart(tmp_path):
    path = tmp_path / 'state.db'
    ledger.apply_migrations(path)
    with db.connect(path) as conn:
        for mode in ['control', 'access_control', 'ignored']:
            conn.execute(
                'INSERT INTO agent_requests(id,mode,created_at,updated_at) VALUES(?,?,?,?)',
                (mode, mode, ledger.now_iso(), ledger.now_iso()),
            )
    for mode in ['control', 'access_control', 'ignored']:
        assert ledger.mirror_legacy_request(mode, db_path=path) is None
    assert ledger.reconcile_legacy_requests(db_path=path) == {'scanned': 0, 'synchronized': 0}
    with db.connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM agent_tasks').fetchone()[0] == 0


def test_revocation_before_worker_finish_cannot_restore_approval_wait(tmp_path, monkeypatch):
    path, root, _ = failed_task(tmp_path, monkeypatch)
    (root / 'note.txt').write_text('before')
    task = store.submit(path, OperationSpec(workspace=str(root), prompt='review'), 'operator', 'worker')
    record = store.claim(path, 'worker')
    plan = files.propose(path, task['id'], 'operator', root,
                         [{'path': 'note.txt', 'action': 'modify', 'content': 'after', 'reason': 'review'}],
                         files.snapshot(root))
    files.decide(path, plan['id'], 'operator', revoke=True)
    store.finish(path, record, TaskOutcome('awaiting_approval', 'obsolete review'))
    assert ledger.get_task(task['id'], db_path=path)['status'] != 'awaiting_approval'
    with db.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM approvals WHERE task_id=? AND status='pending'",
                            (task['id'],)).fetchone()[0] == 0
    assert (root / 'note.txt').read_text() == 'before'


def test_api_query_does_not_create_work_or_start_model(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from nyanya_agent.dashboard_api import create_app
    from nyanya_agent.operation_service import OperationService

    monkeypatch.setenv('NYANYA_DASHBOARD_CONTROL_TOKEN', 'fixture-control')
    monkeypatch.setattr(OperationService, 'ensure_worker', lambda _: (_ for _ in ()).throw(AssertionError('worker started')))
    path = tmp_path / 'api.db'
    client = TestClient(create_app(path), base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
    response = client.post('/v1/operations', json={'prompt': '남은 작업은 무엇인가?', 'workspace': str(tmp_path)},
                           headers={'X-Nyanya-Control-Token': 'fixture-control'})
    assert response.status_code == 201
    assert response.json()['kind'] == 'control'
    assert ledger.list_tasks(db_path=path) == []


def test_approval_before_result_commit_does_not_leave_pending_feedback(tmp_path, monkeypatch):
    path, root, _ = failed_task(tmp_path, monkeypatch)
    (root / 'note.txt').write_text('before')
    task = store.submit(path, OperationSpec(workspace=str(root), prompt='review'), 'operator', 'worker')
    record = store.claim(path, 'worker')
    plan = files.propose(path, task['id'], 'operator', root,
                         [{'path': 'note.txt', 'action': 'modify', 'content': 'after', 'reason': 'review'}],
                         files.snapshot(root))
    files.decide(path, plan['id'], 'operator', plan['plan_hash'])
    store.finish(path, record, TaskOutcome('awaiting_approval', 'review'))
    with db.connect(path) as conn:
        row = conn.execute('SELECT status,decided_by FROM approvals WHERE task_id=?', (task['id'],)).fetchone()
        assert tuple(row) == ('approved', 'operator')


def test_api_cancel_stops_owned_adapter_process(tmp_path, monkeypatch):
    import sys
    from fastapi.testclient import TestClient
    from nyanya_agent import execution_adapters as adapters, execution_runtime
    from nyanya_agent.dashboard_api import create_app

    monkeypatch.setenv('NYANYA_DASHBOARD_CONTROL_TOKEN', 'fixture-control')
    monkeypatch.setattr(adapters, 'is_allowed_workspace_path', lambda _: True)
    path = tmp_path / 'adapter.db'
    task = ledger.create_task(title='owned adapter', db_path=path)
    adapter = adapters.ManagedSubprocessAdapter()
    execution = ledger.create_execution(task_id=task['id'], adapter_type='subprocess',
                                         status='starting', db_path=path)
    handle = adapter.start(adapters.AdapterRequest(
        execution_id=execution['id'], command=(sys.executable, '-c', 'import time; time.sleep(30)'),
        cwd=tmp_path, output_dir=tmp_path / execution['id'],
    ))
    ledger.heartbeat_runtime_session(
        session_id=f"runtime_{execution['id']}", execution_id=execution['id'],
        adapter_type='subprocess', external_id=handle.external_id, status='running',
        pid=handle.pid, metadata={'handle': handle.to_dict()}, db_path=path,
    )
    execution = ledger.transition_execution(execution['id'], 'running', db_path=path)
    coordinator = execution_runtime.ExecutionCoordinator(db_path=path, adapters={'subprocess': adapter})
    app = create_app(path)
    app.state.execution_coordinator = coordinator
    try:
        response = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)).post(
            f"/v1/executions/{execution['id']}/cancel", json={},
            headers={'X-Nyanya-Control-Token': 'fixture-control'},
        )
        assert response.status_code == 200
        assert response.json()['status'] == 'cancelled'
        assert ledger.list_runtime_sessions(db_path=path)[0]['status'] == 'cancelled'
        assert ledger.get_task(task['id'], db_path=path)['status'] == 'cancelled'
    finally:
        coordinator.cancel(execution['id'])
        adapter.cancel(handle)


def test_worker_maintenance_repeats_after_startup(tmp_path, monkeypatch):
    from nyanya_agent.operation_worker import Worker

    worker = Worker(tmp_path / 'worker.db', 'fixture')
    clock = iter([0, 0, 31, 31])
    monkeypatch.setattr('nyanya_agent.operation_worker.time.monotonic', lambda: next(clock))
    calls = []

    def maintenance(path):
        calls.append(path)
        if len(calls) == 2:
            worker.stop.set()

    monkeypatch.setattr(files, 'settle_expired', maintenance)
    worker.run()
    assert len(calls) == 2


def queued_task(tmp_path, monkeypatch):
    root = tmp_path / 'workspace'
    root.mkdir()
    path = tmp_path / 'state.db'
    monkeypatch.setenv('NYANYA_WORKSPACE_ROOTS', str(root))
    store.register_worker(path, 'worker')
    task = store.submit(path, OperationSpec(workspace=str(root), prompt='fresh normal request'),
                        'operator', 'worker')
    return path, root, task


@pytest.mark.parametrize('status', ['queued', 'running', 'cancelling'])
def test_live_work_is_not_a_background_recovery_notice(tmp_path, monkeypatch, status):
    path, _, task = queued_task(tmp_path, monkeypatch)
    if status != 'queued':
        store.claim(path, 'worker')
    if status == 'cancelling':
        assert store.cancel(path, task['id'], 'operator') == 'cancelling'
    assert store.recovery_inventory(path) == []
    assert notices.prepare(path, 'operator') is None
    # Explicit user-requested task queries retain every active lifecycle state.
    listed = store.incomplete(path, 'operator')
    assert len(listed) == 1 and listed[0]['id'] == task['id'] and listed[0]['status'] == status
    assert task['id'] in store.reminder(path, 'operator')


def test_other_completion_notice_excludes_active_work_and_dedupes_revision(tmp_path, monkeypatch):
    path, root, failed = failed_task(tmp_path, monkeypatch)
    active = store.submit(path, OperationSpec(workspace=str(root), prompt='still working'), 'operator', 'worker')
    store.claim(path, 'worker')
    queued = store.submit(path, OperationSpec(workspace=str(root), prompt='waiting for worker'), 'operator', 'worker')
    completed = store.submit(path, OperationSpec(workspace=str(root), prompt='independent completion'), 'operator', 'worker')
    record = store.claim(path, 'worker')
    assert record['task_id'] == queued['id']
    store.finish(path, record, TaskOutcome('succeeded', 'done'))
    record = store.claim(path, 'worker')
    assert record['task_id'] == completed['id']
    store.finish(path, record, TaskOutcome('succeeded', 'done'))
    pending = store.submit(path, OperationSpec(workspace=str(root), prompt='another queued request'), 'operator', 'worker')
    first = notices.prepare(path, 'operator', exclude=completed['id'])
    assert first and failed['id'] in first.text
    assert active['id'] not in first.text and pending['id'] not in first.text
    assert {row['id'] for row in store.incomplete(path, 'operator')} == {failed['id'], active['id'], pending['id']}
    notices.delivered(path, first)
    assert notices.prepare(path, 'operator', exclude=completed['id']) is None
    # Another eligible queue entry does not change the actionable-notice revision.
    store.submit(path, OperationSpec(workspace=str(root), prompt='more queued work'), 'operator', 'worker')
    assert notices.prepare(path, 'operator') is None


@pytest.mark.parametrize('status', ['running', 'cancelling'])
def test_expired_claim_and_recovered_hold_remain_actionable(tmp_path, monkeypatch, status):
    path, _, task = queued_task(tmp_path, monkeypatch)
    store.claim(path, 'worker')
    if status == 'cancelling':
        store.cancel(path, task['id'], 'operator')
    with db.connect(path) as conn:
        conn.execute("UPDATE task_claims SET expires_at='2000-01-01T00:00:00+00:00' WHERE task_id=?", (task['id'],))
    assert task['id'] in notices.prepare(path, 'operator').text
    assert store.recover(path) == 1
    assert ledger.get_task(task['id'], db_path=path)['status'] == 'blocked'
    assert task['id'] in notices.prepare(path, 'operator').text


@pytest.mark.parametrize('failure', ['worker_closed', 'queue_held', 'exhausted_attempts', 'claim_released', 'execution_lost'])
def test_background_filter_does_not_hide_held_or_lost_work(tmp_path, monkeypatch, failure):
    path, _, task = queued_task(tmp_path, monkeypatch)
    if failure in {'claim_released', 'execution_lost'}:
        record = store.claim(path, 'worker')
    with db.connect(path) as conn:
        if failure == 'worker_closed':
            conn.execute("UPDATE operation_workers SET closed=1 WHERE id='worker'")
        elif failure == 'queue_held':
            conn.execute("UPDATE task_operations SET eligible=0,hold_reason='held' WHERE task_id=?", (task['id'],))
        elif failure == 'exhausted_attempts':
            conn.execute("UPDATE task_operations SET attempts=max_attempts WHERE task_id=?", (task['id'],))
        elif failure == 'claim_released':
            conn.execute("UPDATE task_claims SET released=1 WHERE task_id=?", (task['id'],))
        else:
            conn.execute("UPDATE executions SET status='lost' WHERE id=?", (record['execution_id'],))
    if failure == 'exhausted_attempts':
        assert store.has_queued(path, 'worker') is False
    assert task['id'] in notices.prepare(path, 'operator').text
    assert [row['id'] for row in store.recovery_inventory(path)] == [task['id']]


def test_completed_uncertain_delivery_is_periodic_candidate_without_other_holds(tmp_path, monkeypatch):
    path, _, task = queued_task(tmp_path, monkeypatch)
    record = store.claim(path, 'worker')
    store.finish(path, record, TaskOutcome('succeeded', 'answer'))
    with db.connect(path) as conn:
        conn.execute("UPDATE task_results SET delivery_status='uncertain' WHERE execution_id=?", (record['execution_id'],))
    assert store.incomplete(path, 'operator') == []
    assert [row['id'] for row in store.recovery_inventory(path)] == [task['id']]
    first = notices.prepare(path, 'operator')
    assert first and task['id'] in first.text and '결과 전달 확인 필요' in first.text
    notices.delivered(path, first)
    assert notices.prepare(path, 'operator') is None
    assert store.acknowledge_delivery(path, task['id'], 'operator') == 'acknowledged'
    assert store.recovery_inventory(path) == []


def test_dismissed_failure_is_not_a_periodic_notice_candidate(tmp_path, monkeypatch):
    path, _, task = failed_task(tmp_path, monkeypatch)
    store.dismiss(path, task['id'], 'operator')
    assert store.recovery_inventory(path) == []
    assert notices.prepare(path, 'operator') is None


def test_legacy_claimed_running_work_is_not_mislabeled_as_recovery(tmp_path):
    path = tmp_path / 'state.db'
    task = ledger.create_task(title='legacy current request', requested_by='request-origin',
                              metadata={'owner_key': 'operator'}, db_path=path)
    record = work_queue.claim(path, task['id'], 'legacy-worker', 'operator')
    assert record is not None
    assert store.recovery_inventory(path) == []
    assert notices.prepare(path, 'operator') is None
    with db.connect(path) as conn:
        conn.execute("UPDATE task_claims SET expires_at='2000-01-01T00:00:00+00:00' WHERE task_id=?", (task['id'],))
    assert task['id'] in notices.prepare(path, 'operator').text
    assert notices.prepare(path, 'request-origin') is None


def test_notice_fields_and_actionability_share_one_task_snapshot(tmp_path, monkeypatch):
    path, _, task = failed_task(tmp_path, monkeypatch)

    def forbidden_second_read(*args, **kwargs):
        pytest.fail('Background notice mixed a candidate snapshot with another task-state read')

    monkeypatch.setattr(store, 'incomplete', forbidden_second_read)
    monkeypatch.setattr(store, 'delivery_issues', forbidden_second_read)
    notice = notices.prepare(path, 'operator')
    assert notice and task['id'] in notice.text
