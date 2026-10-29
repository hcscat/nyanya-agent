"""Owner-scoped read approval and durable copies; final writes reuse reviewed plans."""

from datetime import UTC, datetime, timedelta
import hashlib
import json

from nyanya_agent import database as db, execution_store as ledger
from nyanya_agent.task_outcomes import SafeOperationError


MAX_FILES = 80
MAX_SNAPSHOT_BYTES = 50_000
MAX_OPEN_DRAFTS = 20


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _now():
    return datetime.now(UTC).isoformat()


def _scope(conn, draft, owner, workspace, *, task_id=None, conversation_key=None, current=True):
    if not draft or (draft["owner_key"], draft["workspace"]) != (owner, workspace):
        raise PermissionError("Draft scope mismatch")
    if draft["session_id"]:
        session = conn.execute("SELECT * FROM conversation_sessions WHERE id=?", (draft["session_id"],)).fetchone()
        if current and session["generation"] != draft["generation"]:
            raise SafeOperationError("Draft belongs to an earlier conversation generation")
        if task_id:
            turn = conn.execute("SELECT c.*,t.project_id FROM conversation_turns c JOIN agent_tasks t ON t.id=c.task_id WHERE c.task_id=?", (task_id,)).fetchone()
            if not turn or (turn["session_id"], turn["generation"]) != (draft["session_id"], draft["generation"]):
                raise PermissionError("Draft conversation mismatch")
            source = conn.execute("SELECT project_id FROM agent_tasks WHERE id=?", (draft["source_task_id"],)).fetchone()
            if source["project_id"] != turn["project_id"]:
                raise PermissionError("Draft project mismatch")
        elif conversation_key is None or hashlib.sha256(conversation_key.encode()).hexdigest() != session["conversation_hash"]:
            raise PermissionError("Draft conversation mismatch")


def _paths(paths):
    from nyanya_agent import reviewed_changes as files

    if not isinstance(paths, list) or len(paths) > MAX_FILES:
        raise SafeOperationError("Draft file scope exceeds its bound")
    result = []
    for value in paths:
        if not isinstance(value, str) or len(value.encode()) > 1024:
            raise SafeOperationError("Invalid draft file path")
        name = str(files.relative(value))
        if not files._context_path_allowed(name) or name in result:
            raise SafeOperationError("Private or duplicate draft path")
        result.append(name)
    return sorted(result)


def create(path, record, paths):
    from nyanya_agent.operation_store import check_workspace

    owner, spec = record["owner"], record["spec"]
    root = str(check_workspace(spec.workspace, owner))
    paths = _paths(paths)
    with db.connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        prior = conn.execute("SELECT * FROM operation_drafts WHERE source_task_id=?", (record["task_id"],)).fetchone()
        if prior:
            if prior["paths_json"] != _json(paths):
                raise SafeOperationError("Retry cannot replace a draft scope")
            return dict(prior)
        if conn.execute("SELECT count(*) FROM operation_drafts WHERE owner_key=? AND status IN ('pending','ready')",
                        (owner,)).fetchone()[0] >= MAX_OPEN_DRAFTS:
            raise SafeOperationError("Close existing drafts before opening another")
        turn = conn.execute("SELECT session_id,generation FROM conversation_turns WHERE task_id=?", (record["task_id"],)).fetchone()
        identifier, timestamp = ledger.new_id("draft"), _now()
        scope_hash = hashlib.sha256(_json([identifier, owner, root, paths, dict(turn) if turn else None]).encode()).hexdigest()
        conn.execute(
            "INSERT INTO operation_drafts(id,owner_key,workspace,source_task_id,session_id,generation,paths_json,"
            "scope_hash,status,created_at,updated_at,expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (identifier, owner, root, record["task_id"], turn["session_id"] if turn else None,
             turn["generation"] if turn else None, _json(paths), scope_hash, "pending" if paths else "ready",
             timestamp, timestamp, (datetime.now(UTC) + timedelta(hours=1) if paths else
                                    datetime.now(UTC) + timedelta(days=30)).isoformat()),
        )
        return dict(conn.execute("SELECT * FROM operation_drafts WHERE id=?", (identifier,)).fetchone())


def describe(draft):
    paths = json.loads(draft["paths_json"])
    return (f"초안: {draft['id']} · {draft['status']} · 버전 {draft['revision']}\n"
            + "복사할 파일: " + (", ".join(paths) or "없음")
            + (f"\n복사·조회 승인: open-draft {draft['id']} {draft['scope_hash']}" if draft["status"] == "pending" else
               f"\n피드백: draft-feedback {draft['id']} <요청>\n종료: draft-close {draft['id']}"))


def open_and_submit(path, identifier, scope_hash, owner, generation, *, conversation_key=None):
    from dataclasses import replace
    from nyanya_agent import reviewed_changes as files, operation_store as store
    from nyanya_agent.context_security import sensitive_content
    from nyanya_agent.operation_spec import OperationSpec

    with db.connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        draft = conn.execute("SELECT * FROM operation_drafts WHERE id=?", (identifier,)).fetchone()
        root = str(store.check_workspace(draft["workspace"], owner)) if draft else ""
        _scope(conn, draft, owner, root, conversation_key=conversation_key)
        if draft["scope_hash"] != scope_hash or draft["expires_at"] <= _now():
            raise SafeOperationError("Draft read scope changed or expired")
        if draft["status"] == "ready" and draft["open_task_id"]:
            return ledger._parse_record(dict(conn.execute("SELECT * FROM agent_tasks WHERE id=?", (draft["open_task_id"],)).fetchone())), False
        source = conn.execute("SELECT t.*,o.spec_json FROM agent_tasks t JOIN task_operations o ON o.task_id=t.id WHERE t.id=?", (draft["source_task_id"],)).fetchone()
        if draft["status"] != "pending" or source["status"] != "awaiting_approval":
            raise SafeOperationError("Draft is not waiting for read-scope approval")
        snapshot, total = {}, 0
        for name in json.loads(draft["paths_json"]):
            data = files.read_file(root, name)
            if data is None:
                raise SafeOperationError("A planned input file is unavailable")
            total += len(data)
            if total > MAX_SNAPSHOT_BYTES:
                raise SafeOperationError("Draft input exceeds the snapshot limit")
            try:
                content = data.decode("utf-8")
            except UnicodeError as exc:
                raise SafeOperationError("Draft inputs must be UTF-8 text") from exc
            if "\0" in content or sensitive_content(content):
                raise SafeOperationError("Draft input is unsupported or contains sensitive data")
            snapshot[name] = {"content": content, "sha256": files.digest(data)}
        timestamp = _now()
        conn.execute("UPDATE operation_drafts SET status='ready',snapshot_json=?,revision=revision+1,updated_at=?,expires_at=? WHERE id=?",
                     (_json(snapshot), timestamp, (datetime.now(UTC) + timedelta(days=30)).isoformat(), identifier))
        _settle_review(conn, source["id"], "completed", "Read scope approved")
        conn.execute("UPDATE approvals SET status='approved',decided_by=?,decided_at=? WHERE task_id=? AND action='draft.read_scope' AND status='pending'",
                     (owner, timestamp, source["id"]))
        task = store._submit_conn(
            conn, replace(OperationSpec.loads(source["spec_json"]), draft_id=identifier), owner, generation,
            root=store.check_workspace(root, owner), parent_task_id=source["id"], conversation_key=conversation_key,
            project_id=source["project_id"],
        )
        conn.execute("UPDATE operation_drafts SET open_task_id=? WHERE id=?", (task["id"], identifier))
        ledger.append_event_conn(conn, task_id=source["id"], event_type="draft.scope_approved",
                                 message="Exact read scope approved; original files unchanged", metadata={"draft_id": identifier})
        return task, True


def active(path, owner, workspace, conversation_key):
    if conversation_key is None:
        return ""
    with db.connect(path) as conn:
        rows = conn.execute(
            "SELECT d.id FROM operation_drafts d JOIN conversation_sessions s ON s.id=d.session_id "
            "JOIN agent_tasks origin ON origin.id=d.source_task_id "
            "WHERE d.owner_key=? AND d.workspace=? AND s.conversation_hash=? AND d.generation=s.generation "
            "AND origin.project_id IS NULL AND d.status='ready' AND d.expires_at>? ORDER BY d.created_at DESC LIMIT 2",
            (owner, workspace, hashlib.sha256(conversation_key.encode()).hexdigest(), _now()),
        ).fetchall()
    if len(rows) > 1:
        raise SafeOperationError("Select an explicit draft before continuing")
    return rows[0]["id"] if rows else ""


def load(path, identifier, record):
    from nyanya_agent.operation_store import check_workspace

    root = str(check_workspace(record["spec"].workspace, record["owner"]))
    with db.connect(path) as conn:
        draft = conn.execute("SELECT * FROM operation_drafts WHERE id=?", (identifier,)).fetchone()
        _scope(conn, draft, record["owner"], root, task_id=record["task_id"])
        if draft["status"] != "ready" or draft["expires_at"] <= _now():
            raise SafeOperationError("Draft is not available for feedback")
        draft = dict(draft)
        draft["original"] = json.loads(draft["snapshot_json"])
        draft["changes"] = []
        if draft["plan_id"]:
            plan = conn.execute("SELECT * FROM change_plans WHERE id=?", (draft["plan_id"],)).fetchone()
            if plan["status"] != "pending":
                raise SafeOperationError("Finish or close the existing file plan before new feedback")
            draft["changes"] = json.loads(plan["changes_json"])
    return draft


def directory(identifier):
    if not isinstance(identifier, str) or not identifier.startswith("draft_") or not identifier[6:].isalnum():
        raise SafeOperationError("Invalid draft identity")
    return "nyanya-tasks/drafts/" + identifier


def current_snapshot(draft):
    from nyanya_agent.reviewed_changes import digest

    values = {name: dict(item) for name, item in draft["original"].items()}
    for change in draft["changes"]:
        if change["action"] == "delete":
            values[change["path"]]["pending_deletion"] = True
        else:
            values[change["path"]] = {"content": change["content"], "sha256": digest(change["content"].encode())}
    if sum(len(x["content"].encode()) for x in values.values()) > 2_000_000:
        raise SafeOperationError("Draft contents exceed the working-copy limit")
    return values


def merge(draft, changes):
    from nyanya_agent import reviewed_changes as files

    if not isinstance(changes, list) or len(changes) > 40:
        raise SafeOperationError("Invalid draft delta")
    combined = {x["path"]: {k: x[k] for k in ("path", "action", "content", "reason")} for x in draft["changes"]}
    seen, prefix = set(), directory(draft["id"]) + "/"
    for change in changes:
        if not isinstance(change, dict) or set(change) - {"path", "action", "content", "reason"}:
            raise SafeOperationError("Invalid draft change fields")
        name, action = str(files.relative(change["path"])), change["action"]
        if action not in {"create", "modify", "delete"}:
            raise SafeOperationError("Unsupported draft action")
        if action == "create" and not name.startswith(prefix):
            name = prefix + name
        if name in seen:
            raise SafeOperationError("Duplicate draft delta")
        seen.add(name)
        if name not in draft["original"]:
            if not name.startswith(prefix):
                raise SafeOperationError("A new input needs a separately approved read scope")
            previous = combined.get(name)
            if action != "create" and (not previous or previous["action"] != "create"):
                raise SafeOperationError("Draft target does not exist")
            if action == "delete":
                combined.pop(name, None)
                continue
            action = "create"
        elif action == "create":
            raise SafeOperationError("Creation cannot replace an existing input")
        if not isinstance(change.get("content", ""), str) or not isinstance(change.get("reason"), str) or not change["reason"].strip():
            raise SafeOperationError("Draft text and rationale are required")
        if action == "modify" and change["content"] == draft["original"][name]["content"]:
            combined.pop(name, None)
        else:
            combined[name] = {"path": name, "action": action, "content": change.get("content", ""), "reason": change["reason"]}
    if len(combined) > 40:
        raise SafeOperationError("Draft plan exceeds the file limit")
    return list(combined.values())


def link_plan_conn(conn, draft, task_id, plan_id):
    from nyanya_agent.operation_store import _unresolved_effects

    current = conn.execute("SELECT * FROM operation_drafts WHERE id=?", (draft["id"],)).fetchone()
    if not current or current["status"] != "ready" or current["revision"] != draft["revision"]:
        raise SafeOperationError("Draft changed while this result was running")
    _scope(conn, current, draft["owner_key"], draft["workspace"], task_id=task_id)
    if current["plan_id"]:
        previous = conn.execute("SELECT * FROM change_plans WHERE id=?", (current["plan_id"],)).fetchone()
        if previous["status"] != "pending" and not (previous["task_id"] == task_id and previous["status"] == "revoked"):
            raise SafeOperationError("The previous plan is already being applied or held")
        if previous["task_id"] != task_id and _unresolved_effects(conn, previous["task_id"]):
            raise SafeOperationError("The previous draft has uncertain execution evidence")
        conn.execute("UPDATE change_plans SET status='revoked' WHERE id=?", (previous["id"],))
        conn.execute("UPDATE approvals SET status='rejected',decided_at=? WHERE task_id=? AND status='pending'", (_now(), previous["task_id"]))
        if previous["task_id"] != task_id:
            _settle_review(conn, previous["task_id"], "completed", "Superseded by draft feedback")
    conn.execute("UPDATE operation_drafts SET plan_id=?,revision=revision+1,updated_at=? WHERE id=?", (plan_id, _now(), draft["id"]))


def require_plan_conn(conn, plan_id):
    draft = conn.execute(
        "SELECT d.* FROM operation_drafts d JOIN change_plans p ON p.id=? "
        "JOIN task_operations o ON o.task_id=p.task_id "
        "WHERE d.id=json_extract(o.spec_json,'$.draft_id') OR d.source_task_id=p.task_id",
        (plan_id,),
    ).fetchone()
    if draft and (draft["status"] != "ready" or draft["plan_id"] != plan_id):
        raise SafeOperationError("Only the latest open draft plan can be applied")


def show(path, identifier, owner, *, conversation_key=None):
    from nyanya_agent.operation_store import check_workspace

    with db.connect(path) as conn:
        draft = conn.execute("SELECT * FROM operation_drafts WHERE id=?", (identifier,)).fetchone()
        root = str(check_workspace(draft["workspace"], owner)) if draft else ""
        _scope(conn, draft, owner, root, conversation_key=conversation_key, current=False)
        return dict(draft)


def close(path, identifier, owner, *, conversation_key=None):
    from nyanya_agent.operation_store import _unresolved_effects

    draft = show(path, identifier, owner, conversation_key=conversation_key)
    with db.connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        live = conn.execute("SELECT * FROM operation_drafts WHERE id=?", (identifier,)).fetchone()
        if live["revision"] != draft["revision"]:
            raise SafeOperationError("Draft changed; refresh before closing")
        _scope(conn, live, owner, draft["workspace"], conversation_key=conversation_key, current=False)
        tasks = conn.execute("SELECT t.id,t.status FROM agent_tasks t JOIN task_operations o ON o.task_id=t.id "
                             "WHERE t.id=? OR json_extract(o.spec_json,'$.draft_id')=?", (draft["source_task_id"], identifier)).fetchall()
        if any(t["status"] in {"queued", "running", "cancelling"} or _unresolved_effects(conn, t["id"]) for t in tasks):
            raise SafeOperationError("Draft has active or uncertain work; preserve it for review")
        if live["status"] in {"closed", "applied"}:
            return
        if live["plan_id"]:
            plan = conn.execute("SELECT * FROM change_plans WHERE id=?", (live["plan_id"],)).fetchone()
            if plan["status"] not in {"pending", "revoked", "expired"}:
                raise SafeOperationError("Draft plan cannot be closed safely")
            if plan["status"] == "pending":
                conn.execute("UPDATE change_plans SET status='revoked' WHERE id=?", (plan["id"],))
        for task in tasks:
            if task["status"] == "awaiting_approval":
                _settle_review(conn, task["id"], "cancelled", "Draft explicitly closed")
                conn.execute("UPDATE approvals SET status='rejected',decided_at=? WHERE task_id=? AND status='pending'", (_now(), task["id"]))
        conn.execute("UPDATE operation_drafts SET status='closed',updated_at=?,revision=revision+1 WHERE id=?", (_now(), identifier))


def _settle_review(conn, task_id, status, reason):
    timestamp = _now()
    conn.execute("UPDATE agent_tasks SET status=?,completed_at=?,updated_at=? WHERE id=? AND status='awaiting_approval'",
                 (status, timestamp, timestamp, task_id))
    rows = conn.execute("SELECT id FROM executions WHERE task_id=? AND status='awaiting_approval'", (task_id,)).fetchall()
    for row in rows:
        conn.execute("UPDATE executions SET status=?,ended_at=?,updated_at=? WHERE id=?", ("succeeded" if status == "completed" else status, timestamp, timestamp, row["id"]))
        ledger.append_event_conn(conn, task_id=task_id, execution_id=row["id"], event_type="draft.review_closed",
                                 status=status, message=reason)


def maintain(path):
    """Clear only old, explicitly settled working copies; never plans or ledgers."""
    cutoff = (datetime.now(UTC) - timedelta(days=7)).isoformat()
    with db.connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        from nyanya_agent.operation_store import _unresolved_effects

        expired = conn.execute("SELECT * FROM operation_drafts WHERE status='pending' AND expires_at<? LIMIT 100", (_now(),)).fetchall()
        for draft in expired:
            task = conn.execute("SELECT status FROM agent_tasks WHERE id=?", (draft["source_task_id"],)).fetchone()
            if task["status"] == "awaiting_approval" and not _unresolved_effects(conn, draft["source_task_id"]):
                _settle_review(conn, draft["source_task_id"], "cancelled", "Read scope expired without copying files")
                conn.execute("UPDATE approvals SET status='expired',decided_at=? WHERE task_id=? AND action='draft.read_scope' AND status='pending'", (_now(), draft["source_task_id"]))
                conn.execute("UPDATE operation_drafts SET status='closed',updated_at=?,revision=revision+1 WHERE id=?", (_now(), draft["id"]))
        conn.execute("UPDATE operation_drafts SET snapshot_json='{}' WHERE id IN (SELECT id FROM operation_drafts "
                     "WHERE status IN ('closed','applied') AND updated_at<? AND snapshot_json!='{}' LIMIT 100)", (cutoff,))
