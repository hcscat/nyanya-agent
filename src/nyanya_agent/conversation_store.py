"""Durable conversation relations; task prompts/results remain authoritative.

History is untrusted provider context, never permission or executable recovery.
Reset only advances a context generation and leaves every workflow row intact.
"""

from datetime import UTC, datetime
import hashlib
import json
import re

from nyanya_agent import database as db, execution_store as ledger
from nyanya_agent.context_security import sensitive_content
from nyanya_agent.task_outcomes import SafeOperationError

MAX_CONTEXT_BYTES = 24 * 1024
MAX_TURNS = 8
MAX_RECALL_TURNS = 4
MAX_TOTAL_TURNS = MAX_TURNS + MAX_RECALL_TURNS


def _now():
    return datetime.now(UTC).isoformat()


def _hash(key):
    if not isinstance(key, str) or not key or len(key.encode()) > 4096:
        raise SafeOperationError("Invalid conversation key")
    return hashlib.sha256(key.encode()).hexdigest()


def _workspace(workspace, owner):
    from nyanya_agent.operation_store import check_workspace

    return str(check_workspace(workspace, owner))


def _session_conn(conn, owner, conversation_key, workspace):
    timestamp = _now()
    hashed = _hash(conversation_key)
    conn.execute(
        "INSERT INTO conversation_sessions(id,owner_key,conversation_hash,workspace_root,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?) ON CONFLICT(owner_key,conversation_hash,workspace_root) DO NOTHING",
        (ledger.new_id("conversation"), owner, hashed, workspace, timestamp, timestamp),
    )
    session = conn.execute(
        "SELECT * FROM conversation_sessions WHERE owner_key=? AND conversation_hash=? AND workspace_root=?",
        (owner, hashed, workspace),
    ).fetchone()
    return session


def bind_conn(conn, *, task_id, owner, conversation_key, workspace):
    """Caller owns the intake transaction and has checked workspace registration."""
    task = conn.execute(
        "SELECT t.requested_by,t.metadata_json,o.spec_json FROM agent_tasks t "
        "JOIN task_operations o ON o.task_id=t.id WHERE t.id=?", (task_id,),
    ).fetchone()
    if not task or task["requested_by"] != owner:
        raise PermissionError("Conversation task owner mismatch")
    spec = json.loads(task["spec_json"])
    if spec.get("kind") != "request" or spec.get("workspace") != workspace:
        raise PermissionError("Conversation task workspace or kind mismatch")
    prior = conn.execute("SELECT * FROM conversation_turns WHERE task_id=?", (task_id,)).fetchone()
    if prior:
        scope = conn.execute("SELECT * FROM conversation_sessions WHERE id=?", (prior["session_id"],)).fetchone()
        if (scope["owner_key"], scope["conversation_hash"], scope["workspace_root"]) != (owner, _hash(conversation_key), workspace):
            raise PermissionError("Conversation intake scope mismatch")
        return dict(prior)
    session = _session_conn(conn, owner, conversation_key, workspace)
    previous = conn.execute(
        "SELECT task_id FROM conversation_turns WHERE session_id=? AND generation=? ORDER BY sequence DESC LIMIT 1",
        (session["id"], session["generation"]),
    ).fetchone()
    timestamp = _now()
    conn.execute(
        "INSERT INTO conversation_turns(task_id,session_id,generation,sequence,related_task_id,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (task_id, session["id"], session["generation"], session["next_sequence"],
         previous["task_id"] if previous else None, timestamp, timestamp),
    )
    conn.execute(
        "UPDATE conversation_sessions SET next_sequence=next_sequence+1,updated_at=?,"
        "pending_task_id=NULL,pending_execution_id=NULL WHERE id=?", (timestamp, session["id"]),
    )
    return dict(conn.execute("SELECT * FROM conversation_turns WHERE task_id=?", (task_id,)).fetchone())


def has_earlier_work_conn(conn, task_id):
    """Active turns block both directions; eligible queued turns retain sequence order."""
    return bool(conn.execute(
        "SELECT 1 FROM conversation_turns current JOIN conversation_turns earlier "
        "ON earlier.session_id=current.session_id AND earlier.generation=current.generation "
        "AND earlier.task_id<>current.task_id JOIN agent_tasks t ON t.id=earlier.task_id "
        "JOIN task_operations o ON o.task_id=t.id WHERE current.task_id=? "
        "AND (t.status IN ('running','cancelling') OR "
        "(earlier.sequence<current.sequence AND t.status='queued' AND o.eligible=1 "
        "AND o.attempts<o.max_attempts)) LIMIT 1", (task_id,),
    ).fetchone())


def complete_conn(conn, record, outcome):
    """Called after work_queue's live claim fence and authoritative result insertion."""
    task_id, execution_id = record["task_id"], record["execution_id"]
    turn = conn.execute(
        "SELECT c.*,s.generation AS live_generation,s.next_sequence FROM conversation_turns c "
        "JOIN conversation_sessions s ON s.id=c.session_id JOIN agent_tasks t ON t.id=c.task_id "
        "JOIN task_results r ON r.execution_id=t.current_execution_id "
        "WHERE c.task_id=? AND t.current_execution_id=? AND r.execution_id=?",
        (task_id, execution_id, execution_id),
    ).fetchone()
    if not turn or turn["generation"] != turn["live_generation"]:
        return
    kind = record.get("reply_kind", "answer")
    if kind not in {"answer", "question"}:
        kind = "answer"
    timestamp = _now()
    conn.execute(
        "UPDATE conversation_turns SET reply_kind=?,completed_execution_id=?,updated_at=? WHERE task_id=?",
        (kind, execution_id, timestamp, task_id),
    )
    if turn["sequence"] == turn["next_sequence"] - 1:
        question = outcome.status == "succeeded" and kind == "question"
        conn.execute(
            "UPDATE conversation_sessions SET pending_task_id=?,pending_execution_id=?,updated_at=? "
            "WHERE id=? AND generation=?",
            (task_id if question else None, execution_id if question else None,
             timestamp, turn["session_id"], turn["generation"]),
        )


def _serialize(conn, session, *, before_sequence=None, query="", project_id=None, max_bytes=MAX_CONTEXT_BYTES):
    from nyanya_agent.work_memory import _storage_disabled

    if type(max_bytes) is not int or max_bytes < 2:
        raise ValueError("Conversation context limit must allow an empty JSON object")
    limit = min(max_bytes, MAX_CONTEXT_BYTES)
    params = [session["id"], session["memory_reset_generation"], session["owner_key"], session["workspace_root"]]
    before = ""
    if before_sequence is not None:
        before = " AND (c.generation<? OR (c.generation=? AND c.sequence<?)) AND t.project_id IS ?"
        params.extend([session["generation"], session["generation"], before_sequence, project_id])
    sql = (
        "SELECT c.*,t.prompt,t.status,t.current_execution_id,r.outcome,r.response,r.delivery_status, "
        "(SELECT p.status FROM change_plans p WHERE p.task_id=t.id AND p.owner_key=t.requested_by "
        "AND p.workspace=json_extract(t.metadata_json,'$.workspace_root') "
        "ORDER BY p.created_at DESC,p.rowid DESC LIMIT 1) AS current_plan_status "
        "FROM conversation_turns c JOIN agent_tasks t ON t.id=c.task_id "
        "JOIN task_operations o ON o.task_id=t.id LEFT JOIN task_results r ON r.execution_id=t.current_execution_id "
        "WHERE c.session_id=? AND c.generation>=? AND t.requested_by=? "
        "AND json_extract(o.spec_json,'$.workspace')=? "
        "AND NOT EXISTS (SELECT 1 FROM task_work_records m WHERE m.status='forgotten' "
        "AND m.source_task_id=c.task_id)" + before
    )
    rows = conn.execute(sql + " ORDER BY c.generation DESC,c.sequence DESC LIMIT ?", [*params, MAX_TURNS]).fetchall()
    recent_ids = [row["task_id"] for row in rows]
    # Search the existing ledger, not a second transcript or an extra model call.
    # LIMIT bounds materialized context; older matching turns remain searchable.
    tokens = list(dict.fromkeys(re.findall(r"[\w가-힣]{2,}", query[:2048].casefold())))[:8]
    if tokens and rows:
        matches = " OR ".join("instr(lower(t.prompt || ' ' || coalesce(r.response,'')),?)>0" for _ in tokens)
        placeholders = ",".join("?" for _ in recent_ids)
        older = conn.execute(
            sql + f" AND c.task_id NOT IN ({placeholders}) AND ({matches}) "
            "ORDER BY c.generation DESC,c.sequence DESC LIMIT ?",
            [*params, *recent_ids, *tokens, MAX_RECALL_TURNS],
        ).fetchall()
        rows = sorted([*rows, *older], key=lambda row: (row["generation"], row["sequence"]), reverse=True)
    turns = []
    for row in reversed(rows):
        request, response = row["prompt"], row["response"] or ""
        if _storage_disabled(request):
            continue
        if len(request.encode()) + len(response.encode()) > limit:
            continue
        if sensitive_content(request) or sensitive_content(response):
            continue
        turns.append({
            "task_id": row["task_id"], "request": request, "response": response,
            "context_source": "recent" if row["task_id"] in recent_ids else "related_earlier_turn",
            "outcome": row["outcome"] or row["status"],
            "current_task_status": row["status"],
            "current_plan_status": row["current_plan_status"],
            "delivery_status": row["delivery_status"] or "no_saved_result",
            "reply_kind": row["reply_kind"] if row["completed_execution_id"] == row["current_execution_id"] else "answer",
            "pending_question": bool(session["pending_task_id"] == row["task_id"]
                                     and session["pending_execution_id"] == row["current_execution_id"]
                                     and row["outcome"] == "succeeded"),
        })
    while turns:
        value = json.dumps({"kind": "untrusted_conversation_history", "generation": session["generation"],
                            "evidence": "Saved attempt outcome, response and delivery; current task and plan lifecycle are separate.",
                            "turns": turns}, ensure_ascii=False, separators=(",", ":"))
        # Escaping can change assignment-like patterns; never bypass the final transfer filter.
        if len(value.encode()) <= limit and not sensitive_content(value):
            return value
        turns.pop(0)
    return "{}"


def worker_context(path, task_id, owner, workspace, *, max_bytes=MAX_CONTEXT_BYTES):
    root = _workspace(workspace, owner)
    ledger.apply_migrations(path)
    with db.connect(path) as conn:
        conn.execute("BEGIN")
        turn = conn.execute(
            "SELECT c.*,s.owner_key,s.workspace_root,s.generation AS live_generation FROM conversation_turns c "
            "JOIN conversation_sessions s ON s.id=c.session_id WHERE c.task_id=?", (task_id,),
        ).fetchone()
        if not turn:
            return "{}"
        if turn["owner_key"] != owner or turn["workspace_root"] != root:
            raise PermissionError("Conversation context scope mismatch")
        task = conn.execute("SELECT requested_by,metadata_json,prompt,project_id FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
        if (task["requested_by"] != owner
                or ledger.decode_json(task["metadata_json"], {}).get("workspace_root") != root):
            raise PermissionError("Conversation task scope mismatch")
        if turn["generation"] != turn["live_generation"]:
            return "{}"
        session = conn.execute("SELECT * FROM conversation_sessions WHERE id=?", (turn["session_id"],)).fetchone()
        return _serialize(conn, session, before_sequence=turn["sequence"], query=task["prompt"],
                          project_id=task["project_id"], max_bytes=max_bytes)


def snapshot(path, owner, conversation_key, workspace, *, max_bytes=MAX_CONTEXT_BYTES):
    """Screened export of current history, for an explicit owner-scoped save action."""
    root = _workspace(workspace, owner)
    ledger.apply_migrations(path)
    with db.connect(path) as conn:
        conn.execute("BEGIN")
        session = conn.execute(
            "SELECT * FROM conversation_sessions WHERE owner_key=? AND conversation_hash=? AND workspace_root=?",
            (owner, _hash(conversation_key), root),
        ).fetchone()
        return _serialize(conn, session, max_bytes=max_bytes) if session else "{}"


def reset(path, owner, conversation_key, workspace):
    root = _workspace(workspace, owner)
    ledger.apply_migrations(path)
    with db.connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        session = _session_conn(conn, owner, conversation_key, root)
        conn.execute(
            "UPDATE conversation_sessions SET generation=generation+1,memory_reset_generation=generation+1,"
            "next_sequence=1,pending_task_id=NULL,"
            "pending_execution_id=NULL,updated_at=? WHERE id=?", (_now(), session["id"]),
        )
        return session["generation"] + 1
