"""OPS-DEPLOY-01: isolated upgrade, cancellation and file-apply fencing evidence."""

from contextlib import contextmanager
import os
import threading

import pytest

from nyanya_agent import database as db, execution_store as ledger, operation_store as store
from nyanya_agent import reviewed_changes as files, work_queue
from nyanya_agent.operation_spec import OperationSpec
from nyanya_agent.task_outcomes import SafeOperationError, TaskOutcome


@pytest.fixture
def operation(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(root))
    path = tmp_path / "state.db"
    generation = "fixture-worker"
    store.register_worker(path, generation)
    task = store.submit(path, OperationSpec(workspace=str(root), prompt="fixture request"), "operator", generation)
    return path, root, generation, task


def approved_apply(operation, action="modify"):
    path, root, generation, task = operation
    (root / "note.txt").write_text("before")
    request = store.claim(path, generation)
    plan = files.propose(
        path, task["id"], "operator", root,
        [{"path": "note.txt", "action": action, "content": "after", "reason": "fixture correction"}],
        files.snapshot(root),
    )
    store.finish(path, request, TaskOutcome("awaiting_approval", "review required"))
    files.decide(path, plan["id"], "operator", plan["plan_hash"])
    store.submit(path, OperationSpec(kind="apply", workspace=str(root), plan_id=plan["id"]), "operator", generation)
    return plan, store.claim(path, generation)


@pytest.mark.parametrize("version", [2, 3])
def test_quiesced_legacy_upgrade_holds_all_attempts_without_replay(tmp_path, monkeypatch, version):
    path = tmp_path / "legacy.db"
    migrations = ledger.MIGRATIONS
    monkeypatch.setattr(ledger, "MIGRATIONS", migrations[:version])
    task = ledger.create_task(title="preserve request", prompt="original request", db_path=path)
    queued = ledger.create_task(title="never started", db_path=path)
    if version == 3:
        claim = work_queue.claim(path, task["id"], "old-worker", "operator")
        first_id = claim["execution_id"]
    else:
        first_id = ledger.create_execution(task_id=task["id"], adapter_type="legacy", status="running", db_path=path)["id"]
        ledger.transition_task(task["id"], "running", db_path=path)
    last = ledger.create_execution(task_id=task["id"], adapter_type="legacy", db_path=path)
    monkeypatch.setattr(ledger, "MIGRATIONS", migrations)
    ledger.apply_migrations(path)
    assert store.recover(path) == 0
    assert ledger.get_task(task["id"], db_path=path)["status"] == "running"
    with pytest.raises(SafeOperationError):
        store.hold_legacy_for_quiesced_upgrade(path, writers_stopped=False, reason="fixture")
    reason = "Fixture: old writers and children stopped; backup checked"
    assert store.hold_legacy_for_quiesced_upgrade(path, writers_stopped=True, reason=reason) == 2
    assert store.hold_legacy_for_quiesced_upgrade(path, writers_stopped=True, reason=reason) == 0
    assert ledger.get_task(task["id"], db_path=path)["prompt"] == "original request"
    assert ledger.get_task(task["id"], db_path=path)["status"] == "blocked"
    assert ledger.get_task(queued["id"], db_path=path)["status"] == "blocked"
    assert ledger.get_execution(first_id, db_path=path)["status"] == "lost"
    assert ledger.get_execution(last["id"], db_path=path)["status"] == "lost"
    assert reason in store.explain(path, task["id"], "operator")
    incomplete = {row["id"]: row for row in store.incomplete(path, "operator")}
    assert incomplete[task["id"]]["attempts"] == 2
    assert "시도 수: 2" in store.explain(path, task["id"], "operator")
    assert incomplete[queued["id"]]["attempts"] == 0
    assert "시도 수: 0" in store.explain(path, queued["id"], "operator")
    with db.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM task_operations").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM task_claims WHERE released=0").fetchone()[0] == 0
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    events = ledger.list_events(db_path=path)
    assert len([e for e in events if e["event_type"] == "operation.legacy_upgrade_held"]) == 2
    store.register_worker(path, "new-worker")
    assert store.claim(path, "new-worker") is None
    with pytest.raises(PermissionError):
        store.resume(path, task["id"], "operator", "new-worker")
    store.cancel(path, task["id"], "operator")
    assert ledger.get_task(task["id"], db_path=path)["status"] == "cancelled"


@pytest.mark.parametrize("attempts", [0, 2])
def test_incomplete_preserves_operation_attempts_over_execution_count(operation, attempts):
    path, _, _, task = operation
    ledger.create_execution(task_id=task["id"], adapter_type="fixture", db_path=path)
    with db.connect(path) as conn:
        conn.execute("UPDATE task_operations SET attempts=? WHERE task_id=?", (attempts, task["id"]))
    assert store.incomplete(path, "operator")[0]["attempts"] == attempts
    assert f"시도 수: {attempts}" in store.explain(path, task["id"], "operator")


def test_upgrade_audit_failure_rolls_back_task_execution_and_claim(operation, monkeypatch):
    path, _, _, _ = operation
    task = ledger.create_task(title="legacy", db_path=path)
    record = work_queue.claim(path, task["id"], "old-worker", "operator")

    append = ledger.append_event_conn

    def fail(*args, **kwargs):
        if kwargs.get("event_type") == "operation.legacy_upgrade_held":
            raise RuntimeError("fixture audit failure")
        return append(*args, **kwargs)

    monkeypatch.setattr(ledger, "append_event_conn", fail)
    with pytest.raises(RuntimeError, match="audit failure"):
        store.hold_legacy_for_quiesced_upgrade(path, writers_stopped=True, reason="fixture stop verified")
    assert ledger.get_task(task["id"], db_path=path)["status"] == "running"
    assert ledger.get_execution(record["execution_id"], db_path=path)["status"] == "running"
    with db.connect(path) as conn:
        assert conn.execute("SELECT released FROM task_claims WHERE task_id=?", (task["id"],)).fetchone()[0] == 0


@pytest.mark.parametrize("claim_state", ["expired", "released"])
def test_cancellation_without_usable_claim_does_not_wait_forever(operation, claim_state):
    path, _, generation, task = operation
    record = store.claim(path, generation)
    with db.connect(path) as conn:
        if claim_state == "expired":
            conn.execute("UPDATE task_claims SET expires_at='2000'")
        else:
            conn.execute("UPDATE task_claims SET released=1")
    store.cancel(path, task["id"], "operator")
    assert ledger.get_task(task["id"], db_path=path)["status"] == "blocked"
    assert ledger.get_execution(record["execution_id"], db_path=path)["status"] == "lost"
    with db.connect(path) as conn:
        assert conn.execute("SELECT released FROM task_claims").fetchone()[0] == 1
        assert conn.execute("SELECT eligible FROM task_operations").fetchone()[0] == 0
    with pytest.raises(ValueError, match="Stale"):
        store.finish(path, record, TaskOutcome("succeeded", "late"))


def test_active_cancel_still_requires_worker_acknowledgement(operation):
    path, _, generation, task = operation
    record = store.claim(path, generation)
    store.cancel(path, task["id"], "operator")
    assert ledger.get_execution(record["execution_id"], db_path=path)["status"] == "cancelling"
    assert ledger.get_task(task["id"], db_path=path)["status"] == "cancelling"
    store.finish(path, record, TaskOutcome("cancelled", "owned process stopped"))
    assert ledger.get_task(task["id"], db_path=path)["status"] == "cancelled"


def test_cancel_remains_recoverable_if_worker_dies_before_acknowledgement(operation):
    path, _, generation, task = operation
    record = store.claim(path, generation)
    store.cancel(path, task["id"], "operator")
    store.heartbeat(path, generation, closed=True)
    assert store.recover(path) == 1
    assert ledger.get_task(task["id"], db_path=path)["status"] == "blocked"
    assert ledger.get_execution(record["execution_id"], db_path=path)["status"] == "lost"


def test_old_execution_cancellation_cannot_cancel_a_new_attempt(operation):
    path, _, generation, task = operation
    record = store.claim(path, generation)
    with pytest.raises(SafeOperationError, match="no longer current"):
        store.cancel(path, task["id"], "operator", expected_execution_id="old-execution")
    assert ledger.get_execution(record["execution_id"], db_path=path)["status"] == "running"


@pytest.mark.parametrize("endpoint", ["tasks", "executions"])
@pytest.mark.parametrize("approved", [False, True])
def test_dashboard_cancel_waiting_parent_prevents_approval_and_apply(operation, monkeypatch, endpoint, approved):
    from fastapi.testclient import TestClient
    from nyanya_agent.dashboard_api import create_app

    path, root, _, task = operation
    plan, apply_record = approved_apply(operation)
    if not approved:
        with db.connect(path) as conn:
            conn.execute("UPDATE change_plans SET status='pending' WHERE id=?", (plan["id"],))
    parent = ledger.get_task(task["id"], db_path=path)
    target = task["id"] if endpoint == "tasks" else parent["current_execution_id"]
    monkeypatch.setenv("NYANYA_DASHBOARD_CONTROL_TOKEN", "fixture-control")
    with TestClient(create_app(path), client=("127.0.0.1", 50000)) as client:
        route = f"/v1/{endpoint}/{target}/cancel"
        assert client.post(route, json={}).status_code == 401
        response = client.post(route, json={}, headers={"X-Nyanya-Control-Token": "fixture-control"})
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"
    assert ledger.get_task(task["id"], db_path=path)["status"] == "cancelled"
    with pytest.raises(SafeOperationError):
        files.decide(path, plan["id"], "operator", plan["plan_hash"])
    with pytest.raises(SafeOperationError, match="Original task"):
        files.apply(path, plan["id"], "operator", record=apply_record)
    assert (root / "note.txt").read_text() == "before"


@pytest.mark.parametrize("endpoint", ["tasks", "executions"])
def test_dashboard_cancel_does_not_trust_payload_owner(operation, monkeypatch, endpoint):
    from fastapi.testclient import TestClient
    from nyanya_agent.dashboard_api import create_app

    path, _, generation, task = operation
    record = store.claim(path, generation)
    with db.connect(path) as conn:
        conn.execute("UPDATE agent_tasks SET requested_by='another-owner',metadata_json='{}' WHERE id=?", (task["id"],))
    monkeypatch.setenv("NYANYA_DASHBOARD_CONTROL_TOKEN", "fixture-control")
    target = task["id"] if endpoint == "tasks" else record["execution_id"]
    client = TestClient(create_app(path), client=("127.0.0.1", 50000))
    response = client.post(
        f"/v1/{endpoint}/{target}/cancel", json={"actor": "another-owner"},
        headers={"X-Nyanya-Control-Token": "fixture-control"},
    )
    assert response.status_code == 403
    assert ledger.get_execution(record["execution_id"], db_path=path)["status"] == "running"


@pytest.mark.parametrize("loss", ["eligible", "released", "expired", "current", "worker", "execution", "parent", "missing_record"])
def test_stale_apply_rejected_before_journal(operation, loss):
    path, root, _, task = operation
    plan, record = approved_apply(operation)
    with db.connect(path) as conn:
        if loss == "eligible":
            conn.execute("UPDATE task_operations SET eligible=0 WHERE task_id=?", (record["task_id"],))
        elif loss == "released":
            conn.execute("UPDATE task_claims SET released=1")
        elif loss == "expired":
            conn.execute("UPDATE task_claims SET expires_at='2000'")
        elif loss == "current":
            conn.execute("UPDATE agent_tasks SET current_execution_id=NULL WHERE id=?", (record["task_id"],))
        elif loss == "worker":
            conn.execute("UPDATE operation_workers SET closed=1")
        elif loss == "execution":
            conn.execute("UPDATE executions SET status='cancelling' WHERE id=?", (record["execution_id"],))
        elif loss == "parent":
            conn.execute("UPDATE agent_tasks SET status='cancelled' WHERE id=?", (task["id"],))
        elif loss == "missing_record":
            record = None
    with pytest.raises(SafeOperationError):
        files.apply(path, plan["id"], "operator", record=record)
    with db.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM change_journal").fetchone()[0] == 0
    assert (root / "note.txt").read_text() == "before"
    assert sorted(p.name for p in root.iterdir()) == ["note.txt"]


@pytest.mark.parametrize("action", ["create", "modify", "delete"])
def test_eligibility_lost_after_journal_before_any_workspace_mutation(operation, monkeypatch, action):
    path, root, generation, task = operation
    if action == "create":
        record = store.claim(path, generation)
        plan = files.propose(
            path, task["id"], "operator", root,
            [{"path": "new.txt", "action": "create", "content": "new", "reason": "fixture artifact"}], {},
        )
    else:
        plan, record = approved_apply(operation, action)
    original = files.parent_fd

    @contextmanager
    def lose_after_journal(*args, **kwargs):
        if "mutation_guard" in kwargs:
            with db.connect(path) as conn:
                conn.execute("UPDATE task_operations SET eligible=0 WHERE task_id=?", (record["task_id"],))
        with original(*args, **kwargs) as value:
            yield value

    monkeypatch.setattr(files, "parent_fd", lose_after_journal)
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    with pytest.raises(SafeOperationError, match="ownership"):
        files.apply(path, plan["id"], "operator", record=record)
    assert files.get_plan(path, plan["id"], "operator")["status"] == "uncertain"
    after = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert after == before
    if action == "create":
        assert list(root.iterdir()) == []


def test_eligibility_loss_after_temp_write_prevents_replace_and_cleanup(operation, monkeypatch):
    path, root, _, _ = operation
    plan, record = approved_apply(operation)
    original_connect, original_fsync = db.connect, os.fsync
    lose = threading.Event()
    lost = False

    def fsync(fd):
        original_fsync(fd)
        lose.set()  # First fsync is the temporary file, inside its write transaction.

    @contextmanager
    def connect(*args, **kwargs):
        nonlocal lost
        with original_connect(*args, **kwargs) as conn:
            yield conn
        if lose.is_set() and not lost:
            lost = True
            with original_connect(path) as conn:
                conn.execute("UPDATE task_operations SET eligible=0 WHERE task_id=?", (record["task_id"],))

    monkeypatch.setattr(files.os, "fsync", fsync)
    monkeypatch.setattr(db, "connect", connect)
    with pytest.raises(SafeOperationError, match="ownership"):
        files.apply(path, plan["id"], "operator", record=record)
    assert lost
    assert (root / "note.txt").read_text() == "before"
    temporary = list(root.glob(".nyanya-*"))
    assert len(temporary) == 1 and temporary[0].read_text() == "after"
    assert files.get_plan(path, plan["id"], "operator")["status"] == "uncertain"


@pytest.mark.parametrize("action,boundary", [
    ("create", "mkdir"), ("create", "open"), ("modify", "open"),
    ("modify", "fchmod"), ("modify", "replace"),
])
def test_no_further_mutations_after_ownership_loss_at_each_boundary(operation, monkeypatch, action, boundary):
    path, root, generation, task = operation
    if action == "create":
        record = store.claim(path, generation)
        plan = files.propose(
            path, task["id"], "operator", root,
            [{"path": "nested/new.txt", "action": "create", "content": "new", "reason": "fixture artifact"}], {},
        )
    else:
        plan, record = approved_apply(operation)
    original_connect = db.connect
    original_mutation = getattr(files.os, boundary)
    lose = threading.Event()
    observed = None

    def inventory():
        return {
            str(p.relative_to(root)): (p.stat().st_mode, p.read_bytes() if p.is_file() else None)
            for p in root.rglob("*")
        }

    def mutation(*args, **kwargs):
        result = original_mutation(*args, **kwargs)
        if boundary in {"fchmod", "replace"} or kwargs.get("dir_fd") is not None:
            if boundary != "open" or args[1] & os.O_CREAT:
                lose.set()
        return result

    @contextmanager
    def connect(*args, **kwargs):
        nonlocal observed
        with original_connect(*args, **kwargs) as conn:
            yield conn
        if lose.is_set() and observed is None:
            observed = inventory()
            with original_connect(path) as conn:
                conn.execute("UPDATE task_operations SET eligible=0 WHERE task_id=?", (record["task_id"],))

    monkeypatch.setattr(files.os, boundary, mutation)
    monkeypatch.setattr(db, "connect", connect)
    with pytest.raises(SafeOperationError, match="ownership"):
        files.apply(path, plan["id"], "operator", record=record)
    assert observed is not None and inventory() == observed
    assert files.get_plan(path, plan["id"], "operator")["status"] == "uncertain"


def test_valid_product_record_applies_and_completes_parent(operation):
    path, root, _, task = operation
    plan, record = approved_apply(operation)
    result = files.apply(path, plan["id"], "operator", record=record)
    store.finish(path, record, TaskOutcome("succeeded", result))
    assert (root / "note.txt").read_text() == "after"
    assert ledger.get_task(task["id"], db_path=path)["status"] == "completed"


def test_product_creation_result_loss_still_requires_reconciliation(operation):
    path, root, generation, task = operation
    record = store.claim(path, generation)
    plan = files.propose(
        path, task["id"], "operator", root,
        [{"path": "new.txt", "action": "create", "content": "new", "reason": "fixture artifact"}], {},
    )
    files.apply(path, plan["id"], "operator", record=record)
    store.finish(path, record, TaskOutcome("blocked", "result commit interrupted"))
    with pytest.raises(SafeOperationError, match="File side effects"):
        store.resume(path, task["id"], "operator", generation)
    evidence = files.reconcile(path, plan["id"], "operator")
    files.resolve(path, plan["id"], "operator", files.evidence_hash(evidence))
    assert ledger.get_task(task["id"], db_path=path)["status"] == "completed"
    assert len(list(root.rglob("new.txt"))) == 1


def test_never_started_isolated_plan_helper_contract(operation):
    path, root, _, task = operation
    plan = files.propose(
        path, task["id"], "operator", root,
        [{"path": "new.txt", "action": "create", "content": "new", "reason": "fixture artifact"}], {},
    )
    files.apply(path, plan["id"], "operator")
    assert (root / plan["changes"][0]["path"]).read_text() == "new"
