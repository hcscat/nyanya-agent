from concurrent.futures import ThreadPoolExecutor
import json
import threading
import time

import pytest

from nyanya_agent import database as db, execution_store as ledger, operation_store as store, work_queue
from nyanya_agent import model_routing, reviewed_changes as files
from nyanya_agent.operation_spec import OperationSpec
from nyanya_agent.operation_worker import Worker
from nyanya_agent.operation_service import OperationService
from nyanya_agent.task_outcomes import TaskOutcome


def fake_model(profile, prompt, workspace, timeout, cancel):
    if prompt.startswith("Return only JSON"):
        assert profile == "flash"
        return json.dumps({"importance": 2, "impact": 1, "complexity": 3, "reason": "bounded code review"})
    return json.dumps({"summary": "analysis complete", "changes": []})


@pytest.fixture
def setup(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(workspace))
    path = tmp_path / "state.db"
    worker = Worker(path, invoke=fake_model)
    return path, workspace, worker


def add(setup, prompt="inspect", owner="operator"):
    path, root, worker = setup
    return store.submit(path, OperationSpec(prompt=prompt, workspace=str(root)), owner, worker.generation)


def test_operation_roundtrip_and_unknown_executable_fields(setup):
    _, root, _ = setup
    spec = OperationSpec(prompt="inspect", workspace=str(root))
    assert OperationSpec.loads(spec.dumps()) == spec
    with pytest.raises(TypeError):
        OperationSpec.loads(json.dumps({"workspace": str(root), "shell": "rm anything"}))
    with pytest.raises(ValueError):
        OperationSpec(version=7, workspace=str(root)).dumps()


def test_data_only_operation_runs_without_submitter_callback(setup):
    path, _, worker = setup
    task = add(setup)
    worker.run_once()
    assert ledger.get_task(task["id"], db_path=path)["status"] == "completed"
    assert work_queue.result(path, task["id"], "operator")["response"] == "analysis complete"
    assert any(e["event_type"] == "operation.routed" for e in ledger.list_events(db_path=path))


def test_same_owner_parallelism_and_global_capacity(setup):
    path, _, worker = setup
    tasks = [add(setup, str(i)) for i in range(3)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        claims = list(pool.map(lambda _: store.claim(path, worker.generation, 2), range(3)))
    assert len([c for c in claims if c]) == 2
    assert len({c["task_id"] for c in claims if c}) == 2
    assert sum(ledger.get_task(t["id"], db_path=path)["status"] == "queued" for t in tasks) == 1


def test_dead_worker_queue_is_held_but_other_tasks_can_complete(setup):
    path, root, worker = setup
    old = add(setup, "original request")
    assert store.recovery_inventory(path) == []
    store.heartbeat(path, worker.generation, closed=True)
    next_worker = Worker(path, invoke=fake_model)
    assert store.recover(path) == 1
    assert [t["id"] for t in store.recovery_inventory(path)] == [old["id"]]
    new = store.submit(
        path, OperationSpec(prompt="new independent work", workspace=str(root)), "operator", next_worker.generation
    )
    next_worker.run_once()
    assert ledger.get_task(old["id"], db_path=path)["status"] == "blocked"
    result = work_queue.result(path, new["id"], "operator")["response"]
    assert old["id"] in result and "미완료" in result
    explanation = store.explain(path, old["id"], "operator")
    assert "original request" in explanation and "heartbeat" in explanation
    with pytest.raises(PermissionError):
        store.explain(path, old["id"], "other")


def test_recovery_rejects_old_worker_result_and_requires_explicit_resume(setup):
    path, _, worker = setup
    task = add(setup)
    old = store.claim(path, worker.generation)
    store.heartbeat(path, worker.generation, closed=True)
    store.recover(path)
    with pytest.raises(ValueError):
        store.finish(path, old, TaskOutcome("succeeded", "late"))
    fresh = Worker(path, invoke=fake_model)
    assert store.claim(path, fresh.generation) is None
    store.resume(path, task["id"], "operator", fresh.generation)
    fresh.run_once()
    assert ledger.get_task(task["id"], db_path=path)["status"] == "completed"


@pytest.mark.parametrize(
    "importance,impact,complexity,profile",
    [(1, 1, 1, "flash"), (2, 2, 3, "luna"), (4, 1, 2, "astra"), (1, 4, 1, "astra"), (1, 1, 5, "astra")],
)
def test_routing_axes(importance, impact, complexity, profile):
    assert (
        model_routing.route(dict(importance=importance, impact=impact, complexity=complexity, reason="evidence"))
        == profile
    )
    assert model_routing.PROFILES["luna"].effort == "xhigh"
    assert model_routing.PROFILES["astra"].effort == "low"
    with pytest.raises(ValueError, match="task kind"):
        model_routing.route(dict(importance=1, impact=1, complexity=1, reason="invalid path", task_kind="../outside"))


def test_bad_model_assessment_fails_without_fallback(setup):
    path, _, worker = setup
    task = add(setup)
    worker.invoke = lambda *_: '{"importance":true,"impact":1,"complexity":1,"reason":"bad"}'
    worker.run_once()
    assert ledger.get_task(task["id"], db_path=path)["status"] == "blocked"
    assert "Invalid routing score" in store.explain(path, task["id"], "operator")


def make_plan(setup, action="modify"):
    path, root, worker = setup
    (root / "note.txt").write_text("before\n")
    task = add(setup)
    plan = files.propose(
        path,
        task["id"],
        "operator",
        root,
        [{"path": "note.txt", "action": action, "content": "after\n", "reason": "requested correction"}],
        files.snapshot(root),
    )
    return task, plan


def test_review_preview_approval_and_exact_apply(setup):
    path, root, _ = setup
    task, plan = make_plan(setup)
    assert "-before" in files.preview(path, plan["id"], "operator")
    assert (root / "note.txt").read_text() == "before\n"
    with pytest.raises(ValueError):
        files.apply(path, plan["id"], "operator")
    with pytest.raises(ValueError):
        files.decide(path, plan["id"], "other", plan["plan_hash"])
    with pytest.raises(ValueError):
        files.decide(path, plan["id"], "operator", "changed hash")
    files.decide(path, plan["id"], "operator", plan["plan_hash"])
    files.apply(path, plan["id"], "operator")
    assert (root / "note.txt").read_text() == "after\n"
    with pytest.raises(ValueError):
        files.apply(path, plan["id"], "operator")
    with db.connect(path) as conn:
        assert (
            conn.execute("SELECT before_content FROM change_journal WHERE plan_id=?", (plan["id"],)).fetchone()[0]
            == b"before\n"
        )


def test_create_is_exclusive_and_under_dated_task_directory(setup):
    path, root, _ = setup
    task = add(setup)
    plan = files.propose(
        path,
        task["id"],
        "operator",
        root,
        [{"path": "report.txt", "action": "create", "content": "new", "reason": "new report"}],
        {},
        task_kind="document",
    )
    assert plan["status"] == "approved"
    assert plan["changes"][0]["path"].startswith("nyanya-tasks/document/")
    files.apply(path, plan["id"], "operator")
    assert not (root / "report.txt").exists()
    assert (root / plan["changes"][0]["path"]).read_text() == "new"


@pytest.mark.parametrize("failure", ["edited", "expired", "revoked", "symlink"])
def test_approval_revalidation_before_apply(setup, failure):
    path, root, _ = setup
    _, plan = make_plan(setup)
    files.decide(path, plan["id"], "operator", plan["plan_hash"])
    if failure == "edited":
        (root / "note.txt").write_text("external edit")
    if failure == "expired":
        with db.connect(path) as conn:
            conn.execute("UPDATE change_plans SET expires_at='2000' WHERE id=?", (plan["id"],))
    if failure == "revoked":
        files.decide(path, plan["id"], "operator", revoke=True)
    if failure == "symlink":
        outside = root.parent / "outside"
        outside.write_text("outside")
        (root / "note.txt").unlink()
        (root / "note.txt").symlink_to(outside)
    with pytest.raises((ValueError, OSError)):
        files.apply(path, plan["id"], "operator")
    assert (root / "note.txt").read_text() != "after\n"


def test_delete_needs_approval(setup):
    path, root, _ = setup
    _, plan = make_plan(setup, "delete")
    with pytest.raises(ValueError):
        files.apply(path, plan["id"], "operator")
    assert (root / "note.txt").exists()
    files.decide(path, plan["id"], "operator", plan["plan_hash"])
    files.apply(path, plan["id"], "operator")
    assert not (root / "note.txt").exists()


def test_partial_apply_failure_has_journal_and_no_automatic_replay(setup, monkeypatch):
    path, root, _ = setup
    task = add(setup)
    (root / "a").write_text("a")
    (root / "b").write_text("b")
    plan = files.propose(
        path,
        task["id"],
        "operator",
        root,
        [{"path": x, "action": "modify", "content": "new", "reason": "requested"} for x in ["a", "b"]],
        files.snapshot(root),
    )
    files.decide(path, plan["id"], "operator", plan["plan_hash"])
    original = files.os.replace
    calls = []

    def replace(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise OSError("disk full fixture")
        return original(*args, **kwargs)

    monkeypatch.setattr(files.os, "replace", replace)
    with pytest.raises(OSError):
        files.apply(path, plan["id"], "operator")
    assert files.get_plan(path, plan["id"], "operator")["status"] == "uncertain"
    evidence = files.reconcile(path, plan["id"], "operator")
    assert [e["observed"] for e in evidence] == ["after", "before"]
    with pytest.raises(ValueError):
        files.apply(path, plan["id"], "operator")


def test_worker_executes_generated_plan_but_waits_for_modification_approval(setup):
    path, root, worker = setup
    (root / "note.txt").write_text("before")
    task = add(setup)

    def model(profile, prompt, *args):
        if prompt.startswith("Return only JSON"):
            return fake_model(profile, prompt, *args)
        return json.dumps(
            {
                "summary": "change proposal",
                "changes": [{"path": "note.txt", "action": "modify", "content": "after", "reason": "fix"}],
            }
        )

    worker.invoke = model
    worker.run_once()
    assert ledger.get_task(task["id"], db_path=path)["status"] == "awaiting_approval"
    assert (root / "note.txt").read_text() == "before"
    with db.connect(path) as conn:
        row = conn.execute("SELECT * FROM change_plans").fetchone()
    service = OperationService(path, generation=worker.generation)
    # Explicitly test an existing in-process fixture worker, not the denied production launcher.
    service.ensure_worker = lambda: worker.generation
    service.control(f"approve {row['id']} {row['plan_hash']}", "operator", responder=lambda _: None)
    worker.run_once()
    service.close()
    assert (root / "note.txt").read_text() == "after"
    assert ledger.get_task(task["id"], db_path=path)["status"] == "completed"


def test_workspace_registration_revalidated_in_worker(setup, monkeypatch):
    path, root, worker = setup
    registration = root.parent / "workspaces.json"
    registration.write_text(json.dumps({"users": {"discord-user:test": {"workspace": str(root)}}}))
    monkeypatch.setenv("NYANYA_USER_WORKSPACES_FILE", str(registration))
    task = add(setup, owner="discord-user:test")
    registration.write_text('{"users":{}}')
    worker.run_once()
    assert ledger.get_task(task["id"], db_path=path)["status"] == "failed"


def test_snapshot_does_not_include_private_state_or_symlinks(setup):
    _, root, _ = setup
    (root / ".env").write_text("private")
    (root / "config").mkdir()
    (root / "config/user_workspaces.json").write_text("private")
    (root / "public").write_text("public")
    (root / "link").symlink_to(root / ".env")
    assert set(files.snapshot(root)) == {"public"}


def test_two_real_worker_threads_run_simultaneously(setup):
    path, _, worker = setup
    tasks = [add(setup, str(i)) for i in range(2)]
    barrier = threading.Barrier(2)
    names = []

    def invoke(profile, prompt, *args):
        if prompt.startswith("Return only JSON"):
            return fake_model(profile, prompt, *args)
        names.append(threading.get_ident())
        barrier.wait(timeout=3)
        return '{"summary":"parallel","changes":[]}'

    worker.invoke = invoke
    thread = threading.Thread(target=worker.run)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and any(
            ledger.get_task(t["id"], db_path=path)["status"] != "completed" for t in tasks
        ):
            time.sleep(0.05)
        assert len(set(names)) == 2
        assert all(ledger.get_task(t["id"], db_path=path)["status"] == "completed" for t in tasks)
    finally:
        worker.stop.set()
        thread.join(timeout=5)
    assert not thread.is_alive()


# Captured before per-test monkeypatch: only used with an explicitly fake local executable.
REAL_ENSURE_WORKER = OperationService.ensure_worker


def test_dedicated_worker_process_executes_spec_with_fake_cli(tmp_path, monkeypatch):
    import sys
    import types

    root = tmp_path / "workspace"
    root.mkdir()
    fake = tmp_path / "agy-fixture"
    fake.write_text(
        "#!"
        + sys.executable
        + '\nimport sys,json\np=sys.argv[sys.argv.index("--prompt")+1]\nprint(json.dumps({"importance":1,"impact":1,"complexity":1,"reason":"fixture"} if p.startswith("Return only JSON") else {"summary":"process result","changes":[]}))\n'
    )
    fake.chmod(0o700)
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(root))
    monkeypatch.setenv("NYANYA_AGY_CLI", str(fake))
    service = OperationService(tmp_path / "state.db")
    service.ensure_worker = types.MethodType(REAL_ENSURE_WORKER, service)
    try:
        task = service.submit("inspect", root, "operator")
        result = service.wait(task["id"], "operator", timeout=10)
        assert result.status == "succeeded" and result.text == "process result"
        assert service.process.pid != __import__("os").getpid()
    finally:
        service.close()
    assert service.process.poll() is not None


@pytest.mark.skipif(__import__("os").name != "posix", reason="POSIX crash fixture")
def test_real_worker_death_preserves_queued_request(tmp_path, monkeypatch):
    import os
    import signal
    import types

    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(root))
    service = OperationService(tmp_path / "state.db")
    service.ensure_worker = types.MethodType(REAL_ENSURE_WORKER, service)
    try:
        service.ensure_worker()
        os.kill(service.process.pid, signal.SIGSTOP)
        task = service.submit("must remain queued", root, "operator")
        service.process.kill()
        service.process.wait(timeout=3)
        assert service.wait(task["id"], "operator", timeout=3).status == "blocked"
        assert ledger.get_task(task["id"], db_path=service.path)["status"] == "blocked"
        assert "must remain queued" in store.explain(service.path, task["id"], "operator")
    finally:
        service.close()


def test_resume_wait_and_delivery_never_return_previous_attempt(setup):
    path, _, worker = setup
    task = add(setup)
    claim = store.claim(path, worker.generation)
    store.finish(path, claim, TaskOutcome("failed", "old failure"))
    store.resume(path, task["id"], "operator", worker.generation)
    service = OperationService(path, generation=worker.generation)
    replies = []
    delivery = threading.Thread(target=service.deliver, args=(task["id"], "operator", replies.append))
    delivery.start()
    with ThreadPoolExecutor(max_workers=1) as pool:
        waiting = pool.submit(service.wait, task["id"], "operator", 3)
        time.sleep(0.2)
        assert not waiting.done() and replies == []
        worker.run_once()
        assert waiting.result(timeout=3).text == "analysis complete"
    delivery.join(timeout=3)
    service.close()
    assert replies == ["analysis complete"]


def test_explicit_retries_are_bounded_and_require_live_generation(setup):
    path, _, worker = setup
    task = add(setup)
    for attempt in range(3):
        claim = store.claim(path, worker.generation)
        store.finish(path, claim, TaskOutcome("failed", "fixture failure"))
        if attempt < 2:
            with pytest.raises(ValueError, match="Worker not ready"):
                store.resume(path, task["id"], "operator", "nonexistent")
            store.resume(path, task["id"], "operator", worker.generation)
    with pytest.raises(ValueError, match="attempt limit"):
        store.resume(path, task["id"], "operator", worker.generation)
    assert "3" in store.explain(path, task["id"], "operator")


def test_interrupted_apply_resolution_binds_owner_and_observed_files(setup):
    path, root, _ = setup
    task = add(setup)
    (root / "a.txt").write_text("before")
    plan = files.propose(
        path,
        task["id"],
        "operator",
        root,
        [{"path": "a.txt", "action": "modify", "content": "after", "reason": "fix"}],
        files.snapshot(root),
    )
    with db.connect(path) as conn:
        conn.execute("UPDATE change_plans SET status='uncertain' WHERE id=?", (plan["id"],))
    evidence = files.reconcile(path, plan["id"], "operator")
    token = files.evidence_hash(evidence)
    with pytest.raises(PermissionError):
        files.resolve(path, plan["id"], "other", token)
    (root / "a.txt").write_text("external edit")
    with pytest.raises(ValueError, match="Observed files changed"):
        files.resolve(path, plan["id"], "operator", token)
    evidence = files.reconcile(path, plan["id"], "operator")
    files.resolve(path, plan["id"], "operator", files.evidence_hash(evidence))
    assert files.get_plan(path, plan["id"], "operator")["status"] == "reconciled"
    assert (root / "a.txt").read_text() == "external edit"
    assert ledger.get_task(task["id"], db_path=path)["status"] == "blocked"


def test_preview_preserves_original_review_even_after_external_change(setup):
    path, root, _ = setup
    task = add(setup)
    (root / "a.txt").write_text("before\n")
    plan = files.propose(
        path,
        task["id"],
        "operator",
        root,
        [{"path": "a.txt", "action": "modify", "content": "after\n", "reason": "fix"}],
        files.snapshot(root),
    )
    (root / "a.txt").write_text("external\n")
    preview = files.preview(path, plan["id"], "operator")
    assert "-before" in preview and "+after" in preview and "바뀌었습니다" in preview
    assert "external" not in preview


def test_api_operation_submission_uses_worker_and_preserves_undelivered_result(setup, monkeypatch, fixture_worker):
    from fastapi.testclient import TestClient
    from nyanya_agent.dashboard_api import create_app

    path, root, _ = setup
    monkeypatch.setenv("NYANYA_DASHBOARD_CONTROL_TOKEN", "fixture-control")
    with TestClient(create_app(path), client=("127.0.0.1", 50000)) as client:
        payload = {"prompt": "inspect", "workspace": str(root)}
        assert client.post("/v1/operations", json=payload).status_code == 401
        response = client.post("/v1/operations", json=payload, headers={"X-Nyanya-Control-Token": "fixture-control"})
        assert response.status_code == 201
        task_id = response.json()["id"]
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not work_queue.result(path, task_id, "operator"):
            time.sleep(0.05)
        saved = work_queue.result(path, task_id, "operator")
        assert saved["outcome"] == "succeeded" and saved["delivery_status"] == "pending"


def claim_in_process(args):
    path, generation = args
    record = store.claim(path, generation, 2)
    return record["task_id"] if record else None


def test_separate_process_claims_share_atomic_capacity(setup):
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor

    path, _, worker = setup
    for i in range(4):
        add(setup, str(i))
    with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn")) as pool:
        claims = list(pool.map(claim_in_process, [(str(path), worker.generation)] * 4))
    assert len([c for c in claims if c]) == 2
    assert len({c for c in claims if c}) == 2


def test_expired_claim_is_held_even_with_live_worker_heartbeat(setup):
    path, _, worker = setup
    task = add(setup)
    record = store.claim(path, worker.generation)
    with db.connect(path) as conn:
        conn.execute("UPDATE task_claims SET expires_at='2000-01-01T00:00:00+00:00' WHERE task_id=?", (task["id"],))
    assert store.recover(path) == 1
    assert ledger.get_task(task["id"], db_path=path)["status"] == "blocked"
    with pytest.raises(ValueError):
        store.finish(path, record, TaskOutcome("succeeded", "stale"))


def test_creation_side_effects_cannot_be_replayed_after_result_loss(setup):
    path, root, worker = setup
    task = add(setup)
    claim = store.claim(path, worker.generation)
    plan = files.propose(
        path,
        task["id"],
        "operator",
        root,
        [{"path": "new.txt", "action": "create", "content": "new", "reason": "deliver"}],
        {},
    )
    files.apply(path, plan["id"], "operator", record=claim)
    store.finish(path, claim, TaskOutcome("blocked", "result commit interrupted"))
    with pytest.raises(ValueError, match="File side effects"):
        store.resume(path, task["id"], "operator", worker.generation)
    evidence = files.reconcile(path, plan["id"], "operator")
    files.resolve(path, plan["id"], "operator", files.evidence_hash(evidence))
    assert ledger.get_task(task["id"], db_path=path)["status"] == "completed"
    assert len(list(root.rglob("new.txt"))) == 1


def test_cancelled_original_task_cannot_apply_approved_plan(setup):
    path, root, _ = setup
    task = add(setup)
    (root / "a.txt").write_text("before")
    plan = files.propose(
        path,
        task["id"],
        "operator",
        root,
        [{"path": "a.txt", "action": "modify", "content": "after", "reason": "fix"}],
        files.snapshot(root),
    )
    files.decide(path, plan["id"], "operator", plan["plan_hash"])
    store.cancel(path, task["id"], "operator")
    with pytest.raises(ValueError, match="Original task"):
        files.apply(path, plan["id"], "operator")
    assert (root / "a.txt").read_text() == "before"


def test_worker_start_failure_retains_request_and_reason(setup):
    path, root, _ = setup
    service = OperationService(path)

    def fail():
        raise RuntimeError("fixture startup error")

    service.ensure_worker = fail
    task = service.submit("retained request", root, "operator")
    assert task["status"] == "blocked"
    result = service.wait(task["id"], "operator", 1)
    assert result.status == "blocked" and "retained request" in result.text and "Worker 시작 실패" in result.text
    service.close()


def test_remote_and_forwarded_reads_require_authentication(setup, monkeypatch):
    from fastapi.testclient import TestClient
    from nyanya_agent.dashboard_api import create_app

    path, _, _ = setup
    monkeypatch.setenv("NYANYA_DASHBOARD_CONTROL_TOKEN", "fixture-control")
    app = create_app(path)
    with TestClient(app, client=("remote-client", 50000)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/v1/tasks").status_code == 401
        assert client.get("/v1/tasks", headers={"X-Nyanya-Control-Token": "fixture-control"}).status_code == 200
    with TestClient(create_app(path), client=("127.0.0.1", 50000)) as client:
        assert client.get("/v1/tasks").status_code == 200
        assert client.get("/v1/tasks", headers={"X-Forwarded-For": "remote-client"}).status_code == 401


def test_schema_three_backup_upgrade_and_restore_preserve_work(tmp_path, monkeypatch):
    from nyanya_agent.state_backup import backup_database

    path = tmp_path / "v3.db"
    migrations = ledger.MIGRATIONS
    monkeypatch.setattr(ledger, "MIGRATIONS", migrations[:3])
    task = ledger.create_task(title="retained", prompt="original", db_path=path)
    execution = ledger.create_execution(task_id=task["id"], adapter_type="test", db_path=path)
    approval = ledger.request_approval(
        task_id=task["id"], action="feedback.review", requested_by="operator", db_path=path
    )
    backup = tmp_path / "backup-v3.db"
    backup_database(path, backup)
    monkeypatch.setattr(ledger, "MIGRATIONS", migrations)
    assert ledger.apply_migrations(path) == 4
    assert ledger.get_task(task["id"], db_path=path)["current_execution_id"] == execution["id"]
    assert ledger.list_approvals(db_path=path)[0]["id"] == approval["id"]
    restored = tmp_path / "restored.db"
    backup_database(backup, restored)
    with db.connect(restored) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert ledger.apply_migrations(restored) == 4
    assert ledger.get_task(task["id"], db_path=restored)["prompt"] == "original"
    assert ledger.list_events(db_path=restored)


def test_owned_process_cancellation_and_output_limit(tmp_path):
    import sys
    from nyanya_agent.process_runner import run_command
    from nyanya_agent.task_outcomes import OutcomeSignal

    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(OutcomeSignal) as exc:
        run_command(
            [sys.executable, "-c", "import time;time.sleep(30)"], cwd=tmp_path, timeout=2, cancel_event=cancelled
        )
    assert exc.value.outcome.status == "cancelled"
    with pytest.raises(OutcomeSignal) as exc:
        run_command([sys.executable, "-c", "print('x'*5000000)"], cwd=tmp_path, timeout=3)
    assert exc.value.outcome.status == "blocked"


def apply_and_crash_after_file_commit(path, plan_id):
    import os
    import stat

    original = os.fsync

    def crash(fd):
        original(fd)
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            os._exit(93)  # after replace + directory fsync, before journal/result commit

    os.fsync = crash
    files.apply(path, plan_id, "operator")


@pytest.mark.skipif(__import__("os").name != "posix", reason="POSIX file crash fixture")
def test_real_apply_crash_after_file_commit_is_reconciled_without_replay(setup):
    import multiprocessing

    path, root, _ = setup
    task = add(setup)
    (root / "a.txt").write_text("before")
    plan = files.propose(
        path,
        task["id"],
        "operator",
        root,
        [{"path": "a.txt", "action": "modify", "content": "after", "reason": "fix"}],
        files.snapshot(root),
    )
    files.decide(path, plan["id"], "operator", plan["plan_hash"])
    process = multiprocessing.get_context("spawn").Process(
        target=apply_and_crash_after_file_commit, args=(str(path), plan["id"])
    )
    process.start()
    process.join(timeout=5)
    try:
        assert process.exitcode == 93
    finally:
        if process.is_alive():
            process.kill()
            process.join(timeout=3)
    assert (root / "a.txt").read_text() == "after"
    assert files.get_plan(path, plan["id"], "operator")["status"] == "applying"
    with db.connect(path) as conn:
        row = conn.execute("SELECT state,before_content FROM change_journal WHERE plan_id=?", (plan["id"],)).fetchone()
        assert row["state"] == "prepared" and row["before_content"] == b"before"
    with pytest.raises(ValueError):
        files.apply(path, plan["id"], "operator")
    evidence = files.reconcile(path, plan["id"], "operator")
    assert evidence[0]["observed"] == "after"
    files.resolve(path, plan["id"], "operator", files.evidence_hash(evidence))
    assert ledger.get_task(task["id"], db_path=path)["status"] == "completed"
    assert (root / "a.txt").read_text() == "after"
