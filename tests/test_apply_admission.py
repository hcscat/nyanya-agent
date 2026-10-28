"""Cross-process repeat approval and crash rollback at the admission boundary."""

from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import multiprocessing
import os

import pytest

from nyanya_agent import database as db, operation_store as store, reviewed_changes as files
from nyanya_agent.operation_spec import OperationSpec
from nyanya_agent.task_outcomes import SafeOperationError


@pytest.fixture
def plan(tmp_path, monkeypatch):
    root = tmp_path / 'workspace'
    root.mkdir()
    monkeypatch.setenv('NYANYA_WORKSPACE_ROOTS', str(root))
    path = tmp_path / 'state.db'
    store.register_worker(path, 'worker')
    task = store.submit(path, OperationSpec(prompt='update note', workspace=str(root)), 'operator', 'worker')
    (root / 'note.txt').write_text('before')
    baseline = files.snapshot(root, 'note.txt')
    proposal = files.propose(path, task['id'], 'operator', root,
                             [{'path': 'note.txt', 'action': 'modify', 'content': 'after', 'reason': 'fix'}], baseline)
    return str(path), proposal['id'], proposal['plan_hash'], 'worker'


def approve(args):
    path, plan_id, digest, worker = args
    return store.approve_and_submit_apply(path, plan_id, 'operator', digest, worker)


@pytest.mark.parametrize('processes', [False, True])
def test_concurrent_approval_admits_one_child_and_one_decision(plan, processes):
    executor = ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context('spawn')) if processes else ThreadPoolExecutor(max_workers=2)
    with executor as pool:
        results = list(pool.map(approve, [plan, plan]))
    assert len({task['id'] for task, _ in results}) == 1
    assert sorted(created for _, created in results) == [False, True]
    with db.connect(plan[0]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM task_operations WHERE json_extract(spec_json,'$.kind')='apply'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM execution_events WHERE event_type='plan.approved'").fetchone()[0] == 1


def test_completed_repeat_is_a_read_and_rechecks_hash_owner(plan):
    first, _ = approve(plan)
    with db.connect(plan[0]) as conn:
        conn.execute("UPDATE agent_tasks SET status='completed' WHERE id=?", (first['id'],))
        conn.execute("UPDATE change_plans SET status='applied',expires_at='2000' WHERE id=?", (plan[1],))
        before = conn.execute('SELECT COUNT(*) FROM execution_events').fetchone()[0]
    again, created = approve(plan)
    assert again['id'] == first['id'] and not created
    for owner, digest in [('other-owner', plan[2]), ('operator', 'wrong-hash')]:
        with pytest.raises(SafeOperationError):
            store.approve_and_submit_apply(plan[0], plan[1], owner, digest, plan[3])
    with db.connect(plan[0]) as conn:
        assert conn.execute('SELECT COUNT(*) FROM execution_events').fetchone()[0] == before


def crash_after_approval(args):
    original = files.decide_conn
    def crash(*values):
        original(*values)
        os._exit(73)
    files.decide_conn = crash
    approve(args)


def test_process_death_after_approval_rolls_back_admission(plan):
    process = multiprocessing.get_context('spawn').Process(target=crash_after_approval, args=(plan,))
    process.start()
    process.join(timeout=10)
    if process.is_alive():
        process.kill()
        process.join()
        pytest.fail('Synthetic crash process did not terminate')
    assert process.exitcode == 73
    with db.connect(plan[0]) as conn:
        assert conn.execute('SELECT status FROM change_plans WHERE id=?', (plan[1],)).fetchone()[0] == 'pending'
        assert conn.execute('SELECT COUNT(*) FROM task_operations').fetchone()[0] == 1
    assert approve(plan)[1]


def test_worker_failure_rolls_back_approval_and_legacy_duplicate_is_held(plan):
    with pytest.raises(SafeOperationError, match='Worker not ready'):
        approve((*plan[:3], 'missing-worker'))
    assert files.get_plan(plan[0], plan[1], 'operator')['status'] == 'pending'
    first, _ = approve(plan)
    with db.connect(plan[0]) as conn:
        conn.execute("INSERT INTO agent_tasks(id,source_request_id,title,prompt,requested_by,status,current_execution_id,project_id,metadata_json,created_at,updated_at,completed_at) SELECT 'task_duplicate',source_request_id,title,prompt,requested_by,status,current_execution_id,project_id,metadata_json,created_at,updated_at,completed_at FROM agent_tasks WHERE id=?", (first['id'],))
        conn.execute("INSERT INTO task_operations(task_id,spec_json,worker_generation,parent_task_id) SELECT 'task_duplicate',spec_json,worker_generation,parent_task_id FROM task_operations WHERE task_id=?", (first['id'],))
    with pytest.raises(SafeOperationError, match='legacy'):
        approve(plan)
    with db.connect(plan[0]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM task_operations WHERE json_extract(spec_json,'$.kind')='apply'").fetchone()[0] == 2
