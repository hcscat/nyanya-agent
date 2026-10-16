"""Owner decisions, uncertain effects and private file boundaries."""

from datetime import UTC, datetime, timedelta

import pytest

from nyanya_agent import database as db, execution_store as ledger
from nyanya_agent import operation_store as store, reviewed_changes as files
from nyanya_agent.operation_spec import OperationSpec
from nyanya_agent.task_outcomes import SafeOperationError, TaskOutcome


@pytest.fixture
def operation(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(root))
    path = tmp_path / "state.db"
    store.register_worker(path, "worker")
    task = store.submit(path, OperationSpec(workspace=str(root), prompt="original request"),
                        "operator", "worker")
    return path, root, task


def test_failed_dismissal_preserves_history_and_is_idempotent(operation):
    path, _, task = operation
    record = store.claim(path, "worker")
    store.finish(path, record, TaskOutcome("failed", "model timeout"))
    assert task["id"] in store.list_text(path, "operator")
    assert store.dismiss(path, task["id"], "operator") == "failed"
    assert store.dismiss(path, task["id"], "operator") == "failed"
    assert task["id"] not in store.list_text(path, "operator")
    assert ledger.get_task(task["id"], db_path=path)["status"] == "failed"
    assert "model timeout" in store.explain(path, task["id"], "operator")
    assert "dismissed" in store.explain(path, task["id"], "operator")
    with pytest.raises(PermissionError):
        store.explain(path, task["id"], "another-owner")
    events = [event for event in ledger.list_events(db_path=path)
              if event["event_type"] == "operation.dismissed"]
    assert len(events) == 1


def test_completed_history_remains_explainable(operation):
    path, _, task = operation
    record = store.claim(path, "worker")
    store.finish(path, record, TaskOutcome("succeeded", "done"))
    assert task["id"] not in store.list_text(path, "operator")
    assert "상태: completed" in store.explain(path, task["id"], "operator")


def test_expired_claim_double_cancel_keeps_lost_evidence(operation):
    path, _, task = operation
    record = store.claim(path, "worker")
    with db.connect(path) as conn:
        conn.execute("UPDATE task_claims SET expires_at='2000' WHERE task_id=?", (task["id"],))
    assert store.cancel(path, task["id"], "operator") == "blocked"
    assert store.cancel(path, task["id"], "operator") == "blocked"
    assert ledger.get_execution(record["execution_id"], db_path=path)["status"] == "lost"
    assert ledger.get_task(task["id"], db_path=path)["status"] == "blocked"
    assert task["id"] in store.list_text(path, "operator")
    with pytest.raises(SafeOperationError):
        store.dismiss(path, task["id"], "operator")


@pytest.mark.parametrize("decision", ["revoke", "expire"])
def test_plan_closure_settles_parent_and_approval(operation, decision):
    path, root, task = operation
    target = root / "note.txt"
    target.write_text("before")
    record = store.claim(path, "worker")
    plan = files.propose(path, task["id"], "operator", root,
                         [{"path": "note.txt", "action": "modify", "content": "after",
                           "reason": "review"}], files.snapshot(root))
    store.finish(path, record, TaskOutcome("awaiting_approval", "review required"))
    if decision == "revoke":
        files.decide(path, plan["id"], "operator", revoke=True)
        expected = "revoked"
    else:
        with db.connect(path) as conn:
            conn.execute("UPDATE change_plans SET expires_at=? WHERE id=?",
                         ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), plan["id"]))
        assert files.settle_expired(path) == 1
        assert files.settle_expired(path) == 0
        expected = "expired"
    assert files.get_plan(path, plan["id"], "operator")["status"] == expected
    assert ledger.get_task(task["id"], db_path=path)["status"] == "cancelled"
    with db.connect(path) as conn:
        statuses = [row[0] for row in conn.execute("SELECT status FROM approvals WHERE task_id=?", (task["id"],))]
    assert statuses == (["expired"] if decision == "expire" else ["rejected"])
    assert target.read_text() == "before"


def test_local_instructions_and_backup_reports_are_excluded(operation):
    _, root, _ = operation
    paths = ["AGENTS.md", "AGENTS.override.md", "AGENTS_LOCAL_TEST.md",
             "nested/AGENTS.md.bak", "nested/AGENTS-workspace.md", "backups/notes.txt",
             "reports/notes.txt", "nested/reports/notes.txt"]
    for name in paths:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("private")
        with pytest.raises(SafeOperationError):
            files.relative(name)
    (root / "public.txt").write_text("public")
    assert set(files.snapshot(root)) == {"public.txt"}


def test_cancel_parent_with_active_apply_child_stays_held(operation):
    path, root, task = operation
    (root / "note.txt").write_text("before")
    request = store.claim(path, "worker")
    plan = files.propose(path, task["id"], "operator", root,
                         [{"path": "note.txt", "action": "modify", "content": "after",
                           "reason": "review"}], files.snapshot(root))
    store.finish(path, request, TaskOutcome("awaiting_approval", "review required"))
    files.decide(path, plan["id"], "operator", plan["plan_hash"])
    child = store.submit(path, OperationSpec(kind="apply", workspace=str(root), plan_id=plan["id"]),
                         "operator", "worker")
    store.claim(path, "worker")
    assert store.cancel(path, task["id"], "operator") == "blocked"
    assert store.cancel(path, task["id"], "operator") == "blocked"
    assert ledger.get_task(task["id"], db_path=path)["status"] == "blocked"
    assert ledger.get_task(child["id"], db_path=path)["status"] == "cancelling"
    with pytest.raises(SafeOperationError):
        store.dismiss(path, task["id"], "operator")


def test_resolve_refuses_live_child_even_with_matching_hash(operation):
    path, root, task = operation
    (root / "note.txt").write_text("before")
    request = store.claim(path, "worker")
    plan = files.propose(path, task["id"], "operator", root,
                         [{"path": "note.txt", "action": "modify", "content": "after",
                           "reason": "review"}], files.snapshot(root))
    store.finish(path, request, TaskOutcome("awaiting_approval", "review required"))
    files.decide(path, plan["id"], "operator", plan["plan_hash"])
    store.submit(path, OperationSpec(kind="apply", workspace=str(root), plan_id=plan["id"]),
                 "operator", "worker")
    store.claim(path, "worker")
    with db.connect(path) as conn:
        conn.execute("UPDATE change_plans SET status='uncertain' WHERE id=?", (plan["id"],))
    evidence = files.reconcile(path, plan["id"], "operator")
    with pytest.raises(SafeOperationError, match="Active execution"):
        files.resolve(path, plan["id"], "operator", files.evidence_hash(evidence))


def test_hash_bound_resolution_clears_lost_effect_hold(operation):
    path, root, task = operation
    record = store.claim(path, "worker")
    plan = files.propose(path, task["id"], "operator", root,
                         [{"path": "note.txt", "action": "create", "content": "after",
                           "reason": "review"}], {})
    files.apply(path, plan["id"], "operator", record=record)
    store.finish(path, record, TaskOutcome("blocked", "result commit interrupted"))
    with db.connect(path) as conn:
        assert store._unresolved_effects(conn, task["id"])
    evidence = files.reconcile(path, plan["id"], "operator")
    files.resolve(path, plan["id"], "operator", files.evidence_hash(evidence))
    with db.connect(path) as conn:
        assert not store._unresolved_effects(conn, task["id"])
    assert ledger.get_task(task["id"], db_path=path)["status"] == "completed"

    # A later lost apply attempt for a different plan is not covered by that resolution.
    other = files.propose(path, task["id"], "operator", root,
                          [{"path": "other.txt", "action": "create", "content": "other",
                            "reason": "separate change"}], {})
    child = store.submit(path, OperationSpec(kind="apply", workspace=str(root), plan_id=other["id"]),
                         "operator", "worker")
    ledger.create_execution(task_id=child["id"], adapter_type="operation", status="lost", db_path=path)
    with db.connect(path) as conn:
        conn.execute("UPDATE change_plans SET status='reconciled' WHERE id=?", (other["id"],))
        assert store._unresolved_effects(conn, task["id"])


def test_cancel_rejects_changed_selection_without_side_effects(operation):
    path, _, task = operation
    selected = ledger.get_task(task["id"], db_path=path)
    record = store.claim(path, "worker")
    with pytest.raises(SafeOperationError, match="Selected task changed"):
        store.cancel(path, task["id"], "operator", expected_status=selected["status"],
                     expected_updated_at=selected["updated_at"])
    assert ledger.get_task(task["id"], db_path=path)["status"] == "running"
    assert ledger.get_execution(record["execution_id"], db_path=path)["status"] == "running"
    assert not any(event["event_type"] == "operation.cancel_requested"
                   for event in ledger.list_events(db_path=path))


def test_dismiss_rejects_changed_revision_without_side_effects(operation):
    path, _, task = operation
    record = store.claim(path, "worker")
    store.finish(path, record, TaskOutcome("failed", "model timeout"))
    selected = ledger.get_task(task["id"], db_path=path)
    with db.connect(path) as conn:
        conn.execute("UPDATE agent_tasks SET updated_at=? WHERE id=?", ("2100-01-01", task["id"]))
    with pytest.raises(SafeOperationError, match="Selected task changed"):
        store.dismiss(path, task["id"], "operator", expected_status=selected["status"],
                      expected_updated_at=selected["updated_at"])
    assert task["id"] in store.list_text(path, "operator")
    assert not any(event["event_type"] == "operation.dismissed"
                   for event in ledger.list_events(db_path=path))


def test_resolve_keeps_parent_blocked_for_unrelated_lost_attempt(operation):
    path, root, task = operation
    older = ledger.create_execution(task_id=task["id"], adapter_type="operation",
                                    status="lost", db_path=path)
    record = store.claim(path, "worker")
    plan = files.propose(path, task["id"], "operator", root,
                         [{"path": "note.txt", "action": "create", "content": "after",
                           "reason": "review"}], {})
    files.apply(path, plan["id"], "operator", record=record)
    store.finish(path, record, TaskOutcome("blocked", "result commit interrupted"))
    evidence = files.reconcile(path, plan["id"], "operator")
    files.resolve(path, plan["id"], "operator", files.evidence_hash(evidence))
    assert ledger.get_task(task["id"], db_path=path)["status"] == "blocked"
    assert task["id"] in store.list_text(path, "operator")
    with db.connect(path) as conn:
        assert store._unresolved_effects(conn, task["id"])
        resolved = conn.execute("SELECT metadata_json FROM execution_events WHERE event_type='plan.resolved'").fetchone()
    assert older["id"] not in resolved["metadata_json"]


def test_resolved_apply_child_does_not_retain_lost_hold(operation):
    path, root, task = operation
    (root / "note.txt").write_text("before")
    request = store.claim(path, "worker")
    plan = files.propose(path, task["id"], "operator", root,
                         [{"path": "note.txt", "action": "modify", "content": "after",
                           "reason": "review"}], files.snapshot(root))
    store.finish(path, request, TaskOutcome("awaiting_approval", "review required"))
    files.decide(path, plan["id"], "operator", plan["plan_hash"])
    child = store.submit(path, OperationSpec(kind="apply", workspace=str(root), plan_id=plan["id"]),
                         "operator", "worker")
    apply_record = store.claim(path, "worker")
    files.apply(path, plan["id"], "operator", record=apply_record)
    store.finish(path, apply_record, TaskOutcome("blocked", "result commit interrupted"))
    evidence = files.reconcile(path, plan["id"], "operator")
    files.resolve(path, plan["id"], "operator", files.evidence_hash(evidence))
    assert ledger.get_task(task["id"], db_path=path)["status"] == "completed"
    assert ledger.get_task(child["id"], db_path=path)["status"] == "completed"
    with db.connect(path) as conn:
        assert not store._unresolved_effects(conn, child["id"])
        assert conn.execute("SELECT COUNT(*) FROM approvals WHERE task_id=? AND status='pending'",
                            (task["id"],)).fetchone()[0] == 0
