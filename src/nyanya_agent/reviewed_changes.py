"""File plans with immutable content, preimages, one-use approval and an apply journal.

Only this module writes requested workspace files. No generated shell is executed.
POSIX dir-fd traversal refuses symlinks; non-POSIX apply fails closed.
"""

from nyanya_agent.task_outcomes import SafeOperationError
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime, timedelta
import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
from nyanya_agent import database as db, execution_store as ledger
from nyanya_agent.operation_store import check_workspace, now, require_apply_ownership


MAX_BYTES = 2_000_000
PRIVATE = {
    ".git",
    ".env",
    ".venv",
    "node_modules",
    "__pycache__",
    ".codex",
    ".gemini",
    ".ssh",
    "data",
    "logs",
    "run",
    "sessions",
    "private",
    "downloads",
    "user_workspaces.json",
    "local_system.md",
    "credentials.json",
    "auth.json",
}


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
        or any(part in PRIVATE or part.startswith(".env") for part in path.parts)
    ):
        raise SafeOperationError("Unsafe or private relative file path")
    return path


@contextmanager
def parent_fd(root, value, create=False, mutation_guard=nullcontext):
    if os.name != "posix":
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
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_BYTES:
            raise SafeOperationError("Only bounded, single-link regular files are supported")
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


def snapshot(root):
    """Bounded text context, not a recursive secret or host inventory."""
    values = {}
    total = 0
    scanned = 0
    for folder, dirs, files in os.walk(root, followlinks=False):
        scanned += 1
        if scanned > 200 or len(values) >= 80 or total >= 50_000:
            break
        dirs[:] = sorted(
            d for d in dirs if d not in PRIVATE and not d.startswith(".") and not Path(folder, d).is_symlink()
        )
        for filename in sorted(files):
            if (
                filename in PRIVATE
                or filename.startswith(".")
                or filename.endswith((".pem", ".key", ".db", ".sqlite", ".log"))
            ):
                continue
            name = Path(folder, filename).relative_to(root).as_posix()
            try:
                data = read_file(root, name)
                if data is None or b"\0" in data:
                    continue
                content = data.decode("utf-8")
            except (OSError, ValueError, UnicodeError):
                continue
            if len(values) >= 80 or total + len(data) > 50_000:
                continue
            values[name] = {"sha256": digest(data), "content": content}
            total += len(data)
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
        ledger.append_event_conn(
            conn,
            task_id=row["task_id"],
            event_type="plan.revoked" if revoke else "plan.approved",
            message="Authenticated owner decision",
            metadata={"plan_id": plan_id},
        )


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
            if row["status"] not in {"applying", "uncertain", "applied"} or (
                row["status"] == "applied" and parent["status"] == "completed"
            ):
                raise SafeOperationError("Only unresolved file effects can be resolved")
            complete = all(item["observed"] == "after" for item in evidence)
            conn.execute(
                "UPDATE change_plans SET status=? WHERE id=?", ("applied" if complete else "reconciled", plan_id)
            )
            conn.execute(
                "UPDATE agent_tasks SET status=?,updated_at=?,completed_at=? WHERE id=?",
                ("completed" if complete else "blocked", now(), now() if complete else None, plan["task_id"]),
            )
            reason = "파일 상태 확인 완료. 남은 변경은 현재 파일 기준의 새 변경안을 요청하세요."
            conn.execute(
                "UPDATE task_operations SET eligible=0,hold_reason=?,diagnosis=? WHERE task_id=?",
                ("" if complete else "partial_apply_resolved", "" if complete else reason, plan["task_id"]),
            )
            related = conn.execute(
                "SELECT t.id FROM agent_tasks t JOIN task_operations o ON o.task_id=t.id "
                "WHERE json_extract(o.spec_json,'$.kind')='apply' AND json_extract(o.spec_json,'$.plan_id')=? "
                "AND t.status IN ('blocked','failed')",
                (plan_id,),
            ).fetchall()
            for task in related:
                status = "completed" if complete else "cancelled"
                conn.execute(
                    "UPDATE agent_tasks SET status=?,completed_at=?,updated_at=? WHERE id=?",
                    (status, now(), now(), task["id"]),
                )
                ledger.append_event_conn(
                    conn,
                    task_id=task["id"],
                    event_type="task.apply_reconciled",
                    status=status,
                    message="Owner reconciled interrupted file effects; see plan resolution",
                    metadata={"plan_id": plan_id},
                )
            ledger.append_event_conn(
                conn,
                task_id=plan["task_id"],
                event_type="plan.resolved",
                message="Owner acknowledged observed file state; no file writes performed",
                metadata={"plan_id": plan_id, "files": evidence, "complete": complete},
            )
    return "파일 상태 확인을 기록했습니다. " + ("변경안의 모든 결과가 확인되었습니다." if complete else reason)


def observe(root, plan):
    evidence = []
    for item in plan["changes"]:
        current = digest(read_file(root, item["path"]))
        state = "after" if current == item["after_hash"] else "before" if current == item["before_hash"] else "diverged"
        evidence.append({"path": item["path"], "observed": state, "sha256": current})
    return evidence
