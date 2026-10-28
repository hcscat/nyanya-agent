"""Ingress facade: persist operations, supervise a dedicated worker, deliver saved results."""

import os
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
import threading
import time
from nyanya_agent import operation_store as store, execution_store as ledger, work_queue, reviewed_changes, dashboard_store, workflow_notifications
from nyanya_agent import database as db
from nyanya_agent.control_intents import classify
from nyanya_agent.operation_spec import OperationSpec
from nyanya_agent.task_outcomes import SafeOperationError, TaskOutcome


def stop_worker(process, *, timeout=8):
    """Bounded termination and reaping of this controller's Popen child only."""
    try:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Dedicated worker cleanup could not confirm termination") from exc
    finally:
        if process.stdin:
            process.stdin.close()


class OperationService:
    def __init__(self, path=None, *, generation=None):
        self.path = str(db.resolve_db_path(path))
        ledger.apply_migrations(self.path)
        while ledger.reconcile_legacy_requests(limit=500, db_path=self.path)["scanned"]:
            pass
        store.recover(self.path)
        self.generation = generation
        self.process = None
        self.lock = threading.Lock()
        self.closed = threading.Event()
        self.watchers = []

    def ensure_worker(self):
        with self.lock:
            if self.closed.is_set():
                raise RuntimeError("Operation service is closed")
            if self.generation and (self.process is None or self.process.poll() is None):
                return self.generation
            if self.process is not None:
                stop_worker(self.process)
            env = dict(os.environ)
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get("PYTHONPATH", "")
            slots = max(1, min(int(os.getenv("NYANYA_WORKER_CONCURRENCY", "2")), 4))
            generation = ledger.new_id("worker")
            self.generation = None  # A failed launch must never look like an external ready worker.
            self.process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "nyanya_agent.operation_worker",
                    "--db",
                    self.path,
                    "--generation",
                    generation,
                    "--slots",
                    str(slots),
                    "--parent-pid",
                    str(os.getpid()),
                ],
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline and self.process.poll() is None:
                    with db.connect(self.path) as conn:
                        if conn.execute(
                            "SELECT 1 FROM operation_workers WHERE id=? AND closed=0", (generation,)
                        ).fetchone():
                            self.generation = generation
                            return self.generation
                    time.sleep(0.05)
            except BaseException:
                stop_worker(self.process, timeout=5)
                raise
            stop_worker(self.process, timeout=5)
            store.heartbeat(self.path, generation, closed=True)
            store.recover(self.path)
            raise RuntimeError("Dedicated worker failed to become ready")

    def submit(
        self,
        prompt,
        workspace,
        owner,
        *,
        profile="auto",
        source_request_id=None,
        conversation_key=None,
        responder=None,
        kind="request",
        plan_id="",
    ):
        if kind == "request" and classify(prompt).kind != "work_request":
            raise ValueError("Operation control text cannot be submitted as model work")
        store.check_workspace(workspace, owner)
        launch_error = None
        try:
            generation = self.ensure_worker()
        except (RuntimeError, OSError, ValueError) as exc:
            launch_error = type(exc).__name__
            generation = ledger.new_id("unavailable_worker")
            store.register_worker(self.path, generation)
        task = store.submit(
            self.path,
            OperationSpec(
                kind=kind, prompt=prompt, workspace=str(Path(workspace).resolve()), profile=profile, plan_id=plan_id
            ),
            owner,
            generation,
            source_request_id=source_request_id,
            conversation_key=conversation_key,
        )
        if launch_error:
            store.heartbeat(self.path, generation, closed=True)
            store.recover(self.path)
            store.record_start_failure(self.path, task["id"], owner, launch_error)
            if responder:
                thread = threading.Thread(target=self.deliver, args=(task["id"], owner, responder, 0), daemon=True)
                self.watchers.append(thread)
                thread.start()
            return ledger.get_task(task["id"], db_path=self.path)
        self.watchers = [thread for thread in self.watchers if thread.is_alive()]
        if responder:
            attempt = store.watch_attempt(self.path, task["id"], owner)
            thread = threading.Thread(target=self.deliver, args=(task["id"], owner, responder, attempt), daemon=True)
            self.watchers.append(thread)
            thread.start()
        return task

    def deliver(self, task_id, owner, responder, attempt=None):
        if attempt is None:
            attempt = store.watch_attempt(self.path, task_id, owner)
        while not self.closed.wait(0.15):
            state = store.delivery_state(self.path, task_id, owner)
            if state is None or state["attempts"] > attempt:
                return
            if (state["attempts"] == attempt and state["execution_id"]
                    and state["status"] not in {"queued", "running"}):
                execution_id = state["execution_id"]
                if state["delivery_status"] != "pending":
                    return
                notice = workflow_notifications.prepare(
                    self.path, owner, exclude=task_id,
                    source=state.get("request_source") or "", channel_id=state.get("request_channel_id") or "",
                ) if state["outcome"] == "succeeded" else None
                if not store.claim_delivery(self.path, task_id, owner, execution_id, attempt):
                    return
                try:
                    responder(state["response"] + (notice.text if notice else ""))
                except Exception as exc:
                    store.settle_delivery(self.path, execution_id, delivered=False, error=type(exc).__name__)
                else:
                    store.settle_delivery(self.path, execution_id, delivered=True)
                    if notice:
                        workflow_notifications.delivered(self.path, notice)
                return
            if state["status"] in {"blocked", "cancelled", "failed"}:
                return

    def wait(self, task_id, owner, timeout=1200):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            saved = work_queue.result(self.path, task_id, owner)
            if saved:
                current = ledger.get_task(task_id, db_path=self.path)
                if (
                    current["status"] not in {"queued", "running"}
                    and current["current_execution_id"] == saved["execution_id"]
                ):
                    return TaskOutcome(saved["outcome"], saved["response"])
            current = ledger.get_task(task_id, db_path=self.path)
            if current and current["status"] in {"blocked", "failed", "cancelled"} and (
                not saved or current["current_execution_id"] != saved["execution_id"]
            ):
                return TaskOutcome(
                    current["status"],
                    "취소되었습니다." if current["status"] == "cancelled" else store.explain(self.path, task_id, owner),
                )
            if self.process and self.process.poll() is not None:
                store.heartbeat(self.path, self.generation, closed=True)
                store.recover(self.path)
                return TaskOutcome("blocked", "Worker가 종료되었습니다. why 작업ID로 확인하세요.")
            time.sleep(0.1)
        store.cancel(self.path, task_id, owner)
        return TaskOutcome("timed_out", "대기시간을 초과했습니다. 실제 작업 종료는 별도 확인이 필요합니다.")

    def control(self, text, owner, *, conversation_key=None, responder=None, wait=True):
        intent = classify(text)
        if intent.kind != "work_request":
            return self.handle_intent(text, owner, conversation_key=conversation_key or owner, responder=responder, wait=wait)
        parts = text.split()
        command = parts[0].lower() if parts else ""
        if command in {"recovery", "복구", "tasks", "작업목록"}:
            return store.reminder(self.path, owner).strip() or "미완료 작업이 없습니다."
        if command == "why" and len(parts) == 2:
            return store.explain(self.path, parts[1], owner)
        if command == "plan" and len(parts) == 2:
            return reviewed_changes.preview(self.path, parts[1], owner)
        if command == "plan-file" and len(parts) >= 3:
            return reviewed_changes.plan_file(self.path, parts[1], owner, " ".join(parts[2:]))
        if command == "reconcile" and len(parts) == 2:
            evidence = reviewed_changes.reconcile(self.path, parts[1], owner)
            return (
                str(evidence)
                + f"\n관측만 수행했습니다. 이 상태를 확인 처리하려면: resolve {parts[1]} {reviewed_changes.evidence_hash(evidence)}"
            )
        if command == "resolve" and len(parts) == 3:
            return reviewed_changes.resolve(self.path, parts[1], owner, parts[2])
        if command == "revoke" and len(parts) == 2:
            reviewed_changes.decide(self.path, parts[1], owner, revoke=True)
            return "변경안 승인을 거절/철회했습니다."
        if command == "approve" and len(parts) == 3:
            task, created = store.approve_and_submit_apply(
                self.path, parts[1], owner, parts[2], self.ensure_worker(),
            )
            if not created:
                return f"이미 접수된 변경안입니다: {task['id']} ({task['status']}). 새 작업은 만들지 않았습니다."
            if responder:
                attempt = store.watch_attempt(self.path, task["id"], owner)
                thread = threading.Thread(target=self.deliver, args=(task["id"], owner, responder, attempt), daemon=True)
                self.watchers.append(thread)
                thread.start()
            if responder is None and wait:
                return self.wait(task["id"], owner).text
            return f"승인된 변경안 적용을 접수했습니다: {task['id']}"
        if command == "resume" and len(parts) == 2:
            store.resume(self.path, parts[1], owner, self.ensure_worker())
            if responder:
                attempt = store.watch_attempt(self.path, parts[1], owner)
                thread = threading.Thread(target=self.deliver, args=(parts[1], owner, responder, attempt), daemon=True)
                self.watchers.append(thread)
                thread.start()
            if responder is None and wait:
                return self.wait(parts[1], owner).text
            return "사용자 요청으로 재시도를 등록했습니다. 모델/경로/권한을 다시 검사합니다."
        if command == "cancel" and len(parts) == 2:
            store.cancel(self.path, parts[1], owner)
            return "취소를 요청했습니다. 실행 중 작업은 종료 확인을 기다립니다."
        return None

    @staticmethod
    def _scope_hash(value):
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _control_request(self, owner, request_id):
        if request_id:
            return request_id
        return dashboard_store.create_agent_request(
            source="control", user_id=owner, trigger="local", command="task_list",
            mode="control", prompt="", status="completed", db_path=self.path,
        )

    def _selection(self, owner, conversation_key):
        actor_hash = self._scope_hash(owner)
        conversation_hash = self._scope_hash(conversation_key)
        with db.connect(self.path) as conn:
            row = conn.execute(
                "SELECT e.metadata_json FROM request_events e JOIN agent_requests r ON r.id=e.request_id "
                "WHERE e.event_type='control.selection' AND r.mode='control' "
                "AND json_extract(e.metadata_json,'$.actor')=? "
                "AND json_extract(e.metadata_json,'$.conversation')=? "
                "ORDER BY e.rowid DESC LIMIT 1", (actor_hash, conversation_hash),
            ).fetchone()
        if not row:
            return None
        data = json.loads(row["metadata_json"])
        return data if datetime.fromisoformat(data["expires_at"]) > datetime.now(timezone.utc) else None

    def _list_and_select(self, owner, conversation_key, request_id):
        request_id = self._control_request(owner, request_id)
        with db.connect(self.path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT id,status,updated_at FROM agent_tasks WHERE "
                "COALESCE(json_extract(metadata_json,'$.owner_key'),requested_by)=? "
                "AND status NOT IN ('completed','cancelled') "
                "AND NOT (status='failed' AND COALESCE(json_extract(metadata_json,'$.user_disposition'),'')='dismissed') "
                "ORDER BY created_at,rowid", (owner,),
            ).fetchall()
            selected = [dict(row) for row in rows]
            display = store.list_text(self.path, owner)
            metadata = {
                "actor": self._scope_hash(owner),
                "conversation": self._scope_hash(conversation_key),
                "targets": selected,
                "revision": self._scope_hash(json.dumps(selected, sort_keys=True)),
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
            }
            dashboard_store.append_request_event_conn(conn, request_id, "control.selection", "Owner task list selected", metadata)
        return display

    def _cancel_selection(self, owner, conversation_key):
        selected = self._selection(owner, conversation_key)
        if selected is None:
            return "취소할 대상이 확정되지 않았습니다. 먼저 작업목록을 조회한 뒤 다시 취소를 요청하세요."
        targets = selected["targets"]
        if not targets:
            return "취소할 미완료 작업이 없습니다."
        with db.connect(self.path) as conn:
            current = [dict(row) for row in conn.execute(
                "SELECT id,status,updated_at FROM agent_tasks WHERE "
                "COALESCE(json_extract(metadata_json,'$.owner_key'),requested_by)=? "
                "AND status NOT IN ('completed','cancelled') "
                "AND NOT (status='failed' AND COALESCE(json_extract(metadata_json,'$.user_disposition'),'')='dismissed') "
                "ORDER BY created_at,rowid", (owner,),
            ).fetchall()]
        if current != targets:
            return "목록 이후 작업 상태가 바뀌었습니다. 작업목록을 다시 조회하고 취소 범위를 확인하세요."
        lines = []
        processed = 0
        for item in targets:
            try:
                if item["status"] == "failed":
                    status = store.dismiss(
                        self.path, item["id"], owner,
                        expected_status=item["status"], expected_updated_at=item["updated_at"],
                    )
                    lines.append(self._cancel_response(item["id"], status))
                else:
                    status = store.cancel(
                        self.path, item["id"], owner,
                        expected_status=item["status"], expected_updated_at=item["updated_at"],
                    )
                    lines.append(self._cancel_response(item["id"], status))
                processed += 1
            except SafeOperationError:
                lines.append(self._held_cancel_response(item["id"], owner) or
                             f"{item['id']}: 처리 보류. 상태가 달라졌거나 확인이 필요한 기록이 있습니다. 목록을 다시 확인해 주세요.")
            except (PermissionError, ValueError):
                lines.append(f"{item['id']}: 소유자나 현재 상태를 확인해야 해서 처리를 보류했습니다.")
        return (
            f"선택한 {len(targets)}개 중 {processed}개 요청을 처리했습니다.\n" + "\n".join(lines)
        )

    @staticmethod
    def _cancel_response(task_id, status):
        message = {
            "failed": "실패한 작업을 다시 진행하지 않기로 기록했습니다. 실패 이력은 보존됩니다.",
            "completed": "이미 완료된 작업이라 취소할 실행이 없습니다.",
            "cancelled": "취소된 상태입니다. 다시 실행하지 않습니다.",
            "cancelling": "실행에 중단을 요청했습니다. 실제 종료 확인을 기다리고 있습니다.",
            "blocked": "실행 결과를 확정할 수 없어 보류했습니다. 기록을 확인한 뒤 후속 조치를 정해야 합니다.",
        }.get(status, "현재 상태를 확인해야 합니다.")
        return f"{task_id}: {message}"

    def _cancel_task(self, task_id, owner):
        try:
            status = store.cancel(self.path, task_id, owner)
        except SafeOperationError:
            response = self._held_cancel_response(task_id, owner)
            if response is None:
                raise
            return response
        return self._cancel_response(task_id, status)

    def _held_cancel_response(self, task_id, owner):
        with db.connect(self.path) as conn:
            row = conn.execute("SELECT status FROM agent_tasks WHERE id=? AND requested_by=?", (task_id, owner)).fetchone()
            if not row or not store._unresolved_effects(conn, task_id):
                return None
        state = {"completed": "현재 작업은 완료 상태입니다", "cancelled": "현재 작업은 취소 상태입니다", "failed": "현재 작업은 실패 상태입니다"}.get(row["status"], "현재 작업은 보류 상태입니다")
        return (f"{task_id}: {state}. 다만 이전 실행의 결과가 확인되지 않아 취소 처리를 확정하지 않았습니다. "
                f"기록을 보존했습니다. why {task_id}로 원래 요청과 확인이 필요한 근거를 볼 수 있습니다.")

    def runtime_status(self):
        """Report configured local limits without probing a model or external provider."""
        spec = OperationSpec(kind="request", prompt="status", workspace=".")
        slots = max(1, min(int(os.getenv("NYANYA_WORKER_CONCURRENCY", "2")), 4))
        return (
            f"점검 시각 {datetime.now(timezone.utc).isoformat()} (UTC). 현재 설정 기준: "
            f"요청별 실행 제한 {spec.timeout_seconds}초, "
            f"Flash 판단 단계 상한 {min(120, spec.timeout_seconds)}초, "
            f"동시 작업 상한 {slots}개. "
            "이는 로컬 설정값이며 모델 인증이나 실제 실행 성공을 확인한 결과는 아닙니다."
        )

    def handle_intent(self, text, owner, *, conversation_key=None, request_id=None, responder=None, wait=True):
        intent = classify(text)
        scope = conversation_key or owner
        if intent.kind == "work_request":
            return self.control(text, owner, responder=responder, wait=wait)
        if intent.kind == "clarify":
            return "어떤 작업에 대한 요청인지 의도를 확정하기 어렵습니다. 목록만 볼지, 어떤 작업을 중단할지 알려주세요."
        if intent.kind == "task_list":
            return self._list_and_select(owner, scope, request_id)
        if intent.kind == "runtime_status":
            return self.runtime_status()
        if intent.kind == "task_cancel_selection":
            return self._cancel_selection(owner, scope)
        if intent.kind == "task_explain":
            return store.explain(self.path, intent.task_id, owner)
        if intent.kind == "task_cancel":
            return self._cancel_task(intent.task_id, owner)
        if intent.kind == "task_dismiss":
            try:
                status = store.dismiss(self.path, intent.task_id, owner)
            except SafeOperationError:
                held = self._held_cancel_response(intent.task_id, owner)
                if held:
                    return held.replace("취소 처리를", "종결 처리를")
                with db.connect(self.path) as conn:
                    row = conn.execute("SELECT status FROM agent_tasks WHERE id=? AND requested_by=?", (intent.task_id, owner)).fetchone()
                if row and row["status"] in {"completed", "cancelled"}:
                    return self._cancel_response(intent.task_id, row["status"])
                return f"{intent.task_id}: 실패한 작업에만 재진행 안 함 결정을 기록할 수 있습니다. 현재 작업의 중단을 원하면 그렇게 알려주세요."
            return self._cancel_response(intent.task_id, status)
        if intent.kind == "delivery_ack":
            store.acknowledge_delivery(self.path, intent.task_id, owner)
            return (f"{intent.task_id}: 결과 전달 확인 알림을 종료했습니다. "
                    "전달 성공을 확인하거나 결과를 재전송하거나 실행을 취소한 것은 아닙니다.")
        if intent.kind == "task_resume":
            store.resume(self.path, intent.task_id, owner, self.ensure_worker())
            if responder:
                attempt = store.watch_attempt(self.path, intent.task_id, owner)
                thread = threading.Thread(target=self.deliver, args=(intent.task_id, owner, responder, attempt), daemon=True)
                self.watchers.append(thread)
                thread.start()
            if responder is None and wait:
                return self.wait(intent.task_id, owner).text
            return "사용자 요청으로 재시도를 등록했습니다. 모델/경로/권한을 다시 검사합니다."
        return None

    def close(self):
        self.closed.set()
        with self.lock:
            if self.process:
                stop_worker(self.process)
                store.heartbeat(self.path, self.generation, closed=True)
                store.recover(self.path)
        for thread in self.watchers:
            thread.join(timeout=0.5)
