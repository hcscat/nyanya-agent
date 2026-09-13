"""Transactional execution authority for serializable operations."""

from nyanya_agent.task_outcomes import SafeOperationError
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from nyanya_agent import execution_store as ledger, database as db
from nyanya_agent.operation_spec import OperationSpec
from nyanya_agent.task_outcomes import TaskOutcome
from nyanya_agent import work_queue


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


def submit(path, spec, owner, generation, *, source_request_id=None, project_id=None, parent_task_id=None):
    spec.validate()
    root = check_workspace(spec.workspace, owner)
    ledger.apply_migrations(path)
    timestamp, task_id = now(), ledger.new_id("task")
    with db.connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
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
        ledger.append_event_conn(
            conn,
            task_id=task_id,
            event_type="operation.accepted",
            status="queued",
            message="Serializable operation accepted",
        )
    return ledger.get_task(task_id, db_path=path)


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
    recover(path)
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
            "CASE WHEN o.task_id IS NULL THEN (SELECT COUNT(*) FROM executions e WHERE e.task_id=t.id) "
            "ELSE o.attempts END AS attempts,o.assessment_json "
            "FROM agent_tasks t LEFT JOIN task_operations o ON o.task_id=t.id "
            "WHERE COALESCE(json_extract(t.metadata_json,'$.owner_key'),t.requested_by)=? "
            "AND t.status NOT IN ('completed','cancelled') AND t.id != ? ORDER BY t.created_at,t.rowid",
            (owner, exclude or ""),
        ).fetchall()
    return [dict(r) for r in rows]


def explain(path, task_id, owner):
    row = next((r for r in incomplete(path, owner) if r["id"] == task_id), None)
    if not row:
        raise PermissionError("해당 사용자의 미완료 작업을 찾지 못했습니다.")
    reason = row["diagnosis"] or {
        "queued": "실행 대기 중입니다.",
        "running": "아직 실행 중입니다.",
        "awaiting_approval": "파일별 변경안에 대한 승인을 기다립니다.",
    }.get(row["status"], "기록만으로 원인을 확정할 수 없습니다.")
    return f"작업: {row['id']}\n원래 요청: {row['prompt']}\n상태: {row['status']}\n근거: {reason}\n시도 수: {row['attempts'] or 0}"


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
    if outcome.status == "succeeded":
        parent = None
        if record.get("spec") and record["spec"].kind == "apply":
            with db.connect(path) as conn:
                row = conn.execute(
                    "SELECT task_id FROM change_plans WHERE id=? AND status='applied'", (record["spec"].plan_id,)
                ).fetchone()
                parent = row["task_id"] if row else None
        outcome = TaskOutcome(outcome.status, outcome.text + reminder(path, record["owner"], record["task_id"], parent))
    work_queue.finish(path, record, outcome)


def resume(path, task_id, owner, generation):
    recover(path)
    with db.connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT t.status,t.requested_by,o.* FROM agent_tasks t JOIN task_operations o ON o.task_id=t.id WHERE t.id=?",
            (task_id,),
        ).fetchone()
        if not row or row["requested_by"] != owner:
            raise PermissionError("Task owner mismatch")
        spec = OperationSpec.loads(row["spec_json"])
        if spec.kind == "apply" or row["status"] not in {"blocked", "failed"} or row["attempts"] >= row["max_attempts"]:
            raise SafeOperationError("This task requires plan reconciliation or has reached its attempt limit")
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
        conn.execute(
            "UPDATE agent_tasks SET status='queued',completed_at=NULL,updated_at=? WHERE id=?", (now(), task_id)
        )
        ledger.append_event_conn(
            conn,
            task_id=task_id,
            event_type="operation.resume_requested",
            status="queued",
            message="Owner explicitly requested a bounded new attempt",
        )
    return task_id


def cancel(path, task_id, owner, *, expected_execution_id=None):
    with db.connect(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
        if not row or row["requested_by"] != owner:
            raise PermissionError("Task owner mismatch")
        if expected_execution_id is not None and row["current_execution_id"] != expected_execution_id:
            raise SafeOperationError("Execution is no longer current")
        if row["status"] in {"completed", "cancelled"}:
            return
        timestamp = now()
        active = conn.execute(
            "SELECT c.* FROM task_claims c JOIN executions e ON e.id=c.execution_id "
            "WHERE c.task_id=? AND c.execution_id=? AND c.released=0 AND c.expires_at>? "
            "AND e.status IN ('running','cancelling')",
            (task_id, row["current_execution_id"], timestamp),
        ).fetchone()
        conn.execute(
            "UPDATE change_plans SET status='revoked' WHERE task_id=? AND status IN ('pending','approved')",
            (task_id,),
        )
        if active:
            conn.execute(
                "UPDATE executions SET status='cancelling',updated_at=? WHERE id=?",
                (timestamp, active["execution_id"]),
            )
            conn.execute("UPDATE agent_tasks SET status='cancelling',updated_at=? WHERE id=?", (timestamp, task_id))
        else:
            uncertain = conn.execute(
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


def recovery_inventory(path):
    """Notice candidates only: do not report a healthy pending operation as interrupted."""
    recover(path)
    with db.connect(path) as conn:
        rows = conn.execute(
            "SELECT t.*,COALESCE(t.source_request_id,p.source_request_id) AS delivery_request_id "
            "FROM agent_tasks t LEFT JOIN task_operations o ON o.task_id=t.id "
            "LEFT JOIN agent_tasks p ON p.id=o.parent_task_id "
            "WHERE t.status IN ('blocked','failed','awaiting_approval') "
            "OR (o.task_id IS NULL AND t.status IN ('queued','running','cancelling')) "
            "ORDER BY t.created_at,t.rowid"
        ).fetchall()
    return [ledger._parse_record(dict(row)) for row in rows]
