"""Synthetic, isolated contracts for one-use Discord document confirmation."""
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
import multiprocessing
import pytest
from nyanya_agent import database as db, execution_store as ledger, upload_approval as uploads
from nyanya_agent.task_outcomes import SafeOperationError
NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
IDENTITY = {'dev': 1, 'ino': 2, 'size': 31, 'mtime_ns': 4, 'ctime_ns': 5}
DIGEST = 'a' * 64

@pytest.fixture
def pending(tmp_path):
    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    path = tmp_path / 'state.db'
    args = dict(owner_key='discord-user:fixture', conversation_key='discord:source:user:fixture', workspace=str(workspace), relative_path='reports/fixture.txt', destination_id='destination', request_channel_id='source', sha256=DIGEST, file_identity=dict(IDENTITY), counts={'email': 2, 'phone': 1}, now=NOW)
    row = uploads.request_upload(path, **args)
    return (path, args, row)

def consume_args(args, **changes):
    values = {key: args[key] for key in ('owner_key', 'conversation_key', 'sha256', 'destination_id', 'workspace', 'relative_path', 'file_identity', 'now')}
    return {**values, **changes}

def lookup(path, args, row):
    return uploads.get_upload(path, row['id'], owner_key=args['owner_key'], conversation_key=args['conversation_key'])

def test_pending_upload_reuses_approval_schema_without_task_or_generic_feedback(pending):
    path, args, row = pending
    assert row['action'] == 'discord.upload.pii' and row['status'] == 'pending'
    assert row['task_id'] is None and row['execution_id'] is None
    assert row['expires_at'] == (NOW + timedelta(seconds=300)).isoformat()
    metadata = lookup(path, args, row)['metadata']
    assert metadata['authorized_actor'] == args['owner_key']
    assert metadata['sha256'] == DIGEST and metadata['counts'] == args['counts']
    assert metadata['destination_id'] == args['destination_id']
    assert metadata['request_channel_id'] == args['request_channel_id']
    assert metadata['file_identity'] == IDENTITY and metadata['phase'] == 'pending'
    with db.connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM agent_tasks').fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM approvals WHERE action='feedback.review'").fetchone()[0] == 0

def test_upload_consumption_is_single_use_and_keeps_only_scoped_metadata(pending):
    path, args, row = pending
    consumed = uploads.consume_upload(path, row['id'], **consume_args(args))
    assert consumed['status'] == 'approved' and consumed['metadata']['phase'] == 'consumed'
    assert consumed['decided_by'] == args['owner_key']
    with pytest.raises(SafeOperationError):
        uploads.consume_upload(path, row['id'], **consume_args(args))
    with db.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit_logs WHERE action='upload.consumed'").fetchone()[0] == 1

@pytest.mark.parametrize('method', ['get', 'consume', 'reject'])
def test_other_authenticated_requester_cannot_read_decide_or_invalidate(pending, method):
    path, args, row = pending
    before = ledger.get_approval(row['id'], db_path=path)
    with pytest.raises(SafeOperationError):
        if method == 'get':
            uploads.get_upload(path, row['id'], owner_key='discord-user:other', conversation_key=args['conversation_key'])
        elif method == 'reject':
            uploads.reject_upload(path, row['id'], owner_key='discord-user:other', conversation_key=args['conversation_key'], now=NOW)
        else:
            uploads.consume_upload(path, row['id'], **consume_args(args, owner_key='discord-user:other'))
    assert ledger.get_approval(row['id'], db_path=path) == before

def test_wrong_conversation_read_is_denied_without_mutation(pending):
    path, args, row = pending
    with pytest.raises(SafeOperationError):
        uploads.get_upload(path, row['id'], owner_key=args['owner_key'], conversation_key='discord:other:user:fixture')
    assert lookup(path, args, row)['status'] == 'pending'

@pytest.mark.parametrize('change', [{'sha256': 'b' * 64}, {'destination_id': 'changed-destination'}, {'workspace': '/synthetic/changed-workspace'}, {'relative_path': 'reports/replaced.txt'}, {'conversation_key': 'discord:other:user:fixture'}, *[{'file_identity': {**IDENTITY, key: value + 1}} for key, value in IDENTITY.items()]])
def test_right_owner_scope_change_invalidates_confirmation_permanently(pending, change):
    path, args, row = pending
    with pytest.raises(SafeOperationError):
        uploads.consume_upload(path, row['id'], **consume_args(args, **change))
    assert lookup(path, args, row)['status'] == 'rejected'
    with pytest.raises(SafeOperationError):
        uploads.consume_upload(path, row['id'], **consume_args(args))

@pytest.mark.parametrize('offset', [300, 301])
def test_expired_confirmation_is_persistently_closed(pending, offset):
    path, args, row = pending
    with pytest.raises(SafeOperationError):
        uploads.consume_upload(path, row['id'], **consume_args(args, now=NOW + timedelta(seconds=offset)))
    assert lookup(path, args, row)['status'] == 'expired'
    with pytest.raises(SafeOperationError):
        uploads.consume_upload(path, row['id'], **consume_args(args))

def test_last_instant_before_expiry_is_usable(pending):
    path, args, row = pending
    assert uploads.consume_upload(path, row['id'], **consume_args(args, now=NOW + timedelta(seconds=299)))['metadata']['phase'] == 'consumed'

def test_reject_or_cancel_prevents_later_send_claim(pending):
    path, args, row = pending
    rejected = uploads.reject_upload(path, row['id'], owner_key=args['owner_key'], conversation_key=args['conversation_key'], now=NOW)
    assert rejected['status'] == 'rejected'
    again = uploads.reject_upload(path, row['id'], owner_key=args['owner_key'], conversation_key=args['conversation_key'], now=NOW)
    assert again['status'] == 'rejected'
    with pytest.raises(SafeOperationError):
        uploads.consume_upload(path, row['id'], **consume_args(args))

def test_reject_after_send_claim_cannot_reopen_or_claim_unsent(pending):
    path, args, row = pending
    uploads.consume_upload(path, row['id'], **consume_args(args))
    with pytest.raises(SafeOperationError):
        uploads.reject_upload(path, row['id'], owner_key=args['owner_key'], conversation_key=args['conversation_key'], now=NOW)
    assert lookup(path, args, row)['metadata']['phase'] == 'consumed'

def test_generic_approval_decision_cannot_unlock_upload_send(pending):
    path, args, row = pending
    with db.connect(path) as conn:
        conn.execute("UPDATE approvals SET status='approved',decided_by=? WHERE id=?", (args['owner_key'], row['id']))
    with pytest.raises(SafeOperationError):
        uploads.consume_upload(path, row['id'], **consume_args(args))
    assert lookup(path, args, row)['metadata']['phase'] != 'consumed'

@pytest.mark.parametrize('action', ['workspace.write', 'feedback.review'])
def test_other_approval_action_cannot_be_consumed_or_rejected_as_upload(pending, action):
    path, args, row = pending
    with db.connect(path) as conn:
        conn.execute('UPDATE approvals SET action=? WHERE id=?', (action, row['id']))
    for operation in (uploads.consume_upload, uploads.reject_upload):
        with pytest.raises(SafeOperationError):
            if operation is uploads.consume_upload:
                operation(path, row['id'], **consume_args(args))
            else:
                operation(path, row['id'], owner_key=args['owner_key'], conversation_key=args['conversation_key'], now=NOW)
    assert ledger.get_approval(row['id'], db_path=path)['status'] == 'pending'

def _race_consume(values):
    path, approval_id, args = values
    try:
        uploads.consume_upload(path, approval_id, **args)
        return 'claimed'
    except SafeOperationError:
        return 'held'

def _race_decide(values):
    path, approval_id, args, reject = values
    try:
        if reject:
            uploads.reject_upload(path, approval_id, owner_key=args['owner_key'], conversation_key=args['conversation_key'], now=args['now'])
            return 'rejected'
        return _race_consume((path, approval_id, args))
    except SafeOperationError:
        return 'held'

@pytest.mark.parametrize('processes', [False, True])
def test_concurrent_approvals_grant_exactly_one_send_claim(pending, processes):
    path, args, row = pending
    executor = ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context('spawn')) if processes else ThreadPoolExecutor(max_workers=2)
    with executor as pool:
        results = list(pool.map(_race_consume, [(str(path), row['id'], consume_args(args))] * 2))
    assert sorted(results) == ['claimed', 'held']

def test_approval_rejection_race_has_one_irreversible_winner(pending):
    path, args, row = pending
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(_race_decide, [(str(path), row['id'], consume_args(args), reject) for reject in (False, True)]))
    current = lookup(path, args, row)
    assert sorted(results) in (['claimed', 'held'], ['held', 'rejected'])
    assert (current['status'], current['metadata']['phase']) in {('approved', 'consumed'), ('rejected', 'rejected')}

def test_pending_limit_and_expiry_keep_confirmation_count_bounded(pending):
    path, args, row = pending
    for _ in range(15):
        uploads.request_upload(path, **args)
    with pytest.raises(SafeOperationError):
        uploads.request_upload(path, **args)
    uploads.request_upload(path, **{**args, 'now': NOW + timedelta(seconds=300)})
    with db.connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM approvals WHERE action='discord.upload.pii' AND status='pending'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM approvals WHERE action='discord.upload.pii' AND status='expired'").fetchone()[0] == 16

@pytest.mark.parametrize('counts', [{}, {'email': 0}, {'email': -1}, {'email': True}, {'email': 'synthetic-value'}, {'synthetic-private-value': 1}])
def test_request_rejects_untrusted_detection_details_without_persisting_values(pending, counts, capsys):
    path, args, _row = pending
    with pytest.raises(SafeOperationError) as caught:
        uploads.request_upload(path, **{**args, 'counts': counts})
    captured = capsys.readouterr()
    combined = str(caught.value) + captured.out + captured.err
    assert 'synthetic-private-value' not in combined and 'synthetic-value' not in combined
    with db.connect(path) as conn:
        rows = conn.execute('SELECT metadata_json,reason FROM approvals').fetchall()
    assert 'synthetic-private-value' not in json.dumps([tuple(row) for row in rows])
    assert 'synthetic-value' not in json.dumps([tuple(row) for row in rows])

def test_confirmation_metadata_and_audit_contain_no_document_body(pending):
    path, args, row = pending
    uploads.consume_upload(path, row['id'], **consume_args(args))
    metadata = lookup(path, args, row)['metadata']
    assert not {'content', 'body', 'text', 'extracted_text', 'matches', 'values', 'frozen_bytes'} & metadata.keys()
    with db.connect(path) as conn:
        events = conn.execute("SELECT actor,entity_type,detail_json FROM audit_logs WHERE action LIKE 'upload.%'").fetchall()
        assert conn.execute("SELECT COUNT(*) FROM execution_events WHERE event_type LIKE 'upload.%'").fetchone()[0] == 0
    assert events and all((actor == 'upload-privacy' and entity == 'upload_approval' for actor, entity, _ in events))
    assert all((set(json.loads(detail)) == {'action', 'status'} for _, _, detail in events))

def test_generic_decision_api_cannot_approve_upload(pending):
    path, args, row = pending
    with db.connect(path) as conn:
        conn.execute('UPDATE approvals SET expires_at=? WHERE id=?', ('2099-01-01T00:00:00+00:00', row['id']))
    before = lookup(path, args, row)
    with pytest.raises((ValueError, PermissionError)):
        ledger.decide_approval(row['id'], decision='approved', decided_by=args['owner_key'], db_path=path)
    after = lookup(path, args, row)
    assert after == before
    assert after['status'] == 'pending' and after['metadata']['phase'] == 'pending'
