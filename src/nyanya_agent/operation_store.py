"""Transactional execution authority for serializable operations."""

from nyanya_agent.task_outcomes import SafeOperationError
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from nyanya_agent import execution_store as ledger, database as db
from nyanya_agent.operation_spec import OperationSpec
from nyanya_agent import work_queue, conversation_store


def now():
    return datetime.now(UTC).isoformat()


def check_workspace(workspace, owner):
    from nyanya_agent.bridge_policy import is_allowed_workspace_path, workspace_config_path

    root = Path(workspace).resolve(strict=True)
    if not root.is_dir() or root == Path(root.anchor) or not is_allowed_workspace_path(root):
        raise SafeOperationError("Workspace is not explicitly allowed")
    if owner.startswith(("discord-user:", "telegram-user:")):
        config = json.loads(workspace_config_path().read_text())
        assigned = config.get("users", {}).get(owner, {}).get("workspace", "")
        if not assigned or Path(assigned).resolve(strict=True) != root:
            raise PermissionError("Workspace registration does not match task owner")
    return root


def register_worker(path, worker_id):
    ledger.apply_migrations(path)
    with db.connect(path) as conn:
        conn.execute("INSERT INTO operation_workers(id,heartbeat_at) VALUES (?,?)", (worker_id, now()))


def heartbeat(path, worker_id, closed=False):
    with db.connect(path) as conn:
        conn.execute("UPDATE operation_workers SET heartbeat_at=?,closed=? WHERE id=?", (now(), int(closed), worker_id))


def _existing_apply_conn(conn, plan_id, owner, workspace):
    rows = conn.execute(
        "SELECT t.*,o.parent_task_id FROM agent_tasks t JOIN task_operations o ON o.task_id=t.id "
        "WHERE json_extract(o.spec_json,'$.kind')='apply' AND json_extract(o.spec_json,'$.plan_id')=?",
        (plan_id,),
    ).fetchall()
    if len(rows) > 1:
        raise SafeOperationError("Multiple legacy apply tasks require recovery review")
    if not rows:
        return None
    row = rows[0]
    plan = conn.execute("SELECT * FROM change_plans WHERE id=? AND owner_key=?", (plan_id, owner)).fetchone()
    if (not plan or row["requested_by"] != owner or plan["workspace"] != workspace
            or row["parent_task_id"] != plan["task_id"]
            or json.loads(row["metadata_json"]).get("workspace_root") != workspace):
        raise PermissionError("Existing apply admission scope mismatch")
    if plan["status"] not in {"approved", "applying", "applied", "uncertain", "reconciled"}:
        raise SafeOperationError("Existing apply plan is no longer eligible")
    return ledger._parse_record(dict(row))


def submit(path, spec, owner, generation, *, source_request_id=None, project_id=None, parent_task_id=None, conversation_key=None):
    spec.validate()
    root = check_workspace(spec.workspace, owner)
    ledger.apply_migrations(path)
    with db.connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        return _submit_conn(conn, spec, owner, generation, root=root, source_request_id=source_request_id,
                            project_id=project_id, parent_task_id=parent_task_id, conversation_key=conversation_key)


def _submit_conn(conn, spec, owner, generation, *, root, source_request_id=None, project_id=None,
                 parent_task_id=None, conversation_key=None):
    """The caller owns the write transaction; every apply intake checks the same admission."""
    timestamp, task_id = now(), ledger.new_id("task")
    worker = conn.execute("SELECT * FROM operation_workers WHERE id=?", (generation,)).fetchone()
    cutoff = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
    if not worker or worker["closed"] or worker["heartbeat_at"] < cutoff:
        raise SafeOperationError("Worker not ready")
    if source_request_id:
        prior = conn.execute(
            "SELECT id FROM agent_tasks WHERE source_request_id=?", (source_request_id,)
        ).fetchone()
        if prior:
            previous = conn.execute("SELECT requested_by FROM agent_tasks WHERE id=?", (prior["id"],)).fetchone()
            if previous["requested_by"] != owner:
                raise PermissionError("Intake belongs to another owner")
            if conn.execute("SELECT 1 FROM task_operations WHERE task_id=?", (prior["id"],)).fetchone():
                if conversation_key is not None and conn.execute(
                    "SELECT 1 FROM conversation_turns WHERE task_id=?", (prior["id"],)
                ).fetchone():
                    conversation_store.bind_conn(
                        conn, task_id=prior["id"], owner=owner,
                        conversation_key=conversation_key, workspace=str(root)
                    )
                return ledger._parse_record(
                    dict(conn.execute("SELECT * FROM agent_tasks WHERE id=?", (prior["id"],)).fetchone())
                )
            # Intake rows may have been imported by an older connector; never adopt a started task.
            row = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (prior["id"],)).fetchone()
            if row["status"] != "queued":
                raise SafeOperationError("Existing intake requires recovery review")
            if row["current_execution_id"]:
                old = conn.execute("SELECT * FROM executions WHERE id=?", (row["current_execution_id"],)).fetchone()
                if old["status"] != "pending" or not json.loads(old["metadata_json"]).get("legacy"):
                    raise SafeOperationError("Existing execution requires recovery review")
                conn.execute(
                    "UPDATE executions SET status='cancelled',ended_at=? WHERE id=?", (timestamp, old["id"])
                )
            task_id = row["id"]
    if spec.kind == "apply":
        existing = _existing_apply_conn(conn, spec.plan_id, owner, str(root))
        if existing:
            return existing
        plan = conn.execute(
            "SELECT * FROM change_plans WHERE id=? AND owner_key=?", (spec.plan_id, owner)
        ).fetchone()
        if not plan or plan["workspace"] != str(root) or plan["status"] != "approved":
            raise SafeOperationError("Apply operation must match its approved plan owner and workspace")
        parent_task_id = plan["task_id"]
    metadata = ledger.encode_json(
        {
            "owner_key": owner,
            "workspace_root": str(root),
            "operation_version": 1,
            "durable_execution": True,
            "interface": owner.split(":")[0],
        }
    )
    conn.execute(
        "INSERT INTO agent_tasks(id,source_request_id,title,prompt,requested_by,metadata_json,created_at,updated_at,project_id) "
        "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET metadata_json=excluded.metadata_json,requested_by=excluded.requested_by,prompt=excluded.prompt,title=excluded.title,current_execution_id=NULL",
        (
            task_id,
            source_request_id,
            ledger.redact(spec.prompt[:160] or "Apply reviewed plan"),
            ledger.redact(spec.prompt),
            owner,
            metadata,
            timestamp,
            timestamp,
            project_id,
        ),
    )
    conn.execute(
        "INSERT INTO task_operations(task_id,spec_json,worker_generation,parent_task_id) VALUES (?,?,?,?)",
        (task_id, spec.dumps(), generation, parent_task_id),
    )
    if conversation_key is not None and spec.kind == "request":
        conversation_store.bind_conn(
            conn, task_id=task_id, owner=owner, conversation_key=conversation_key, workspace=str(root)
        )
    ledger.append_event_conn(
        conn,
        task_id=task_id,
        event_type="operation.accepted",
        status="queued",
        message="Serializable operation accepted",
    )
    return ledger._parse_record(dict(conn.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()))


def approve_and_submit_apply(path, plan_id, owner, plan_hash, generation):
    """Approve and admit exactly one child under SQLite's cross-process writer lock.

    Existing task/spec/plan relations are the durable admission identity. Conflicting
    legacy duplicates are held for review, never selected or deleted automatically.
    """
    from nyanya_agent import reviewed_changes

    ledger.apply_migrations(path)
    with db.connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        plan = conn.execute("SELECT * FROM change_plans WHERE id=? AND owner_key=?", (plan_id, owner)).fetchone()
        if not plan or plan["plan_hash"] != plan_hash:
            raise SafeOperationError("Plan owner or revision hash mismatch")
        root = check_workspace(plan["workspace"], owner)
        existing = _existing_apply_conn(conn, plan_id, owner, str(root))
        if existing:
            return existing, False
        reviewed_changes.decide_conn(conn, plan_id, owner, plan_hash)
        spec = OperationSpec(kind="apply", prompt="승인된 파일 변경안 적용", workspace=str(root), plan_id=plan_id)
        return _submit_conn(conn, spec, owner, generation, root=root), True


def record_start_failure(path, task_id, owner, error_type):
    """Persist a deliverable diagnosis when no provider attempt could start."""
    timestamp = now()
    diagnosis = f"Worker 시작 실패 ({error_type}). 실행 환경을 확인한 뒤 resume 작업ID로 재개하세요."
    with db.connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        task = conn.execute("SELECT status,current_execution_id,prompt FROM agent_tasks WHERE id=? AND requested_by=?",
                            (task_id, owner)).fetchone()
        if not task:
            raise PermissionError("Task owner mismatch")
        if task["status"] != "blocked" or task["current_execution_id"]:
            return
        execution_id = ledger.new_id("exec")
        response = f"원래 요청: {task['prompt']}\n{diagnosis}"
        conn.execute("INSERT INTO executions(id,task_id,adapter_type,status,error,metadata_json,created_at,"
                     "ended_at,updated_at) VALUES (?,?,'operation','failed',?,'{}',?,?,?)",
                     (execution_id, task_id, diagnosis, timestamp, timestamp, timestamp))
        conn.execute("INSERT INTO task_results(execution_id,task_id,outcome,response,created_at,updated_at) "
                     "VALUES (?,?,'blocked',?,?,?)", (execution_id, task_id, response, timestamp, timestamp))
        conn.execute("UPDATE agent_tasks SET current_execution_id=?,updated_at=? WHERE id=?",
                     (execution_id, timestamp, task_id))
        conn.execute("UPDATE task_operations SET hold_reason='worker_start_failed',diagnosis=? WHERE task_id=?",
                     (diagnosis, task_id))
        ledger.append_event_conn(conn, task_id=task_id, execution_id=execution_id,
                                 event_type="operation.worker_start_failed", status="blocked",
                                 message="Worker did not start; no model attempt ran")


def hold_legacy_for_quiesced_upgrade(path, *, writers_stopped, reason):
    """Explicit post-backup upgrade step, never called by startup/recover/claim.

    The caller must prove all old writers and their children stopped first; this
    assertion is not process verification. Requires the additive v4 migration.
    Preserve legacy records without inventing executable specs or replaying work.
    """
    if writers_stopped is not True or not isinstance(reason, str) or not reason.strip():
        raise SafeOperationError("Quiesced upgrade requires stopped writers and an audit reason")
    timestamp = now()
    reason = ledger.redact(reason.strip())
    with db.connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT t.* FROM agent_tasks t LEFT JOIN task_operations o ON o.task_id=t.id "
            "WHERE o.task_id IS NULL AND ("
            "(t.status NOT IN ('completed','cancelled','failed') AND NOT EXISTS "
            "(SELECT 1 FROM execution_events v WHERE v.task_id=t.id "
            "AND v.event_type='operation.legacy_upgrade_held')) OR EXISTS "
            "(SELECT 1 FROM executions e WHERE e.task_id=t.id "
            "AND e.status NOT IN ('succeeded','failed','cancelled','timed_out','lost')) OR EXISTS "
            "(SELECT 1 FROM task_claims c WHERE c.task_id=t.id AND c.released=0))"
        ).fetchall()
        for row in rows:
            status = row["status"] if row["status"] in ledger.TASK_TERMINAL_STATUSES else "blocked"
            metadata = ledger.decode_json(row["metadata_json"], {})
            metadata["legacy_upgrade_hold"] = {"reason": reason, "at": timestamp}
            conn.execute(
                "UPDATE agent_tasks SET status=?,updated_at=?,metadata_json=? WHERE id=?",
                (status, timestamp, ledger.encode_json(metadata), row["id"]),
            )
            attempts = conn.execute(
                "SELECT id,status FROM executions WHERE task_id=? "
                "AND status NOT IN ('succeeded','failed','cancelled','timed_out','lost')", (row["id"],)
            ).fetchall()
            for attempt in attempts:
                conn.execute(
                    "UPDATE executions SET status='lost',error=?,ended_at=?,updated_at=? WHERE id=?",
                    (reason, timestamp, timestamp, attempt["id"]),
                )
                ledger.append_event_conn(
                    conn, task_id=row["id"], execution_id=attempt["id"],
                    event_type="execution.legacy_upgrade_held", status="lost", message=reason,
                    metadata={"previous_status": attempt["status"]},
                )
            released = conn.execute(
                "UPDATE task_claims SET released=1,expires_at=? WHERE task_id=? AND released=0",
                (timestamp, row["id"]),
            ).rowcount
            conn.execute(
                "UPDATE writer_leases SET expires_at=? WHERE owner_id IN "
                "(SELECT id FROM executions WHERE task_id=?) AND expires_at>?",
                (timestamp, row["id"], timestamp),
            )
            ledger.append_event_conn(
                conn, task_id=row["id"], execution_id=row["current_execution_id"],
                event_type="operation.legacy_upgrade_held", status=status, message=reason,
                metadata={"previous_status": row["status"], "claims_released": released,
                          "writers_stopped_asserted": True},
            )
        return len(rows)


def require_apply_ownership(conn, record, plan, owner):
    """Check a product worker's current operation, execution and unexpired claim."""
    if not record or not all(record.get(key) for key in ("task_id", "execution_id", "worker_id")):
        raise SafeOperationError("File apply requires the current worker record")
    timestamp = now()
    cutoff = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
    row = conn.execute(
        "SELECT o.spec_json,o.parent_task_id FROM agent_tasks t "
        "JOIN task_operations o ON o.task_id=t.id "
        "JOIN task_claims c ON c.task_id=t.id AND c.execution_id=t.current_execution_id "
        "JOIN executions e ON e.id=c.execution_id AND e.task_id=t.id "
        "JOIN operation_workers w ON w.id=c.worker_id AND w.id=o.worker_generation "
        "WHERE t.id=? AND c.execution_id=? AND c.worker_id=? AND t.requested_by=? "
        "AND c.owner_key=? AND t.status='running' AND e.status='running' "
        "AND e.adapter_type='operation' AND o.eligible=1 AND c.released=0 "
        "AND c.expires_at>? AND w.closed=0 AND w.heartbeat_at>?",
        (record["task_id"], record["execution_id"], record["worker_id"], owner, owner, timestamp, cutoff),
    ).fetchone()
    if not row:
        raise SafeOperationError("File apply lost current operation execution/claim ownership")
    spec = OperationSpec.loads(row["spec_json"])
    if spec.workspace != plan["workspace"] or (
        spec.kind == "apply" and (spec.plan_id != plan["id"] or row["parent_task_id"] != plan["task_id"])
    ) or (
        spec.kind == "request" and (
            record["task_id"] != plan["task_id"] or any(x["action"] != "create" for x in plan["changes"])
        )
    ):
        raise SafeOperationError("File apply does not match the claimed operation")


def recover(path):
    cutoff = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
    with db.connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT o.task_id,t.current_execution_id FROM task_operations o "
            "JOIN agent_tasks t ON t.id=o.task_id JOIN operation_workers w ON w.id=o.worker_generation "
            "LEFT JOIN task_claims c ON c.task_id=t.id "
            "WHERE o.eligible=1 AND (w.closed=1 OR w.heartbeat_at<? OR (c.released=0 AND c.expires_at<=?)) "
            "AND t.status IN ('queued','running','cancelling')",
            (cutoff, now()),
        ).fetchall()
        for row in rows:
            reason = "실행 worker가 종료되었거나 heartbeat/claim lease가 만료되었습니다. 실제 외부 실행 종료 여부는 확인되지 않았습니다."
            conn.execute(
                "UPDATE task_operations SET eligible=0,hold_reason=?,diagnosis=? WHERE task_id=?",
                ("worker_interrupted", reason, row["task_id"]),
            )
            conn.execute("UPDATE agent_tasks SET status='blocked',updated_at=? WHERE id=?", (now(), row["task_id"]))
            if row["current_execution_id"]:
                conn.execute(
                    "UPDATE executions SET status='lost',error=?,ended_at=?,updated_at=? WHERE id=? AND status NOT IN ('succeeded','failed','cancelled','timed_out','lost')",
                    (reason, now(), now(), row["current_execution_id"]),
                )
                conn.execute("UPDATE task_claims SET released=1 WHERE task_id=?", (row["task_id"],))
            ledger.append_event_conn(
                conn,
                task_id=row["task_id"],
                execution_id=row["current_execution_id"],
                event_type="operation.interrupted",
                status="blocked",
                message=reason,
            )
        return len(rows)


def claim(path, generation, slots=2):
    timestamp = now()
    with db.connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        count = conn.execute(
            "SELECT count(*) FROM task_claims c JOIN task_operations o ON o.task_id=c.task_id WHERE c.released=0"
        ).fetchone()[0]
        if count >= slots:
            return None
        rows = conn.execute(
            "SELECT t.*,o.spec_json,o.attempts,o.max_attempts FROM agent_tasks t JOIN task_operations o ON o.task_id=t.id "
            "WHERE t.status='queued' AND o.eligible=1 AND o.worker_generation=? AND o.attempts<o.max_attempts "
            "ORDER BY t.priority,t.created_at,t.rowid",
            (generation,),
        ).fetchall()
        for row in rows:
            if conversation_store.has_earlier_work_conn(conn, row["id"]):
                continue
            spec = OperationSpec.loads(row["spec_json"])
            # Requests can read concurrently. Applying changes waits for readers/writers of the same workspace.
            active = conn.execute(
                "SELECT o.spec_json FROM task_claims c JOIN task_operations o ON o.task_id=c.task_id WHERE c.released=0"
            ).fetchall()
            if any(
                (other := OperationSpec.loads(x["spec_json"])).workspace == spec.workspace
                and ("apply" in (spec.kind, other.kind))
                for x in active
            ):
                continue
            execution_id = ledger.new_id("exec")
            conn.execute(
                "INSERT INTO executions(id,task_id,adapter_type,status,workdir,metadata_json,created_at,started_at,updated_at,last_heartbeat_at) "
                "VALUES (?,?,'operation','running',?,?,?,?,?,?)",
                (
                    execution_id,
                    row["id"],
                    spec.workspace,
                    ledger.encode_json({"worker_id": generation}),
                    timestamp,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            conn.execute("DELETE FROM task_claims WHERE task_id=? AND released=1", (row["id"],))
            conn.execute(
                "INSERT INTO task_claims(task_id,worker_id,owner_key,execution_id,expires_at) VALUES (?,?,?,?,?)",
                (
                    row["id"],
                    generation,
                    row["requested_by"],
                    execution_id,
                    (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
                ),
            )
            conn.execute(
                "UPDATE agent_tasks SET status='running',current_execution_id=?,updated_at=? WHERE id=?",
                (execution_id, timestamp, row["id"]),
            )
            conn.execute("UPDATE task_operations SET attempts=attempts+1 WHERE task_id=?", (row["id"],))
            ledger.append_event_conn(
                conn,
                task_id=row["id"],
                execution_id=execution_id,
                event_type="operation.claimed",
                status="running",
                message="Worker claimed operation",
            )
            return {
                "task_id": row["id"],
                "worker_id": generation,
                "execution_id": execution_id,
                "spec": spec,
                "owner": row["requested_by"],
            }
    return None


def has_queued(path, generation):
    """Avoid a write transaction when this worker has no eligible work."""
    with db.connect(path) as conn:
        return bool(conn.execute(
            "SELECT 1 FROM agent_tasks t JOIN task_operations o ON o.task_id=t.id "
            "WHERE t.status='queued' AND o.eligible=1 AND o.worker_generation=? "
            "AND o.attempts<o.max_attempts LIMIT 1", (generation,),
        ).fetchone())


def watch_attempt(path, task_id, owner):
    """Bind a responder watcher to the next or already-started attempt."""
    with db.connect(path) as conn:
        row = conn.execute(
            "SELECT o.attempts,t.status FROM task_operations o JOIN agent_tasks t ON t.id=o.task_id "
            "WHERE t.id=? AND t.requested_by=?", (task_id, owner),
        ).fetchone()
    if not row:
        raise PermissionError("Task owner mismatch")
    return row["attempts"] + (row["status"] == "queued")


def delivery_state(path, task_id, owner):
    """One bounded read for watcher task, attempt and saved current result."""
    with db.connect(path) as conn:
        row = conn.execute(
            "SELECT t.status,t.current_execution_id,o.attempts,r.execution_id,r.outcome,"
            "r.response,r.delivery_status FROM agent_tasks t "
            "JOIN task_operations o ON o.task_id=t.id "
            "LEFT JOIN task_results r ON r.execution_id=t.current_execution_id "
            "WHERE t.id=? AND t.requested_by=?", (task_id, owner),
        ).fetchone()
    return dict(row) if row else None


def claim_delivery(path, task_id, owner, execution_id, attempt):
    """A pending result can have exactly one sender, even across controllers."""
    with db.connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        changed = conn.execute(
            "UPDATE task_results SET delivery_status='sending',updated_at=? "
            "WHERE execution_id=? AND delivery_status='pending' AND EXISTS ("
            "SELECT 1 FROM agent_tasks t JOIN task_operations o ON o.task_id=t.id "
            "WHERE t.id=? AND t.requested_by=? AND t.current_execution_id=? "
            "AND o.attempts=? AND ((task_results.outcome='succeeded' AND t.status='completed') "
            "OR (task_results.outcome IN ('failed','timed_out') AND t.status='failed') "
            "OR (task_results.outcome='awaiting_approval' AND t.status='awaiting_approval') "
            "OR (task_results.outcome='cancelled' AND t.status='cancelled') "
            "OR (task_results.outcome='blocked' AND t.status='blocked')))",
            (now(), execution_id, task_id, owner, execution_id, attempt),
        ).rowcount
        return changed == 1


def settle_delivery(path, execution_id, *, delivered, error=""):
    """Only the sender can settle a claimed result; uncertain sends stay held."""
    with db.connect(path) as conn:
        conn.execute("UPDATE task_results SET delivery_status=?,delivery_error=?,updated_at=? "
                     "WHERE execution_id=? AND delivery_status='sending'",
                     ("delivered" if delivered else "uncertain", error, now(), execution_id))


def assessment(path, task_id, value):
    from nyanya_agent.model_routing import route

    profile = route(value)
    with db.connect(path) as conn:
        conn.execute(
            "UPDATE task_operations SET assessment_json=? WHERE task_id=?",
            (ledger.encode_json(ledger.redact(value)), task_id),
        )
        conn.execute(
            "UPDATE agent_tasks SET priority=? WHERE id=?", (100 - value["importance"] * 10 - value["impact"], task_id)
        )
        ledger.append_event_conn(
            conn, task_id=task_id, event_type="operation.routed", message=f"Selected profile: {profile}", metadata=value
        )
    return profile


def incomplete(path, owner, exclude=None):
    with db.connect(path) as conn:
        rows = conn.execute(
            "SELECT t.id,t.title,t.prompt,t.status,o.hold_reason,"
            "COALESCE(o.diagnosis,json_extract(t.metadata_json,'$.legacy_upgrade_hold.reason')) AS diagnosis,"
            "json_extract(t.metadata_json,'$.user_disposition') AS user_disposition,"
            "CASE WHEN o.task_id IS NULL THEN (SELECT COUNT(*) FROM executions e WHERE e.task_id=t.id) "
            "ELSE o.attempts END AS attempts,o.assessment_json,r.delivery_status "
            "FROM agent_tasks t LEFT JOIN task_operations o ON o.task_id=t.id "
            "LEFT JOIN task_results r ON r.execution_id=t.current_execution_id "
            "WHERE COALESCE(json_extract(t.metadata_json,'$.owner_key'),t.requested_by)=? "
            "AND t.status NOT IN ('completed','cancelled') "
            "AND (t.status!='failed' OR COALESCE(json_extract(t.metadata_json,'$.user_disposition'),'')!='dismissed') "
            "AND t.id != ? ORDER BY t.created_at,t.rowid",
            (owner, exclude or ""),
        ).fetchall()
    return [dict(r) for r in rows]


def delivery_issues(path, owner):
    """Completed work can still have an unconfirmed connector send."""
    with db.connect(path) as conn:
        rows = conn.execute(
            "SELECT t.id,t.title,t.status,r.delivery_status FROM agent_tasks t "
            "JOIN task_results r ON r.execution_id=t.current_execution_id "
            "WHERE COALESCE(json_extract(t.metadata_json,'$.owner_key'),t.requested_by)=? "
            "AND r.delivery_status IN ('sending','uncertain') ORDER BY t.created_at,t.rowid",
            (owner,),
        ).fetchall()
    return [dict(row) for row in rows]


def explain(path, task_id, owner):
    with db.connect(path) as conn:
        row = conn.execute(
            "SELECT t.id,t.prompt,t.status,t.metadata_json,o.hold_reason,o.diagnosis,"
            "CASE WHEN o.task_id IS NULL THEN (SELECT COUNT(*) FROM executions e WHERE e.task_id=t.id) "
            "ELSE o.attempts END AS attempts,r.delivery_status "
            "FROM agent_tasks t LEFT JOIN task_operations o ON o.task_id=t.id "
            "LEFT JOIN task_results r ON r.execution_id=t.current_execution_id "
            "WHERE t.id=? AND COALESCE(json_extract(t.metadata_json,'$.owner_key'),t.requested_by)=?",
            (task_id, owner),
        ).fetchone()
    if not row:
        raise PermissionError("해당 사용자의 작업을 찾지 못했습니다.")
    reason = (row["diagnosis"] or ledger.decode_json(row["metadata_json"], {}).get(
        "legacy_upgrade_hold", {}
    ).get("reason")) or {
        "queued": "실행 대기 중입니다.",
        "running": "아직 실행 중입니다.",
        "awaiting_approval": "파일별 변경안에 대한 승인을 기다립니다.",
    }.get(row["status"], "기록만으로 원인을 확정할 수 없습니다.")
    disposition = ledger.decode_json(row["metadata_json"], {}).get("user_disposition", "open")
    delivery = row["delivery_status"] or "no_saved_result"
    if delivery in {"sending", "uncertain"}:
        delivery += " (전달 여부 확인 필요; 자동 재전송하지 않음)"
    elif delivery == "acknowledged":
        delivery += " (알림만 종료; 전달 성공으로 확인한 것은 아님)"
    return (f"작업: {row['id']}\n원래 요청: {row['prompt']}\n상태: {row['status']}"
            f"\n결과 전달: {delivery}"
            f"\n사용자 결정: {disposition}\n근거: {reason}\n시도 수: {row['attempts'] or 0}")


def list_text(path, owner):
    rows = incomplete(path, owner)
    listed_ids = {row["id"] for row in rows}
    issues = [row for row in delivery_issues(path, owner) if row["id"] not in listed_ids]
    if not rows and not issues:
        return "현재 확인할 미완료 작업이 없습니다."
    lines = [
        f"- {row['id']}: {row['title'][:60]} ({row['status']}"
        f"{', 결과 전달 확인 필요' if row['delivery_status'] in {'sending', 'uncertain'} else ''})"
        for row in rows
    ]
    lines.extend(f"- {row['id']}: {row['title'][:60]} ({row['status']}, 결과 전달 확인 필요)"
                 for row in issues)
    note = ("\nack-delivery 작업ID는 결과 전달 확인 알림만 종료합니다. "
            "재전송하거나 실행을 취소하지 않습니다.") if any(
                row["delivery_status"] in {"sending", "uncertain"} for row in [*rows, *issues]
            ) else ""
    return "현재 확인할 작업:\n" + "\n".join(lines) + note


def _unresolved_effects(conn, task_id, *, include_lost=True):
    """A dismissal or repeat cancellation cannot erase an uncertain external effect."""
    operation = conn.execute("SELECT parent_task_id FROM task_operations WHERE task_id=?", (task_id,)).fetchone()
    resolution_owner = operation["parent_task_id"] if operation and operation["parent_task_id"] else task_id
    ids = [task_id]
    if resolution_owner == task_id:
        ids.extend(row["task_id"] for row in conn.execute(
            "SELECT task_id FROM task_operations WHERE parent_task_id=?", (task_id,)
        ).fetchall())
    for current in ids:
        statuses = ("lost", "stale", "starting", "running", "cancelling") if include_lost else (
            "stale", "starting", "running", "cancelling"
        )
        unresolved_attempts = conn.execute(
            f"SELECT id,status FROM executions WHERE task_id=? AND status IN ({','.join('?' for _ in statuses)})",
            (current, *statuses),
        ).fetchall()
        for attempt in unresolved_attempts:
            if attempt["status"] != "lost" or not conn.execute(
                "SELECT 1 FROM execution_events v JOIN change_plans p "
                "ON p.id=json_extract(v.metadata_json,'$.plan_id') "
                "JOIN json_each(v.metadata_json,'$.resolved_execution_ids') ids "
                "WHERE v.task_id=? AND v.event_type='plan.resolved' "
                "AND p.task_id=? AND p.status IN ('applied','reconciled') AND ids.value=?",
                (resolution_owner, resolution_owner, attempt["id"]),
            ).fetchone():
                return True
        if conn.execute(
            "SELECT 1 FROM change_plans WHERE task_id=? AND status IN ('applying','uncertain')",
            (current,),
        ).fetchone():
            return True
        if conn.execute(
            "SELECT 1 FROM change_journal j JOIN change_plans p ON p.id=j.plan_id "
            "WHERE p.task_id=? AND p.status NOT IN ('applied','reconciled')",
            (current,),
        ).fetchone():
            return True
    return False


def _dismiss_conn(conn, row, owner):
    if row["status"] != "failed" or _unresolved_effects(conn, row["id"]):
        raise SafeOperationError("Only a safe failed task can be dismissed; reconcile uncertain effects first")
    metadata = ledger.decode_json(row["metadata_json"], {})
    if metadata.get("user_disposition") == "dismissed":
        return "failed"
    timestamp = now()
    metadata["user_disposition"] = "dismissed"
    metadata["user_disposition_at"] = timestamp
    conn.execute("UPDATE agent_tasks SET metadata_json=?,updated_at=? WHERE id=?",
                 (ledger.encode_json(metadata), timestamp, row["id"]))
    ledger.append_event_conn(conn, task_id=row["id"], event_type="operation.dismissed",
                             status="failed", message="Owner chose not to revisit failed task",
                             metadata={"owner": owner})
    return "failed"


def _require_selected_revision(row, expected_status, expected_updated_at):
    if ((expected_status is not None and row["status"] != expected_status)
            or (expected_updated_at is not None and row["updated_at"] != expected_updated_at)):
        raise SafeOperationError("Selected task changed; refresh the task list before controlling it")


def dismiss(path, task_id, owner, *, expected_status=None, expected_updated_at=None):
    with db.connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
        if not row or row["requested_by"] != owner:
            raise PermissionError("Task owner mismatch")
        _require_selected_revision(row, expected_status, expected_updated_at)
        return _dismiss_conn(conn, row, owner)


def acknowledge_delivery(path, task_id, owner):
    """Suppress an ambiguous-send reminder without asserting receipt or replaying."""
    with db.connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT t.current_execution_id,r.delivery_status FROM agent_tasks t "
            "LEFT JOIN task_results r ON r.execution_id=t.current_execution_id "
            "WHERE t.id=? AND t.requested_by=?", (task_id, owner),
        ).fetchone()
        if not row:
            raise PermissionError("Task owner mismatch")
        if row["delivery_status"] == "acknowledged":
            return "acknowledged"
        if row["delivery_status"] not in {"sending", "uncertain"}:
            raise SafeOperationError("Current result has no ambiguous delivery to acknowledge")
        execution_id = row["current_execution_id"]
        conn.execute("UPDATE task_results SET delivery_status='acknowledged',updated_at=? "
                     "WHERE execution_id=? AND delivery_status IN ('sending','uncertain')",
                     (now(), execution_id))
        ledger.append_event_conn(
            conn, task_id=task_id, execution_id=execution_id,
            event_type="workflow.delivery_acknowledged", status="acknowledged",
            message="Owner suppressed ambiguous delivery reminder without confirming receipt",
            metadata={"previous_delivery_status": row["delivery_status"]},
        )
        return "acknowledged"


def reminder(path, owner, exclude=None, completed_parent=None):
    rows = [r for r in incomplete(path, owner, exclude) if r["id"] != completed_parent]
    if not rows:
        return ""
    return (
        "\n\n미완료 작업이 "
        + str(len(rows))
        + "개 남아 있습니다.\n"
        + "\n".join(f"- {r['id']}: {r['title'][:60]} ({r['status']})" for r in rows[:5])
        + "\nwhy 작업ID로 요청 내용과 중단 근거를 확인할 수 있습니다."
    )


def finish(path, record, outcome):
    work_queue.finish(path, record, outcome)


def resume(path, task_id, owner, generation):
    recover(path)
    with db.connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT t.status,t.requested_by,t.metadata_json,o.* FROM agent_tasks t "
            "JOIN task_operations o ON o.task_id=t.id WHERE t.id=?",
            (task_id,),
        ).fetchone()
        if not row or row["requested_by"] != owner:
            raise PermissionError("Task owner mismatch")
        if conn.execute(
            "SELECT 1 FROM task_results r JOIN agent_tasks t ON t.current_execution_id=r.execution_id "
            "WHERE t.id=? AND r.delivery_status IN ('sending','uncertain')", (task_id,),
        ).fetchone():
            raise SafeOperationError("Acknowledge ambiguous result delivery before resuming this task")
        spec = OperationSpec.loads(row["spec_json"])
        if spec.kind == "apply" or row["status"] not in {"blocked", "failed"} or row["attempts"] >= row["max_attempts"]:
            raise SafeOperationError("This task requires plan reconciliation or has reached its attempt limit")
        if _unresolved_effects(conn, task_id, include_lost=False):
            raise SafeOperationError("File side effects or active execution require reconciliation before another attempt")
        if conn.execute(
            "SELECT 1 FROM change_plans WHERE task_id=? AND status IN ('applying','uncertain','applied','reconciled')",
            (task_id,),
        ).fetchone():
            raise SafeOperationError(
                "File side effects require plan reconciliation and a new request, never task replay"
            )
        check_workspace(spec.workspace, owner)
        worker = conn.execute("SELECT * FROM operation_workers WHERE id=?", (generation,)).fetchone()
        cutoff = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
        if not worker or worker["closed"] or worker["heartbeat_at"] < cutoff:
            raise SafeOperationError("Worker not ready")
        conn.execute(
            "UPDATE task_operations SET eligible=1,worker_generation=?,hold_reason=?,diagnosis=? WHERE task_id=?",
            (generation, "", "", task_id),
        )
        metadata = ledger.decode_json(row["metadata_json"], {})
        metadata.pop("user_disposition", None)
        metadata.pop("user_disposition_at", None)
        conn.execute(
            "UPDATE agent_tasks SET status='queued',completed_at=NULL,updated_at=?,metadata_json=? WHERE id=?",
            (now(), ledger.encode_json(metadata), task_id),
        )
        ledger.append_event_conn(
            conn,
            task_id=task_id,
            event_type="operation.resume_requested",
            status="queued",
            message="Owner explicitly requested a bounded new attempt",
        )
    return task_id


def cancel(path, task_id, owner, *, expected_execution_id=None, expected_status=None, expected_updated_at=None):
    with db.connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
        if not row or row["requested_by"] != owner:
            raise PermissionError("Task owner mismatch")
        _require_selected_revision(row, expected_status, expected_updated_at)
        if expected_execution_id is not None and row["current_execution_id"] != expected_execution_id:
            raise SafeOperationError("Execution is no longer current")
        if row["status"] == "failed":
            return _dismiss_conn(conn, row, owner)
        if row["status"] in {"completed", "cancelled"}:
            if _unresolved_effects(conn, task_id):
                raise SafeOperationError("Recorded terminal state has unresolved effects; reconcile first")
            return row["status"]
        timestamp = now()
        active = conn.execute(
            "SELECT c.* FROM task_claims c JOIN executions e ON e.id=c.execution_id "
            "WHERE c.task_id=? AND c.execution_id=? AND c.released=0 AND c.expires_at>? "
            "AND e.status IN ('running','cancelling')",
            (task_id, row["current_execution_id"], timestamp),
        ).fetchone()
        if row["status"] == "blocked" and _unresolved_effects(conn, task_id):
            return "blocked"
        plans = conn.execute("SELECT id FROM change_plans WHERE task_id=? AND status IN ('pending','approved')",
                             (task_id,)).fetchall()
        conn.execute("UPDATE approvals SET status='rejected',decided_by=?,decided_at=? "
                     "WHERE task_id=? AND status='pending'", (owner, timestamp, task_id))
        for plan in plans:
            conn.execute("UPDATE change_plans SET status='revoked',decided_by=? WHERE id=?", (owner, plan["id"]))
            children = conn.execute(
                "SELECT t.id,t.status FROM agent_tasks t JOIN task_operations o ON o.task_id=t.id "
                "WHERE o.parent_task_id=? AND json_extract(o.spec_json,'$.plan_id')=?",
                (task_id, plan["id"]),
            ).fetchall()
            for child in children:
                if child["status"] == "queued":
                    conn.execute("UPDATE agent_tasks SET status='cancelled',completed_at=?,updated_at=? WHERE id=?",
                                 (timestamp, timestamp, child["id"]))
                    conn.execute("UPDATE task_operations SET eligible=0,hold_reason='parent_cancelled' WHERE task_id=?",
                                 (child["id"],))
                elif child["status"] in {"running", "cancelling"}:
                    conn.execute("UPDATE agent_tasks SET status='cancelling',updated_at=? WHERE id=?",
                                 (timestamp, child["id"]))
                    conn.execute("UPDATE executions SET status='cancelling',updated_at=? "
                                 "WHERE task_id=? AND status='running'", (timestamp, child["id"]))
        if active:
            conn.execute(
                "UPDATE executions SET status='cancelling',updated_at=? WHERE id=?",
                (timestamp, active["execution_id"]),
            )
            conn.execute("UPDATE agent_tasks SET status='cancelling',updated_at=? WHERE id=?", (timestamp, task_id))
        else:
            uncertain = _unresolved_effects(conn, task_id) or conn.execute(
                "SELECT 1 FROM executions WHERE task_id=? AND status IN ('starting','running','cancelling','stale')",
                (task_id,),
            ).fetchone()
            status = "blocked" if uncertain else "cancelled"
            diagnosis = "Cancellation requested without a live claim; external effects require reconciliation" if uncertain else ""
            conn.execute(
                "UPDATE agent_tasks SET status=?,updated_at=?,completed_at=? WHERE id=?",
                (status, timestamp, None if uncertain else timestamp, task_id),
            )
            conn.execute("UPDATE task_claims SET released=1 WHERE task_id=?", (task_id,))
            conn.execute(
                "UPDATE executions SET status=?,error=?,ended_at=?,updated_at=? WHERE task_id=? "
                "AND status NOT IN ('succeeded','failed','cancelled','timed_out','lost')",
                ("lost" if uncertain else "cancelled", diagnosis, timestamp, timestamp, task_id),
            )
            conn.execute(
                "UPDATE task_operations SET hold_reason=?,diagnosis=? WHERE task_id=?",
                ("cancellation_unconfirmed" if uncertain else "cancelled", diagnosis, task_id),
            )
            conn.execute("UPDATE task_operations SET eligible=0 WHERE task_id=?", (task_id,))
        ledger.append_event_conn(
            conn,
            task_id=task_id,
            event_type="operation.cancel_requested",
            message="Owner requested cancellation; active process acknowledgement is separate",
        )
        return "cancelling" if active else status


def recovery_inventory(path, owner=None, exclude=None):
    """Background notice candidates; explicit task lists keep ordinary active work.

    Use the existing worker heartbeat and claim leases, never an arbitrary task
    age. A lease is evidence of active ownership, not proof of external effects.
    """
    timestamp = now()
    cutoff = (datetime.now(UTC) - timedelta(seconds=30)).isoformat()
    with db.connect(path) as conn:
        rows = conn.execute(
            "SELECT t.*,COALESCE(t.source_request_id,p.source_request_id) AS delivery_request_id,"
            "r.delivery_status,o.hold_reason,"
            "COALESCE(o.diagnosis,json_extract(t.metadata_json,'$.legacy_upgrade_hold.reason')) AS diagnosis,"
            "CASE WHEN o.task_id IS NULL THEN (SELECT COUNT(*) FROM executions history WHERE history.task_id=t.id) "
            "ELSE o.attempts END AS attempts,o.assessment_json,"
            "CASE WHEN o.eligible=1 AND o.attempts<o.max_attempts AND COALESCE(o.hold_reason,'')='' "
            "AND w.closed=0 AND w.heartbeat_at>? AND (c.task_id IS NULL OR c.released=1) "
            "THEN 1 ELSE 0 END AS healthy_queue,"
            "CASE WHEN c.released=0 AND c.expires_at>? AND e.status IN ('running','cancelling') "
            "AND (o.task_id IS NULL OR (o.eligible=1 AND COALESCE(o.hold_reason,'')='' "
            "AND c.worker_id=o.worker_generation AND w.closed=0 AND w.heartbeat_at>?)) "
            "THEN 1 ELSE 0 END AS live_claim "
            "FROM agent_tasks t LEFT JOIN task_operations o ON o.task_id=t.id "
            "LEFT JOIN agent_tasks p ON p.id=o.parent_task_id "
            "LEFT JOIN operation_workers w ON w.id=o.worker_generation "
            "LEFT JOIN task_claims c ON c.task_id=t.id AND c.execution_id=t.current_execution_id "
            "AND c.owner_key=COALESCE(json_extract(t.metadata_json,'$.owner_key'),t.requested_by) "
            "LEFT JOIN executions e ON e.id=c.execution_id AND e.task_id=t.id "
            "LEFT JOIN task_results r ON r.execution_id=t.current_execution_id "
            "WHERE (t.status IN ('blocked','failed','awaiting_approval','queued','running','cancelling') "
            "OR r.delivery_status IN ('sending','uncertain')) "
            "AND (? IS NULL OR COALESCE(json_extract(t.metadata_json,'$.owner_key'),t.requested_by)=?) "
            "AND t.id!=? ORDER BY t.created_at,t.rowid",
            (cutoff, timestamp, cutoff, owner, owner, exclude or ""),
        ).fetchall()
    candidates = []
    for row in rows:
        item = dict(row)
        healthy_queue = item.pop("healthy_queue")
        live_claim = item.pop("live_claim")
        delivery_issue = item["delivery_status"] in {"sending", "uncertain"}
        if not delivery_issue:
            if item["status"] == "queued" and healthy_queue:
                continue
            if item["status"] in {"running", "cancelling"} and live_claim:
                continue
            if (item["status"] == "failed"
                    and ledger.decode_json(item["metadata_json"], {}).get("user_disposition") == "dismissed"):
                continue
        candidates.append(ledger._parse_record(item))
    return candidates
