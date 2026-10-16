"""File plans with immutable content, preimages, one-use approval and an apply journal.

Only this module writes requested workspace files. No generated shell is executed.
POSIX dir-fd traversal refuses symlinks; non-POSIX apply fails closed.
"""

from nyanya_agent.task_outcomes import SafeOperationError
from nyanya_agent.context_security import (
    context_references, inline_context_only, select_context_paths, sensitive_content,
    private_path_part as private_part, PRIVATE_PATH_PARTS,
)
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime, timedelta
import difflib
import hashlib
import json
import os
from pathlib import PurePosixPath
import stat
from nyanya_agent import database as db, execution_store as ledger
from nyanya_agent.operation_store import check_workspace, now, require_apply_ownership, _unresolved_effects


MAX_BYTES = 2_000_000
PRIVATE = PRIVATE_PATH_PARTS
# Conventional dependency trees are not automatic source context, even when named.
SNAPSHOT_DEPENDENCIES = {"conda_envs", "site-packages", "venv"}


def digest(data):
    return None if data is None else hashlib.sha256(data).hexdigest()


def relative(value):
    path = PurePosixPath(value)
    if (
        not isinstance(value, str)
        or not value
        or not path.parts
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in value
        or any(private_part(part) for part in path.parts)
    ):
        raise SafeOperationError("Unsafe or private relative file path")
    return path


@contextmanager
def parent_fd(root, value, create=False, mutation_guard=nullcontext):
    if os.name != "posix" or not all(hasattr(os, flag) for flag in ("O_DIRECTORY", "O_NOFOLLOW")):
        raise SafeOperationError("Reviewed apply requires POSIX no-follow directory operations")
    path = relative(value)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[:-1]:
            if create:
                try:
                    with mutation_guard():
                        os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd, path.name
    finally:
        os.close(fd)


def read_at(fd, name):
    try:
        child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    except FileNotFoundError:
        return None
    try:
        info = os.fstat(child)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise SafeOperationError("Only bounded, single-link regular files are supported")
        if info.st_size > MAX_BYTES:
            raise SafeOperationError("File too large")
        with os.fdopen(os.dup(child), "rb") as stream:
            value = stream.read(MAX_BYTES + 1)
        if len(value) > MAX_BYTES:
            raise SafeOperationError("File too large")
        return value
    finally:
        os.close(child)


def read_file(root, path):
    try:
        with parent_fd(root, path) as (fd, name):
            return read_at(fd, name)
    except FileNotFoundError:
        return None


def _context_path_allowed(name):
    path = PurePosixPath(name)
    return bool(path.parts) and all(
        not private_part(part) and not part.startswith(".") and part.casefold() not in SNAPSHOT_DEPENDENCIES
        for part in path.parts
    ) and not path.name.casefold().endswith((".pem", ".key", ".db", ".sqlite", ".log"))


@contextmanager
def _context_directory(root, name):
    if (os.name != "posix" or not hasattr(os, "fwalk")
            or not all(hasattr(os, flag) for flag in ("O_DIRECTORY", "O_NOFOLLOW"))):
        raise SafeOperationError("Context discovery requires POSIX no-follow directory operations")
    if name:
        with parent_fd(root, name) as (parent, basename):
            fd = os.open(basename, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    else:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        yield fd
    finally:
        os.close(fd)


def _context_names(root, starts):
    """Bound discovery across all scopes, anchored to no-follow directory handles."""
    names = []
    scanned = 0
    seen = set()
    for start in dict.fromkeys(starts):
        if scanned >= 200 or len(names) >= 4000:
            break
        try:
            with _context_directory(root, start) as fd:
                for folder, dirs, filenames, _ in os.fwalk(".", dir_fd=fd, follow_symlinks=False):
                    scanned += 1
                    if scanned > 200 or len(names) >= 4000:
                        return names
                    dirs[:] = sorted(
                        d for d in dirs if not private_part(d) and d.casefold() not in SNAPSHOT_DEPENDENCIES
                        and not d.startswith(".")
                    )
                    for filename in sorted(filenames):
                        name = (PurePosixPath(start) / folder / filename).as_posix()
                        if _context_path_allowed(name) and name not in seen:
                            names.append(name)
                            seen.add(name)
                        if len(names) >= 4000:
                            break
        except (OSError, ValueError):
            continue
    return names


def snapshot(root, request=None, diagnostics=None):
    """Read scoped whole files; optional statuses contain no contents or raw errors."""
    def note(name, reason):
        if diagnostics is not None and (name in diagnostics or len(diagnostics) < 160):
            if len(name.encode("utf-8")) <= 1024:
                diagnostics[name] = reason

    if inline_context_only(request):
        return {}
    references, has_explicit = context_references(request, root)
    allowed = []
    for name, directory in references:
        if not name or _context_path_allowed(name):
            allowed.append((name, directory))
        else:
            note(name, "filtered_private")
    references = allowed
    values = {}
    attempted = set()
    total = 0

    def include(name):
        nonlocal total
        if name in attempted:
            return
        attempted.add(name)
        if len(values) >= 80:
            note(name, "omitted_count_bound")
            return
        try:
            data = read_file(root, name)
            if data is None:
                note(name, "missing")
                return
            if b"\0" in data:
                note(name, "unsupported_type")
                return
            if total + len(data) > 50_000:
                note(name, "oversized")
                return
            try:
                content = data.decode("utf-8")
            except UnicodeError:
                note(name, "unsupported_encoding")
                return
            if sensitive_content(content):
                note(name, "filtered_sensitive")
                return
        except SafeOperationError as exc:
            note(name, "oversized" if str(exc) == "File too large" else "unreadable")
            return
        except (OSError, ValueError):
            note(name, "unreadable")
            return
        values[name] = {"sha256": digest(data), "content": content}
        note(name, "included")
        total += len(data)

    for name, _ in references:
        if name:
            include(name)
    if len(values) >= 80 or total >= 50_000:
        return values
    directories = [name for name, directory in references if directory and name not in values]
    bare_files = [name for name, directory in references if not directory and name and "/" not in name and name not in values]
    starts = directories + ([""] if not has_explicit or bare_files else [])
    for name in select_context_paths(_context_names(root, starts), request, root):
        if len(values) >= 80 or total >= 50_000:
            break
        include(name)
    return values


def propose(path, task_id, owner, root, changes, baseline, *, task_kind="work"):
    root = check_workspace(root, owner)
    if not isinstance(changes, list) or not 1 <= len(changes) <= 40:
        raise SafeOperationError("Invalid change list")
    if task_kind not in {"work", "analysis", "code", "document", "data"}:
        raise SafeOperationError("Invalid task directory kind")
    plan_id = ledger.new_id("plan")
    prepared = []
    seen = set()
    total = 0
    directory = f"nyanya-tasks/{task_kind}/{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{plan_id}"
    for item in changes:
        if not isinstance(item, dict) or set(item) - {"path", "action", "content", "reason"}:
            raise SafeOperationError("Unknown file change field")
        name = str(relative(item["path"]))
        action = item["action"]
        reason = item.get("reason", "")
        if action not in {"create", "modify", "delete"} or not isinstance(reason, str) or not reason.strip():
            raise SafeOperationError("Action and rationale required")
        if action == "create":
            name = f"{directory}/{name}"
        if name in seen:
            raise SafeOperationError("Duplicate file operation")
        seen.add(name)
        before = read_file(root, name)
        if action == "create" and before is not None:
            raise SafeOperationError("Creation would overwrite a file")
        if action != "create" and (
            before is None or name not in baseline or digest(before) != baseline[name]["sha256"]
        ):
            raise SafeOperationError("File changed or not present in the reviewed input snapshot")
        content = item.get("content", "")
        if not isinstance(content, str):
            raise SafeOperationError("Text content required")
        data = None if action == "delete" else content.encode()
        total += len(data or b"")
        if total > MAX_BYTES:
            raise SafeOperationError("Plan too large")
        prepared.append(
            {
                "path": name,
                "action": action,
                "reason": reason[:2000],
                "content": content if data is not None else "",
                "before_hash": digest(before),
                "before_content": before.decode("utf-8") if before is not None else "",
                "after_hash": digest(data),
            }
        )
    encoded = json.dumps(prepared, ensure_ascii=False, sort_keys=True)
    plan_hash = digest(encoded.encode())
    automatic = all(x["action"] == "create" for x in prepared)
    with db.connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        task = conn.execute("SELECT requested_by FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
        if not task or task["requested_by"] != owner:
            raise PermissionError("Plan owner mismatch")
        conn.execute(
            "UPDATE change_plans SET status='revoked' WHERE task_id=? AND status IN ('pending','approved')", (task_id,)
        )
        conn.execute(
            "INSERT INTO change_plans(id,task_id,owner_key,workspace,plan_hash,changes_json,status,expires_at,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                plan_id,
                task_id,
                owner,
                str(root),
                plan_hash,
                encoded,
                "approved" if automatic else "pending",
                (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                now(),
            ),
        )
        ledger.append_event_conn(
            conn,
            task_id=task_id,
            event_type="plan.proposed",
            message="Exclusive creation" if automatic else "File-level review required",
            metadata={"plan_id": plan_id, "plan_hash": plan_hash},
        )
    return get_plan(path, plan_id, owner)


def get_plan(path, plan_id, owner):
    with db.connect(path) as conn:
        row = conn.execute("SELECT * FROM change_plans WHERE id=? AND owner_key=?", (plan_id, owner)).fetchone()
    if not row:
        raise PermissionError("Plan not found for this owner")
    plan = dict(row)
    plan["changes"] = json.loads(plan.pop("changes_json"))
    return plan


def preview(path, plan_id, owner):
    plan = get_plan(path, plan_id, owner)
    check_workspace(plan["workspace"], owner)
    lines = [f"변경안: {plan_id}", f"검토 hash: {plan['plan_hash']}", f"상태: {plan['status']}"]
    for item in plan["changes"]:
        before = item["before_content"].encode()
        if digest(read_file(plan["workspace"], item["path"])) != item["before_hash"]:
            lines.append("주의: 검토 이후 파일 상태가 바뀌었습니다. 이 변경안은 적용할 수 없습니다.")
        diff = "".join(
            difflib.unified_diff(
                before.decode("utf-8").splitlines(True),
                item["content"].splitlines(True),
                fromfile=item["path"],
                tofile=item["path"],
            )
        )
        lines.extend([f"{item['action']}: {item['path']}", f"이유: {item['reason']}", diff[:6000]])
        if len(diff) > 6000:
            lines.append("Diff 일부 생략. 전체 내용: plan-file 변경안ID 상대경로")
    lines.append(f"승인: approve {plan_id} {plan['plan_hash']}\n거절/철회: revoke {plan_id}")
    return "\n".join(lines)


def decide(path, plan_id, owner, plan_hash="", revoke=False):
    with db.connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        decide_conn(conn, plan_id, owner, plan_hash, revoke)


def decide_conn(conn, plan_id, owner, plan_hash="", revoke=False):
    """Reuse decision checks within the caller's atomic approval/admission transaction."""
    row = conn.execute("SELECT * FROM change_plans WHERE id=? AND owner_key=?", (plan_id, owner)).fetchone()
    if not row or row["status"] not in {"pending", "approved"}:
        raise SafeOperationError("Plan is not awaiting a decision")
    parent = conn.execute("SELECT status FROM agent_tasks WHERE id=?", (row["task_id"],)).fetchone()
    if not revoke and (not parent or parent["status"] not in {"queued", "running", "awaiting_approval"}):
        raise SafeOperationError("Original task is no longer eligible for approval")
    if not revoke and (row["expires_at"] <= now() or row["plan_hash"] != plan_hash):
        raise SafeOperationError("Plan expired or revision hash changed")
    conn.execute(
        "UPDATE change_plans SET status=?,decided_by=? WHERE id=?",
        ("revoked" if revoke else "approved", owner, plan_id),
    )
    if revoke:
        _settle_closed_plan(conn, row["task_id"], owner, "revoked")
    else:
        conn.execute("UPDATE approvals SET status='approved',decided_by=?,decided_at=? "
                     "WHERE task_id=? AND action='feedback.review' AND status='pending'",
                     (owner, now(), row["task_id"]))
    ledger.append_event_conn(
        conn,
        task_id=row["task_id"],
        event_type="plan.revoked" if revoke else "plan.approved",
        message="Authenticated owner decision",
        metadata={"plan_id": plan_id},
    )


def _settle_closed_plan(conn, task_id, owner, reason):
    """Close review state only after checking all plans, children and effect evidence."""
    timestamp = now()
    if conn.execute("SELECT 1 FROM change_plans WHERE task_id=? AND status IN ('pending','approved','applying')",
                    (task_id,)).fetchone():
        return
    conn.execute("UPDATE approvals SET status=?,decided_by=?,decided_at=? "
                 "WHERE task_id=? AND status='pending'",
                 ("expired" if reason == "expired" else "rejected", owner, timestamp, task_id))
    parent = conn.execute("SELECT status FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
    if not parent:
        return
    if conn.execute("SELECT 1 FROM task_claims WHERE task_id=? AND released=0 AND expires_at>?",
                    (task_id, timestamp)).fetchone():
        # The worker must finish or lose its claim before the parent is settled.
        return
    if parent["status"] in {"completed", "failed", "cancelled"}:
        # Older ledgers can have a terminal parent and an active-looking review attempt.
        # Close only approval waits; running/lost attempts remain for reconciliation.
        uncertain = _unresolved_effects(conn, task_id)
        _close_review_executions(conn, task_id, timestamp, reason, uncertain)
        if uncertain:
            conn.execute("UPDATE agent_tasks SET status='blocked',completed_at=NULL,updated_at=? WHERE id=?",
                         (timestamp, task_id))
            ledger.append_event_conn(conn, task_id=task_id, event_type="operation.review_effects_held",
                                     status="blocked", message="Review effects require reconciliation")
        return
    children = conn.execute(
        "SELECT t.id,t.status FROM agent_tasks t JOIN task_operations o ON o.task_id=t.id "
        "WHERE o.parent_task_id=?", (task_id,),
    ).fetchall()
    for child in children:
        if child["status"] == "queued":
            conn.execute("UPDATE agent_tasks SET status='cancelled',completed_at=?,updated_at=? WHERE id=?",
                         (timestamp, timestamp, child["id"]))
            conn.execute("UPDATE task_operations SET eligible=0,hold_reason=? WHERE task_id=?",
                         (f"plan_{reason}", child["id"]))
        elif child["status"] in {"running", "cancelling"}:
            conn.execute("UPDATE agent_tasks SET status='cancelling',updated_at=? WHERE id=?",
                         (timestamp, child["id"]))
            conn.execute("UPDATE executions SET status='cancelling',updated_at=? "
                         "WHERE task_id=? AND status='running'", (timestamp, child["id"]))
    uncertain = _unresolved_effects(conn, task_id)
    _close_review_executions(conn, task_id, timestamp, reason, uncertain)
    status = "blocked" if uncertain else "cancelled"
    conn.execute("UPDATE agent_tasks SET status=?,completed_at=?,updated_at=? WHERE id=?",
                 (status, None if uncertain else timestamp, timestamp, task_id))
    conn.execute("UPDATE task_operations SET eligible=0,hold_reason=?,diagnosis=? WHERE task_id=?",
                 (f"plan_{reason}", "File effects require reconciliation" if uncertain else
                  f"Review plan {reason} without file apply", task_id))
    ledger.append_event_conn(conn, task_id=task_id, event_type="operation.plan_closed",
                             status=status, message=f"Review plan {reason}; parent settled")


def _close_review_executions(conn, task_id, timestamp, reason, uncertain):
    status = "lost" if uncertain else "cancelled"
    rows = conn.execute(
        "SELECT id FROM executions WHERE task_id=? AND status='awaiting_approval'",
        (task_id,),
    ).fetchall()
    for row in rows:
        conn.execute("UPDATE executions SET status=?,error=?,ended_at=?,updated_at=? WHERE id=?",
                     (status, f"Review plan {reason}", timestamp, timestamp, row["id"]))
        ledger.append_event_conn(conn, task_id=task_id, execution_id=row["id"],
                                 event_type="execution.review_closed", status=status,
                                 message=f"Review plan {reason}; attempt settled")


def settle_expired(path):
    """Explicit maintenance action; listing and explaining tasks stay read-only."""
    timestamp = now()
    settled = 0
    with db.connect(path) as conn:
        pending = conn.execute("SELECT 1 FROM change_plans WHERE status IN ('pending','approved') "
                               "AND expires_at<=? LIMIT 1", (timestamp,)).fetchone()
        stale = conn.execute(
            "SELECT 1 FROM agent_tasks t JOIN executions e ON e.task_id=t.id "
            "WHERE t.status IN ('completed','failed','cancelled') AND e.status='awaiting_approval' "
            "AND NOT EXISTS (SELECT 1 FROM change_plans p WHERE p.task_id=t.id "
            "AND p.status IN ('pending','approved','applying')) LIMIT 1"
        ).fetchone()
        if not pending and not stale:
            return 0
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute("SELECT id,task_id,owner_key FROM change_plans "
                            "WHERE status IN ('pending','approved') AND expires_at<=?", (timestamp,)).fetchall()
        for row in rows:
            conn.execute("UPDATE change_plans SET status='expired' WHERE id=?", (row["id"],))
            _settle_closed_plan(conn, row["task_id"], row["owner_key"], "expired")
            ledger.append_event_conn(conn, task_id=row["task_id"], event_type="plan.expired",
                                     status="expired", message="Review plan expired",
                                     metadata={"plan_id": row["id"]})
            settled += 1
        # Reconcile historical terminal parents once their plans are no longer open.
        legacy = conn.execute(
            "SELECT DISTINCT t.id FROM agent_tasks t JOIN executions e ON e.task_id=t.id "
            "WHERE t.status IN ('completed','failed','cancelled') AND e.status='awaiting_approval' "
            "AND NOT EXISTS (SELECT 1 FROM change_plans p WHERE p.task_id=t.id "
            "AND p.status IN ('pending','approved','applying'))"
        ).fetchall()
        for row in legacy:
            _settle_closed_plan(conn, row["id"], "system", "closed")
    return settled


@contextmanager
def workspace_lock(path, root):
    if os.name != "posix":
        raise SafeOperationError("POSIX apply locking unavailable")
    import fcntl

    folder = db.resolve_db_path(path).parent / "apply-locks"
    folder.mkdir(mode=0o700, exist_ok=True)
    target = folder / (digest(str(root).encode()) + ".lock")
    fd = os.open(target, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def apply(path, plan_id, owner, cancel_event=None, *, record=None):
    """Apply under current worker ownership at journal and mutation boundaries.

    Compatibility contract for isolated plan helpers: omitting record is allowed
    only for a queued, never-started parent with no executions/claims or submitted
    apply child. Every product worker (including automatic creation) must pass its
    claim record. SQLite write locks serialize each mutation with cancellation and
    recovery; this is not a transaction across the entire filesystem plan.
    """
    plan = get_plan(path, plan_id, owner)
    root = check_workspace(plan["workspace"], owner)

    def require_eligible(conn, expected_status):
        if cancel_event and cancel_event.is_set():
            raise SafeOperationError("Apply cancelled; reconcile journal before retry")
        parent = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (plan["task_id"],)).fetchone()
        if not parent or parent["requested_by"] != owner or parent["status"] not in {
            "queued", "running", "awaiting_approval"
        }:
            raise SafeOperationError("Original task is no longer eligible for file apply")
        if record is None:
            if parent["status"] != "queued" or parent["current_execution_id"] or conn.execute(
                "SELECT 1 FROM executions WHERE task_id=? UNION ALL "
                "SELECT 1 FROM task_claims WHERE task_id=? UNION ALL "
                "SELECT 1 FROM task_operations WHERE parent_task_id=?",
                (plan["task_id"], plan["task_id"], plan["task_id"]),
            ).fetchone():
                raise SafeOperationError("File apply requires the current worker record")
        else:
            require_apply_ownership(conn, record, plan, owner)
        current = conn.execute("SELECT status,expires_at FROM change_plans WHERE id=?", (plan_id,)).fetchone()
        if current["status"] != expected_status or current["expires_at"] <= now():
            raise SafeOperationError("Plan is not approved or expired")

    @contextmanager
    def mutation_guard():
        with db.connect(path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            require_eligible(conn, "applying")
            yield

    def write_content(stream, content):
        data = content.encode()
        offset = 0
        while offset < len(data):
            with mutation_guard():
                written = stream.write(data[offset:])
                if not written:
                    raise OSError("File write made no progress")
                offset += written
        with mutation_guard():
            os.fsync(stream.fileno())

    with workspace_lock(path, root):
        with db.connect(path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            require_eligible(conn, "approved")
            if digest(json.dumps(plan["changes"], ensure_ascii=False, sort_keys=True).encode()) != plan["plan_hash"]:
                raise SafeOperationError("Plan integrity failure")
            uncertain = conn.execute(
                "SELECT 1 FROM change_plans WHERE workspace=? AND status IN ('applying','uncertain') AND id!=?",
                (str(root), plan_id),
            ).fetchone()
            if uncertain:
                raise SafeOperationError("An earlier file apply must be reconciled first")
            for index, item in enumerate(plan["changes"]):
                before = read_file(root, item["path"])
                if digest(before) != item["before_hash"]:
                    raise SafeOperationError("Preimage changed; request a new plan")
                conn.execute(
                    "INSERT INTO change_journal(plan_id,ordinal,path,before_hash,after_hash,before_content) VALUES (?,?,?,?,?,?)",
                    (plan_id, index, item["path"], item["before_hash"], item["after_hash"], before),
                )
            conn.execute("UPDATE change_plans SET status='applying' WHERE id=?", (plan_id,))
        try:
            for index, item in enumerate(plan["changes"]):
                if cancel_event and cancel_event.is_set():
                    raise SafeOperationError("Apply cancelled; reconcile journal before retry")
                with parent_fd(root, item["path"], create=item["action"] == "create",
                               mutation_guard=mutation_guard) as (fd, name):
                    if digest(read_at(fd, name)) != item["before_hash"]:
                        raise SafeOperationError("Preimage changed during apply")
                    if item["action"] == "delete":
                        with mutation_guard():
                            if digest(read_at(fd, name)) != item["before_hash"]:
                                raise SafeOperationError("Preimage changed during apply")
                            os.unlink(name, dir_fd=fd)
                    elif item["action"] == "create":
                        with mutation_guard():
                            filefd = os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=fd)
                        with os.fdopen(filefd, "wb", buffering=0) as stream:
                            write_content(stream, item["content"])
                    else:
                        temp = f".nyanya-{plan_id}-{index}"
                        with mutation_guard():
                            filefd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=fd)
                        try:
                            with os.fdopen(filefd, "wb", buffering=0) as stream:
                                with mutation_guard():
                                    mode = stat.S_IMODE(os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode)
                                    os.fchmod(stream.fileno(), mode & 0o777)
                                write_content(stream, item["content"])
                            with mutation_guard():
                                if digest(read_at(fd, name)) != item["before_hash"]:
                                    raise SafeOperationError("Concurrent edit detected")
                                os.replace(temp, name, src_dir_fd=fd, dst_dir_fd=fd)
                        finally:
                            try:
                                with mutation_guard():
                                    os.unlink(temp, dir_fd=fd)
                            except (FileNotFoundError, SafeOperationError):
                                pass  # Ownership loss leaves the temp file for reconciliation.
                    with mutation_guard():
                        os.fsync(fd)
                with db.connect(path) as conn:
                    conn.execute(
                        "UPDATE change_journal SET state='applied' WHERE plan_id=? AND ordinal=?", (plan_id, index)
                    )
            with db.connect(path) as conn:
                conn.execute("BEGIN IMMEDIATE")
                require_eligible(conn, "applying")
                conn.execute("UPDATE change_plans SET status='applied' WHERE id=?", (plan_id,))
                ledger.append_event_conn(
                    conn,
                    task_id=plan["task_id"],
                    event_type="plan.applied",
                    message="Reviewed file plan applied",
                    metadata={"plan_id": plan_id},
                )
        except Exception:
            with db.connect(path) as conn:
                conn.execute("UPDATE change_plans SET status='uncertain' WHERE id=?", (plan_id,))
            raise
    return "파일 적용 완료:\n" + "\n".join(x["path"] for x in plan["changes"])


def reconcile(path, plan_id, owner):
    plan = get_plan(path, plan_id, owner)
    root = check_workspace(plan["workspace"], owner)
    evidence = []
    with workspace_lock(path, root):
        evidence = observe(root, plan)
        with db.connect(path) as conn:
            ledger.append_event_conn(
                conn,
                task_id=plan["task_id"],
                event_type="plan.reconciled",
                message="Read-only file evidence; no writes replayed",
                metadata={"files": evidence},
            )
    return evidence


def plan_file(path, plan_id, owner, name):
    plan = get_plan(path, plan_id, owner)
    check_workspace(plan["workspace"], owner)
    item = next((x for x in plan["changes"] if x["path"] == name), None)
    if item is None:
        raise SafeOperationError("File not in plan")
    return json.dumps(item, ensure_ascii=False, indent=2)


def evidence_hash(evidence):
    return digest(json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode())


def resolve(path, plan_id, owner, observed_hash):
    """Owner acknowledges observed partial effects; never replays or rolls back files."""
    plan = get_plan(path, plan_id, owner)
    root = check_workspace(plan["workspace"], owner)
    with workspace_lock(path, root):
        evidence = observe(root, plan)
        if evidence_hash(evidence) != observed_hash:
            raise SafeOperationError("Observed files changed; run reconcile again")
        with db.connect(path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT status FROM change_plans WHERE id=?", (plan_id,)).fetchone()
            parent = conn.execute("SELECT status FROM agent_tasks WHERE id=?", (plan["task_id"],)).fetchone()
            if conn.execute(
                "SELECT 1 FROM task_claims c JOIN agent_tasks t ON t.id=c.task_id "
                "LEFT JOIN task_operations o ON o.task_id=t.id "
                "WHERE (c.task_id=? OR o.parent_task_id=?) AND c.released=0 AND c.expires_at>?",
                (plan["task_id"], plan["task_id"], now()),
            ).fetchone():
                raise SafeOperationError("Active execution must stop before file effects can be resolved")
            if row["status"] not in {"applying", "uncertain", "applied"} or (
                row["status"] == "applied" and parent["status"] == "completed"
            ):
                raise SafeOperationError("Only unresolved file effects can be resolved")
            complete = all(item["observed"] == "after" for item in evidence)
            conn.execute(
                "UPDATE change_plans SET status=? WHERE id=?", ("applied" if complete else "reconciled", plan_id)
            )
            reason = "파일 상태 확인 완료. 남은 변경은 현재 파일 기준의 새 변경안을 요청하세요."
            related = conn.execute(
                "SELECT t.id FROM agent_tasks t JOIN task_operations o ON o.task_id=t.id "
                "WHERE json_extract(o.spec_json,'$.kind')='apply' AND json_extract(o.spec_json,'$.plan_id')=? "
                "AND t.status IN ('blocked','failed')",
                (plan_id,),
            ).fetchall()
            resolved_executions = [item["id"] for item in conn.execute(
                "SELECT e.id FROM executions e JOIN agent_tasks t ON t.current_execution_id=e.id "
                "WHERE t.id=? AND e.task_id=t.id AND e.status='lost' "
                "AND e.started_at<=? AND e.ended_at>=? "
                "UNION ALL "
                "SELECT e.id FROM executions e JOIN task_operations o ON o.task_id=e.task_id "
                "WHERE o.parent_task_id=? AND json_extract(o.spec_json,'$.plan_id')=? AND e.status='lost'",
                (plan["task_id"], plan["created_at"], plan["created_at"], plan["task_id"], plan_id),
            )]
            ledger.append_event_conn(
                conn,
                task_id=plan["task_id"],
                event_type="plan.resolved",
                message="Owner acknowledged observed file state; no file writes performed",
                metadata={"plan_id": plan_id, "files": evidence, "complete": complete,
                          "resolved_execution_ids": resolved_executions},
            )
            unresolved = _unresolved_effects(conn, plan["task_id"])
            parent_status = "completed" if complete and not unresolved else "blocked"
            conn.execute(
                "UPDATE agent_tasks SET status=?,updated_at=?,completed_at=? WHERE id=?",
                (parent_status, now(), now() if parent_status == "completed" else None, plan["task_id"]),
            )
            diagnosis = ("다른 실행 효과의 확인이 필요합니다." if unresolved else "") if complete else reason
            conn.execute(
                "UPDATE task_operations SET eligible=0,hold_reason=?,diagnosis=? WHERE task_id=?",
                ("unresolved_effects" if unresolved else "" if complete else "partial_apply_resolved",
                 diagnosis, plan["task_id"]),
            )
            for task in related:
                child_unresolved = _unresolved_effects(conn, task["id"])
                status = "blocked" if child_unresolved else "completed" if complete else "cancelled"
                conn.execute(
                    "UPDATE agent_tasks SET status=?,completed_at=?,updated_at=? WHERE id=?",
                    (status, now() if status in {"completed", "cancelled"} else None, now(), task["id"]),
                )
                ledger.append_event_conn(
                    conn,
                    task_id=task["id"],
                    event_type="task.apply_reconciled",
                    status=status,
                    message="Owner reconciled interrupted file effects; see plan resolution",
                    metadata={"plan_id": plan_id},
                )
    return "파일 상태 확인을 기록했습니다. " + ("변경안의 모든 결과가 확인되었습니다." if complete else reason)


def observe(root, plan):
    evidence = []
    for item in plan["changes"]:
        current = digest(read_file(root, item["path"]))
        state = "after" if current == item["after_hash"] else "before" if current == item["before_hash"] else "diverged"
        evidence.append({"path": item["path"], "observed": state, "sha256": current})
    return evidence
