"""Original files stay unchanged until the latest explicitly approved plan applies."""

import json
from pathlib import Path
import sys
import threading

import pytest

from nyanya_agent import database as db, execution_store as ledger, work_drafts
from nyanya_agent.operation_service import OperationService
from nyanya_agent.operation_worker import Worker
from nyanya_agent.task_outcomes import SafeOperationError, OutcomeSignal


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / "original"
    root.mkdir()
    (root / "note.txt").write_text("before\n")
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(root))
    responses, prompts = [], []

    def invoke(profile, prompt, cwd, *_):
        assert Path(cwd).resolve() != root.resolve()
        if prompt.startswith("Return only JSON"):
            return json.dumps(dict(importance=1, impact=1, complexity=1, task_kind="document", reason="fixture"))
        prompts.append(prompt)
        return json.dumps(responses.pop(0))

    worker = Worker(tmp_path / "ledger.db", invoke=invoke)
    service = OperationService(worker.path, generation=worker.generation)
    service.ensure_worker = lambda: worker.generation
    yield root, worker, service, responses, prompts
    service.close()
    worker.close()


def draft_row(service):
    with db.connect(service.path) as conn:
        return dict(conn.execute("SELECT * FROM operation_drafts ORDER BY created_at DESC LIMIT 1").fetchone())


def request(setup, response, prompt="Prepare the requested file work"):
    root, worker, service, responses, _ = setup
    responses.append(response)
    task = service.submit(prompt, root, "operator", conversation_key="channel:a")
    assert worker.run_once()
    return ledger.get_task(task["id"], db_path=service.path)


def open_scope(setup, response):
    _, worker, service, responses, _ = setup
    draft = draft_row(service)
    responses.append(response)
    service.control(f"open-draft {draft['id']} {draft['scope_hash']}", "operator", conversation_key="channel:a", wait=False)
    assert worker.run_once()
    return draft_row(service)


def test_no_original_read_before_scope_approval(setup, monkeypatch):
    from nyanya_agent import reviewed_changes

    def denied(*_):
        pytest.fail("Original contents read before scope approval")

    monkeypatch.setattr(reviewed_changes, "read_file", denied)
    task = request(setup, dict(summary="Need the input", changes=[], read_files=["note.txt"]))
    assert task["status"] == "awaiting_approval"
    draft = draft_row(setup[2])
    assert draft["status"] == "pending" and draft["snapshot_json"] == "{}"


def test_scope_feedback_latest_apply_and_repeat(setup):
    root, worker, service, _, prompts = setup
    request(setup, dict(summary="Read note first", changes=[], read_files=["note.txt"]))
    draft = open_scope(setup, dict(summary="First draft", changes=[dict(path="note.txt", action="modify", content="one\n", reason="requested")]))
    assert (root / "note.txt").read_text() == "before\n"
    assert "before\\n" in prompts[-1]
    old_plan = draft["plan_id"]
    request(setup, dict(summary="Revised draft", changes=[dict(path="note.txt", action="modify", content="two\n", reason="feedback")]), "Revise the draft")
    latest = draft_row(service)
    assert latest["plan_id"] != old_plan
    assert (root / "note.txt").read_text() == "before\n"
    with db.connect(service.path) as conn:
        old = conn.execute("SELECT * FROM change_plans WHERE id=?", (old_plan,)).fetchone()
        plan = conn.execute("SELECT * FROM change_plans WHERE id=?", (latest["plan_id"],)).fetchone()
        assert old["status"] == "revoked"
    with pytest.raises(SafeOperationError):
        service.control(f"approve {old_plan} {old['plan_hash']}", "operator", wait=False)
    with pytest.raises(SafeOperationError):
        service.control(f"approve {plan['id']} {'0' * 64}", "operator", wait=False)
    service.control(f"approve {plan['id']} {plan['plan_hash']}", "operator", wait=False)
    assert worker.run_once()
    assert (root / "note.txt").read_text() == "two\n"
    service.control(f"approve {plan['id']} {plan['plan_hash']}", "operator", wait=False)
    with db.connect(service.path) as conn:
        assert conn.execute("SELECT count(*) FROM change_journal WHERE plan_id=?", (plan["id"],)).fetchone()[0] == 1
        assert conn.execute("SELECT status FROM operation_drafts WHERE id=?", (draft["id"],)).fetchone()[0] == "applied"


def test_new_file_is_staged_and_can_be_revised_or_removed(setup):
    root, _, service, _, _ = setup
    request(setup, dict(summary="Create draft", changes=[dict(path="new.txt", action="create", content="one", reason="requested")]))
    draft = draft_row(service)
    with db.connect(service.path) as conn:
        plan = conn.execute("SELECT * FROM change_plans WHERE id=?", (draft["plan_id"],)).fetchone()
    name = json.loads(plan["changes_json"])[0]["path"]
    assert plan["status"] == "pending" and not (root / name).exists()
    request(setup, dict(summary="Revise", changes=[dict(path=name, action="modify", content="two", reason="feedback")]), "Revise draft")
    request(setup, dict(summary="Remove", changes=[dict(path=name, action="delete", content="", reason="feedback")]), "Remove draft output")
    assert draft_row(service)["plan_id"] is None
    assert not (root / name).exists()


@pytest.mark.parametrize("case", ["owner", "channel", "hash", "reset", "expired", "symlink", "secret"])
def test_read_scope_fails_closed(setup, case):
    from nyanya_agent import conversation_store

    root, worker, service, _, _ = setup
    request(setup, dict(summary="Read", changes=[], read_files=["note.txt"]))
    draft = draft_row(service)
    owner, channel, checksum = "operator", "channel:a", draft["scope_hash"]
    if case == "owner":
        owner = "other"
    elif case == "channel":
        channel = "channel:b"
    elif case == "hash":
        checksum = "wrong"
    elif case == "reset":
        conversation_store.reset(service.path, owner, channel, root)
    elif case == "expired":
        with db.connect(service.path) as conn:
            conn.execute("UPDATE operation_drafts SET expires_at='2000' WHERE id=?", (draft["id"],))
    elif case == "symlink":
        (root / "note.txt").unlink()
        (root / "note.txt").symlink_to(root.parent / "outside")
    elif case == "secret":
        (root / "note.txt").write_text("-----BEGIN PRIVATE KEY-----\nsynthetic\n")
    with pytest.raises((PermissionError, SafeOperationError, OSError)):
        work_drafts.open_and_submit(service.path, draft["id"], checksum, owner, worker.generation, conversation_key=channel)
    assert draft_row(service)["status"] == "pending"
    assert draft_row(service)["snapshot_json"] == "{}"


def test_duplicate_read_approval_has_one_continuation(setup):
    _, worker, service, _, _ = setup
    request(setup, dict(summary="Read", changes=[], read_files=["note.txt"]))
    draft = draft_row(service)
    outcomes = []

    def approve():
        outcomes.append(work_drafts.open_and_submit(service.path, draft["id"], draft["scope_hash"], "operator", worker.generation, conversation_key="channel:a"))

    threads = [threading.Thread(target=approve) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(outcomes) == 2 and sorted(created for _, created in outcomes) == [False, True]
    assert len({task["id"] for task, _ in outcomes}) == 1


def test_original_changed_after_copy_blocks_final_apply(setup):
    root, _, service, _, _ = setup
    request(setup, dict(summary="Read", changes=[], read_files=["note.txt"]))
    draft = open_scope(setup, dict(summary="Edit", changes=[dict(path="note.txt", action="modify", content="after", reason="requested")]))
    (root / "note.txt").write_text("external change")
    with db.connect(service.path) as conn:
        plan = conn.execute("SELECT * FROM change_plans WHERE id=?", (draft["plan_id"],)).fetchone()
    service.control(f"approve {plan['id']} {plan['plan_hash']}", "operator", wait=False)
    assert setup[1].run_once()
    assert (root / "note.txt").read_text() == "external change"
    with db.connect(service.path) as conn:
        assert conn.execute("SELECT count(*) FROM change_journal WHERE plan_id=?", (plan["id"],)).fetchone()[0] == 0


def test_native_original_denial(tmp_path):
    from nyanya_agent.provider_isolation import protect_original
    from nyanya_agent.process_runner import run_command

    if sys.platform != "darwin":
        pytest.skip("Native macOS original-workspace guard")
    original, scratch = (tmp_path / "original").resolve(), (tmp_path / "scratch").resolve()
    original.mkdir()
    scratch.mkdir()
    note = original / "note.txt"
    note.write_text("before")
    code = 'from pathlib import Path; import sys\np=Path(sys.argv[1])\nfor op in [lambda:p.read_text(),lambda:p.write_text("bad")]:\n try:op();print("UNSAFE")\n except PermissionError:print("DENIED")\nPath("draft.txt").write_text("draft")'
    with protect_original(original):
        rc, out, _ = run_command([sys.executable, "-c", code, str(note)], cwd=scratch, timeout=10)
    assert rc == 0 and out.splitlines() == ["DENIED", "DENIED"]
    assert note.read_text() == "before" and (scratch / "draft.txt").read_text() == "draft"


def test_native_guard_has_no_unisolated_fallback(tmp_path, monkeypatch):
    import nyanya_agent.provider_isolation as isolation

    monkeypatch.setattr(isolation.sys, "platform", "unsupported")
    with isolation.protect_original(tmp_path):
        with pytest.raises(OutcomeSignal):
            isolation.isolated_command(["unused"], tmp_path)


def test_explicit_close_settles_waits_and_old_generation_cannot_resume(setup):
    from nyanya_agent import conversation_store

    root, worker, service, _, _ = setup
    task = request(setup, dict(summary="Read", changes=[], read_files=["note.txt"]))
    draft = draft_row(service)
    conversation_store.reset(service.path, "operator", "channel:a", root)
    service.control(f"draft-close {draft['id']}", "operator", conversation_key="channel:a")
    assert (root / "note.txt").read_text() == "before\n"
    assert ledger.get_task(task["id"], db_path=service.path)["status"] == "cancelled"
    with db.connect(service.path) as conn:
        assert conn.execute("SELECT count(*) FROM executions WHERE task_id=? AND status='awaiting_approval'", (task["id"],)).fetchone()[0] == 0
    with pytest.raises(SafeOperationError):
        work_drafts.open_and_submit(service.path, draft["id"], draft["scope_hash"], "operator", worker.generation, conversation_key="channel:a")


def test_read_scope_expiration_does_not_leave_an_approval_wait(setup):
    task = request(setup, dict(summary="Read", changes=[], read_files=["note.txt"]))
    service = setup[2]
    with db.connect(service.path) as conn:
        conn.execute("UPDATE operation_drafts SET expires_at='2000'")
    work_drafts.maintain(service.path)
    assert draft_row(service)["status"] == "closed"
    assert ledger.get_task(task["id"], db_path=service.path)["status"] == "cancelled"
    with db.connect(service.path) as conn:
        assert conn.execute("SELECT status FROM approvals WHERE task_id=?", (task["id"],)).fetchone()[0] == "expired"


def test_cleanup_retains_ready_and_recent_closed_copies(setup):
    request(setup, dict(summary="Read", changes=[], read_files=["note.txt"]))
    draft = open_scope(setup, dict(summary="Reviewed", changes=[]))
    service = setup[2]
    with db.connect(service.path) as conn:
        conn.execute("UPDATE operation_drafts SET updated_at='2000'")
    work_drafts.maintain(service.path)
    assert draft_row(service)["snapshot_json"] != "{}"
    service.control(f"draft-close {draft['id']}", "operator", conversation_key="channel:a")
    work_drafts.maintain(service.path)
    assert draft_row(service)["snapshot_json"] != "{}"
    with db.connect(service.path) as conn:
        conn.execute("UPDATE operation_drafts SET updated_at='2000'")
    work_drafts.maintain(service.path)
    assert draft_row(service)["snapshot_json"] == "{}"
    assert (setup[0] / "note.txt").read_text() == "before\n"


def test_delete_is_only_performed_after_exact_final_approval(setup):
    root, worker, service, _, _ = setup
    request(setup, dict(summary="Read", changes=[], read_files=["note.txt"]))
    draft = open_scope(setup, dict(summary="Propose deletion", changes=[dict(path="note.txt", action="delete", content="", reason="requested")]))
    assert (root / "note.txt").exists()
    with db.connect(service.path) as conn:
        plan = conn.execute("SELECT * FROM change_plans WHERE id=?", (draft["plan_id"],)).fetchone()
    service.control(f"approve {plan['id']} {plan['plan_hash']}", "operator", wait=False)
    assert worker.run_once()
    assert not (root / "note.txt").exists()


def test_feedback_cannot_add_unapproved_input(setup):
    root, _, service, _, _ = setup
    (root / "other.txt").write_text("not approved")
    request(setup, dict(summary="Read", changes=[], read_files=["note.txt"]))
    open_scope(setup, dict(summary="Reviewed", changes=[]))
    task = request(setup, dict(summary="Bad delta", changes=[dict(path="other.txt", action="modify", content="changed", reason="unapproved")]), "Revise draft")
    assert task["status"] != "completed"
    assert (root / "other.txt").read_text() == "not approved"
    assert draft_row(service)["plan_id"] is None


def test_current_inline_only_does_not_materialize_approved_copies(setup):
    root, worker, service, responses, prompts = setup
    request(setup, dict(summary="Read", changes=[], read_files=["note.txt"]))
    draft = open_scope(setup, dict(summary="Reviewed", changes=[]))
    responses.append(dict(summary="Inline only", changes=[]))
    task = service.submit("Do not read files. Analyze only the code in this message.", root, "operator",
                          conversation_key="channel:a", draft_id=draft["id"])
    assert worker.run_once()
    assert ledger.get_task(task["id"], db_path=service.path)["status"] == "completed"
    assert '"note.txt"' not in prompts[-1].split("CURRENT request-scoped snapshot (whole files only):\n")[1].split("Prior conversation")[0]


def test_native_ancestor_rename_denial(tmp_path):
    from nyanya_agent.provider_isolation import protect_original
    from nyanya_agent.process_runner import run_command

    if sys.platform != "darwin":
        pytest.skip("Native macOS original-workspace guard")
    parent = (tmp_path / "parent").resolve()
    original = parent / "original"
    original.mkdir(parents=True)
    note = original / "note.txt"
    note.write_text("before")
    with protect_original(original):
        rc, _, _ = run_command(["/bin/mv", str(parent), str(parent.with_name("moved"))], cwd=tmp_path, timeout=5)
    assert rc != 0 and note.read_text() == "before"


@pytest.mark.parametrize("paths", [["../outside"], [".env"], ["AGENTS.md"], ["note.txt", "note.txt"], ["note.txt"] * 81])
def test_structural_scope_validation_without_language_filters(setup, paths):
    task = request(setup, dict(summary="Invalid scope", changes=[], read_files=paths))
    assert task["status"] != "awaiting_approval"
    with db.connect(setup[2].path) as conn:
        assert conn.execute("SELECT count(*) FROM operation_drafts").fetchone()[0] == 0


def test_uncertain_scope_is_preserved_by_close_and_expiration(setup):
    task = request(setup, dict(summary="Read", changes=[], read_files=["note.txt"]))
    service = setup[2]
    draft = draft_row(service)
    with db.connect(service.path) as conn:
        conn.execute("UPDATE operation_drafts SET expires_at='2000'")
        conn.execute("UPDATE executions SET status='lost' WHERE task_id=?", (task["id"],))
    with pytest.raises(SafeOperationError):
        service.control(f"draft-close {draft['id']}", "operator", conversation_key="channel:a")
    work_drafts.maintain(service.path)
    assert draft_row(service)["status"] == "pending"


def test_pending_new_file_can_be_applied_once(setup):
    root, worker, service, _, _ = setup
    request(setup, dict(summary="Draft output", changes=[dict(path="answer.txt", action="create", content="approved output", reason="requested")]))
    draft = draft_row(service)
    with db.connect(service.path) as conn:
        plan = conn.execute("SELECT * FROM change_plans WHERE id=?", (draft["plan_id"],)).fetchone()
    target = root / json.loads(plan["changes_json"])[0]["path"]
    assert not target.exists()
    service.control(f"approve {plan['id']} {plan['plan_hash']}", "operator", wait=False)
    assert worker.run_once()
    service.control(f"approve {plan['id']} {plan['plan_hash']}", "operator", wait=False)
    assert target.read_text() == "approved output"
    with db.connect(service.path) as conn:
        assert conn.execute("SELECT count(*) FROM change_journal WHERE plan_id=?", (plan["id"],)).fetchone()[0] == 1


def test_late_feedback_cannot_replace_a_newer_draft(setup):
    from nyanya_agent import reviewed_changes as files

    _, _, service, _, _ = setup
    request(setup, dict(summary="Draft output", changes=[dict(path="answer.txt", action="create", content="one", reason="requested")]))
    draft = draft_row(service)
    with db.connect(service.path) as conn:
        conn.execute("UPDATE operation_drafts SET revision=revision+1 WHERE id=?", (draft["id"],))
        loaded = dict(draft, original={}, changes=[])
        before = conn.execute("SELECT count(*) FROM change_plans").fetchone()[0]
    with pytest.raises(SafeOperationError):
        files.propose(service.path, draft["source_task_id"], "operator", draft["workspace"],
                      [dict(path="late.txt", action="create", content="late", reason="stale")], {}, draft_context=loaded)
    with db.connect(service.path) as conn:
        assert conn.execute("SELECT count(*) FROM change_plans").fetchone()[0] == before
        assert conn.execute("SELECT status FROM change_plans WHERE id=?", (draft["plan_id"],)).fetchone()[0] == "pending"


def test_expired_final_plan_can_be_closed_without_losing_expiry_evidence(setup, monkeypatch):
    from nyanya_agent import reviewed_changes

    root, _, service, _, _ = setup
    monkeypatch.setattr(work_drafts, "MAX_OPEN_DRAFTS", 1)
    request(setup, dict(summary="Draft output", changes=[dict(path="answer.txt", action="create", content="pending", reason="requested")]))
    draft = draft_row(service)
    with db.connect(service.path) as conn:
        conn.execute("UPDATE change_plans SET expires_at='2000' WHERE id=?", (draft["plan_id"],))
    reviewed_changes.settle_expired(service.path)
    service.control(f"draft-close {draft['id']}", "operator", conversation_key="channel:a")
    assert draft_row(service)["status"] == "closed"
    with db.connect(service.path) as conn:
        assert conn.execute("SELECT status FROM change_plans WHERE id=?", (draft["plan_id"],)).fetchone()[0] == "expired"
        assert conn.execute("SELECT count(*) FROM change_journal").fetchone()[0] == 0
    assert not list(root.glob("nyanya-tasks/**/*"))
    task = request(setup, dict(summary="Read scope", changes=[], read_files=["note.txt"]))
    assert task["status"] == "awaiting_approval" and draft_row(service)["id"] != draft["id"]


@pytest.mark.parametrize("status", ["approved", "applying", "uncertain"])
def test_expiry_closure_does_not_relax_active_or_uncertain_plan_guards(setup, status):
    request(setup, dict(summary="Draft output", changes=[dict(path="answer.txt", action="create", content="pending", reason="requested")]))
    service = setup[2]
    draft = draft_row(service)
    with db.connect(service.path) as conn:
        conn.execute("UPDATE change_plans SET status=? WHERE id=?", (status, draft["plan_id"]))
    with pytest.raises(SafeOperationError):
        service.control(f"draft-close {draft['id']}", "operator", conversation_key="channel:a")
    assert draft_row(service)["status"] == "ready"
