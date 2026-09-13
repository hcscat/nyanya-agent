"""Ingress facade: persist operations, supervise a dedicated worker, deliver saved results."""

import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from nyanya_agent import operation_store as store, execution_store as ledger, work_queue, reviewed_changes
from nyanya_agent import database as db
from nyanya_agent.operation_spec import OperationSpec
from nyanya_agent.task_outcomes import TaskOutcome


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
        responder=None,
        kind="request",
        plan_id="",
    ):
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
        )
        if launch_error:
            store.heartbeat(self.path, generation, closed=True)
            store.recover(self.path)
            with db.connect(self.path) as conn:
                conn.execute(
                    "UPDATE task_operations SET hold_reason='worker_start_failed',diagnosis=? WHERE task_id=?",
                    (
                        f"Worker 시작 실패 ({launch_error}). 실행 환경을 확인한 뒤 resume 작업ID로 재개하세요.",
                        task["id"],
                    ),
                )
            return ledger.get_task(task["id"], db_path=self.path)
        self.watchers = [thread for thread in self.watchers if thread.is_alive()]
        if responder:
            thread = threading.Thread(target=self.deliver, args=(task["id"], owner, responder), daemon=True)
            self.watchers.append(thread)
            thread.start()
        return task

    def deliver(self, task_id, owner, responder):
        while not self.closed.wait(0.15):
            saved = work_queue.result(self.path, task_id, owner)
            current = ledger.get_task(task_id, db_path=self.path)
            if (
                saved
                and current["status"] not in {"queued", "running"}
                and current["current_execution_id"] == saved["execution_id"]
            ):
                if saved["delivery_status"] == "delivered":
                    return
                try:
                    responder(saved["response"])
                except Exception as exc:
                    work_queue.record_delivery(
                        self.path, saved["execution_id"], delivered=False, error=type(exc).__name__
                    )
                else:
                    work_queue.record_delivery(self.path, saved["execution_id"], delivered=True)
                return
            task = ledger.get_task(task_id, db_path=self.path)
            if task["status"] in {"blocked", "cancelled", "failed"}:
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
            if current and current["status"] in {"blocked", "failed", "cancelled"} and not saved:
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

    def control(self, text, owner, *, responder=None, wait=True):
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
            reviewed_changes.decide(self.path, parts[1], owner, parts[2])
            plan = reviewed_changes.get_plan(self.path, parts[1], owner)
            task = self.submit(
                "승인된 파일 변경안 적용",
                plan["workspace"],
                owner,
                kind="apply",
                plan_id=plan["id"],
                responder=responder,
            )
            if responder is None and wait:
                return self.wait(task["id"], owner).text
            return f"승인된 변경안 적용을 접수했습니다: {task['id']}"
        if command == "resume" and len(parts) == 2:
            store.resume(self.path, parts[1], owner, self.ensure_worker())
            if responder:
                thread = threading.Thread(target=self.deliver, args=(parts[1], owner, responder), daemon=True)
                self.watchers.append(thread)
                thread.start()
            if responder is None and wait:
                return self.wait(parts[1], owner).text
            return "사용자 요청으로 재시도를 등록했습니다. 모델/경로/권한을 다시 검사합니다."
        if command == "cancel" and len(parts) == 2:
            store.cancel(self.path, parts[1], owner)
            return "취소를 요청했습니다. 실행 중 작업은 종료 확인을 기다립니다."
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
