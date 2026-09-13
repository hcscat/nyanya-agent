"""Durable task application service used by all NyaNya ingress adapters."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import os
from pathlib import Path
import threading
from typing import Any

from nyanya_agent import execution_store as ledger
from nyanya_agent import work_queue
from nyanya_agent.task_outcomes import TaskOutcome, as_outcome, outcome_from_error


TaskRunner = Callable[[dict[str, Any], threading.Event], str | TaskOutcome]
TaskResponder = Callable[[str], None]
StatusCallback = Callable[[dict[str, Any], str, str], None]

ACTIVE_TASK_STATUSES = {"running", "awaiting_approval", "blocked", "cancelling"}
ACTIVE_EXECUTION_STATUSES = {"pending", "starting", "running", "awaiting_approval", "cancelling", "stale"}


def _session_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


class DurableTaskService:
    """Submit and execute tasks through the SQLite execution ledger.

    The callback itself is process-local, but the task, execution, queue order,
    status transitions, and event history are durable. If the process exits
    before a callback completes, records remain available for operator review.
    They are never automatically replayed or declared failed by this service.
    """

    def __init__(
        self,
        *,
        db_path: str | Path | None = None,
        status_callback: StatusCallback | None = None,
    ) -> None:
        # Resolve the configured path once. A long-lived worker must not switch
        # databases if a caller later changes the process environment (and
        # tests may intentionally scope the environment per instance).
        self.db_path = ledger.legacy.resolve_db_path(db_path)
        self.status_callback = status_callback
        self.worker_id = ledger.new_id("worker")
        self._threads: set[threading.Thread] = set()
        self._closed = threading.Event()
        self._scheduler: threading.Thread | None = None
        self._lock = threading.RLock()
        self._handlers: dict[str, TaskRunner] = {}
        self._responders: dict[str, TaskResponder] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        ledger.apply_migrations(self.db_path)

    def _emit(self, task: dict[str, Any], status: str, message: str) -> None:
        if self.status_callback is None:
            return
        try:
            self.status_callback(task, status, message)
        except Exception:
            # Observability must never break task execution.
            return

    @staticmethod
    def _owner_key(task: dict[str, Any]) -> str:
        metadata = task.get("metadata")
        if isinstance(metadata, dict) and metadata.get("owner_key"):
            return str(metadata["owner_key"])
        return str(task.get("requested_by") or "operator")

    @staticmethod
    def _workspace_project_name(workspace_root: str) -> str:
        name = Path(workspace_root).name.strip()
        return name or "NyaNya Workspace"

    def _ensure_project(
        self,
        *,
        project_id: str | None,
        project_name: str | None,
        workspace_root: str,
        owner: str,
    ) -> str | None:
        if project_id:
            if ledger.get_project(project_id, db_path=self.db_path) is None:
                raise KeyError(project_id)
            return project_id
        workspace_root = workspace_root.strip()
        if not workspace_root:
            return None
        existing = ledger.find_project_by_workspace(workspace_root, db_path=self.db_path)
        if existing:
            return str(existing["id"])
        try:
            project = ledger.create_project(
                name=(project_name or self._workspace_project_name(workspace_root)).strip(),
                owner=owner,
                workspace_root=workspace_root,
                metadata={"created_by": "durable_task_service", "auto_provisioned": True},
                db_path=self.db_path,
            )
            return str(project["id"])
        except Exception:
            # A second process may have created the same workspace project.
            existing = ledger.find_project_by_workspace(workspace_root, db_path=self.db_path)
            if existing:
                return str(existing["id"])
            raise

    def ensure_codex_session(
        self,
        *,
        project_id: str,
        session_key: str,
        workspace_root: str,
        model: str = "",
        name: str = "Codex project session",
    ) -> dict[str, Any]:
        return ledger.create_codex_session(
            project_id=project_id,
            session_key=_session_key(session_key),
            name=name,
            workspace_root=workspace_root,
            model=model,
            metadata={"session_key_hash": _session_key(session_key)},
            db_path=self.db_path,
        )

    def submit(
        self,
        *,
        title: str,
        prompt: str,
        requested_by: str,
        owner_key: str,
        conversation_key: str,
        mode: str,
        runner: TaskRunner,
        responder: TaskResponder,
        priority: int = 100,
        project_id: str | None = None,
        project_name: str | None = None,
        workspace_root: str = "",
        codex_session_id: str | None = None,
        source_request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._closed.is_set():
            raise RuntimeError("Task service is closed")
        resolved_project_id = self._ensure_project(
            project_id=project_id,
            project_name=project_name,
            workspace_root=workspace_root,
            owner=requested_by,
        )
        task_metadata = {
            **(metadata or {}),
            "owner_key": owner_key,
            "conversation_key": conversation_key,
            "mode": mode,
            "workspace_root": workspace_root,
            "durable_execution": True,
        }
        task = (
            ledger.find_task_by_source_request(source_request_id, db_path=self.db_path)
            if source_request_id
            else None
        )
        if task is None:
            task = ledger.create_task(
                title=title,
                prompt=prompt,
                priority=priority,
                requested_by=requested_by,
                source_request_id=source_request_id,
                project_id=resolved_project_id,
                codex_session_id=codex_session_id,
                metadata=task_metadata,
                db_path=self.db_path,
            )
        else:
            task = ledger.update_task_context(
                task["id"],
                project_id=resolved_project_id,
                codex_session_id=codex_session_id,
                metadata=task_metadata,
                db_path=self.db_path,
            )
        with self._lock:
            task_id = str(task["id"])
            self._handlers[task_id] = runner
            self._responders[task_id] = responder
            self._cancel_events[task_id] = threading.Event()
        self._dispatch(owner_key)
        with self._lock:
            if self._scheduler is None or not self._scheduler.is_alive():
                self._scheduler = threading.Thread(target=self._poll, daemon=True)
                self._scheduler.start()
        return task

    def _tasks_for_owner(self, owner_key: str) -> list[dict[str, Any]]:
        return work_queue.pending_tasks(self.db_path, owner_key)

    def tasks_for_owner(self, owner_key: str) -> list[dict[str, Any]]:
        return self._tasks_for_owner(owner_key)

    def recovery_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            return [task for task in work_queue.recovery_tasks(self.db_path, self.worker_id)
                    if task["id"] not in self._handlers]

    def _poll(self) -> None:
        while not self._closed.wait(0.5):
            with self._lock:
                if not self._handlers:
                    self._scheduler = None
                    return
                owners = {self._owner_key(task) for task in work_queue.pending_tasks(self.db_path)
                          if task["id"] in self._handlers}
            for owner in owners:
                self._dispatch(owner)

    def _dispatch(self, owner_key: str) -> None:
        if self._closed.is_set():
            return
        with self._lock:
            tasks = self._tasks_for_owner(owner_key)
            if any(task.get("status") in ACTIVE_TASK_STATUSES for task in tasks):
                return
            # A stored record without a live operation is held for human review.
            queued = [task for task in tasks if task["status"] == "queued"]
            if not queued or queued[0]["id"] not in self._handlers:
                return
            task = queued[0]
            claimed = work_queue.claim(self.db_path, task["id"], self.worker_id, owner_key)
            if claimed is None:
                return
            thread = threading.Thread(target=self._run, args=(task, claimed), daemon=True)
            self._threads.add(thread)
            thread.start()

    def _run(self, task: dict[str, Any], claim: dict[str, Any]) -> None:
        task_id = str(task["id"])
        cancel_event = self._cancel_events[task_id]
        monitor_stop = threading.Event()
        lease_lost = threading.Event()

        def monitor() -> None:
            while not monitor_stop.wait(0.5):
                try:
                    if not work_queue.renew(self.db_path, claim):
                        lease_lost.set()
                        cancel_event.set()
                        return
                    execution = ledger.get_execution(claim["execution_id"], db_path=self.db_path)
                    if execution and execution["status"] == "cancelling":
                        cancel_event.set()
                except Exception:
                    lease_lost.set()
                    cancel_event.set()
                    return

        watcher = threading.Thread(target=monitor, daemon=True)
        watcher.start()
        try:
            self._emit(task, "running", "Local worker started")
            try:
                outcome = as_outcome(self._handlers[task_id](task, cancel_event))
            except Exception as exc:
                outcome = outcome_from_error(exc)
            if lease_lost.is_set():
                # No result or side effect may be acknowledged by a stale worker.
                return
            work_queue.finish(self.db_path, claim, outcome)
            current = ledger.get_task(task_id, db_path=self.db_path) or task
            saved = work_queue.result(self.db_path, task_id, self._owner_key(task))
            answer = saved["response"] if saved else outcome.text
            self._emit(current, current["status"], answer)
            try:
                self._responders[task_id](answer)
            except Exception as exc:
                work_queue.record_delivery(self.db_path, claim["execution_id"], delivered=False,
                                           error=type(exc).__name__)
            else:
                work_queue.record_delivery(self.db_path, claim["execution_id"], delivered=True)
        except Exception:
            # Preserve an uncommitted/expired attempt for operator reconciliation.
            # Never force a terminal status over a newer execution.
            self._emit(task, "blocked", "Worker result could not be committed; operator review required")
        finally:
            monitor_stop.set()
            watcher.join(timeout=2)
            with self._lock:
                self._handlers.pop(task_id, None)
                self._responders.pop(task_id, None)
                self._cancel_events.pop(task_id, None)
                self._threads.discard(threading.current_thread())
            self._dispatch(self._owner_key(task))

    def close(self, timeout: float = 5.0) -> None:
        """Bounded shutdown; unresolved operations remain recorded for review."""
        self._closed.set()
        with self._lock:
            for event in self._cancel_events.values():
                event.set()
            threads = list(self._threads)
            if self._scheduler:
                threads.append(self._scheduler)
        import time
        deadline = time.monotonic() + timeout
        for thread in threads:
            thread.join(timeout=max(0, deadline - time.monotonic()))

    def run_sync(
        self,
        *,
        title: str,
        prompt: str,
        requested_by: str,
        owner_key: str,
        conversation_key: str,
        mode: str,
        runner: TaskRunner,
        priority: int = 100,
        project_id: str | None = None,
        project_name: str | None = None,
        workspace_root: str = "",
        codex_session_id: str | None = None,
        source_request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        wait_seconds: float | None = None,
        return_outcome: bool = False,
    ) -> str | TaskOutcome:
        """Submit a task and wait for its durable final response.

        This is the synchronous facade used by the terminal CLI. Execution is
        still performed by the same worker, queue, lease, and SQLite records as
        asynchronous bridge requests.
        """
        completed = threading.Event()
        result: list[str] = []

        def responder(answer: str) -> None:
            result.append(answer)
            completed.set()

        task = self.submit(
            title=title,
            prompt=prompt,
            requested_by=requested_by,
            owner_key=owner_key,
            conversation_key=conversation_key,
            mode=mode,
            runner=runner,
            responder=responder,
            priority=priority,
            project_id=project_id,
            project_name=project_name,
            workspace_root=workspace_root,
            codex_session_id=codex_session_id,
            source_request_id=source_request_id,
            metadata=metadata,
        )
        timeout = wait_seconds
        if timeout is None:
            timeout = max(60.0, float(os.getenv("NYANYA_TERMINAL_TASK_TIMEOUT_SECONDS", "86400")))
        if completed.wait(timeout):
            saved = work_queue.result(self.db_path, task["id"], owner_key)
            outcome = TaskOutcome(saved["outcome"], saved["response"]) if saved else TaskOutcome("failed", "작업 결과가 비어 있습니다.")
            return outcome if return_outcome else outcome.text
        self.cancel_task(task["id"], actor=requested_by, reason="Synchronous task wait timed out")
        outcome = TaskOutcome("timed_out", "작업 대기 시간이 초과되었습니다. 실제 실행 종료 여부를 확인하세요.")
        return outcome if return_outcome else outcome.text

    def cancel_task(self, task_id: str, *, actor: str = "operator", reason: str = "") -> dict[str, Any]:
        task = ledger.get_task(task_id, db_path=self.db_path)
        if task is None:
            raise KeyError(task_id)
        if task["status"] in ledger.TASK_TERMINAL_STATUSES:
            return task
        with self._lock:
            event = self._cancel_events.get(task_id)
            if event is not None:
                event.set()
        execution_id = task.get("current_execution_id")
        if execution_id:
            execution = ledger.get_execution(execution_id, db_path=self.db_path)
            if execution and execution["status"] == "awaiting_approval":
                return ledger.transition_execution(execution_id, "cancelled", actor=actor,
                                                   message="Operator dismissed held work", db_path=self.db_path)
            if execution and execution["status"] in ACTIVE_EXECUTION_STATUSES:
                return ledger.transition_execution(
                    execution_id,
                    "cancelling",
                    actor=actor,
                    message=reason or "Cancellation requested",
                    force=True,
                    db_path=self.db_path,
                )
        cancelled = ledger.transition_task(
            task_id,
            "cancelled",
            actor=actor,
            message=reason or "Task cancelled",
            force=True,
            db_path=self.db_path,
        )
        self._emit(cancelled, "cancelled", reason or "Task cancelled")
        self._dispatch(self._owner_key(cancelled))
        return cancelled

    def cancel_owner(self, owner_key: str, *, actor: str = "operator", reason: str = "") -> dict[str, int]:
        current = 0
        queued = 0
        for task in self._tasks_for_owner(owner_key):
            if task["status"] in ACTIVE_TASK_STATUSES:
                current += 1
                self.cancel_task(task["id"], actor=actor, reason=reason)
            elif task["status"] == "queued":
                queued += 1
                self.cancel_task(task["id"], actor=actor, reason=reason)
        return {"current": current, "queued": queued}

    def cancel_all(self, *, actor: str = "operator", reason: str = "") -> dict[str, int]:
        owners = {
            self._owner_key(task)
            for task in work_queue.pending_tasks(self.db_path)
            if task.get("status") in ACTIVE_TASK_STATUSES or task.get("status") == "queued"
        }
        totals = {"current": 0, "queued": 0}
        for owner_key in owners:
            result = self.cancel_owner(owner_key, actor=actor, reason=reason)
            totals["current"] += result["current"]
            totals["queued"] += result["queued"]
        return totals

    def status_text(self, owner_key: str | None = None) -> str:
        tasks = work_queue.pending_tasks(self.db_path, owner_key)
        if owner_key:
            tasks = [task for task in tasks if self._owner_key(task) == owner_key]
        active = [task for task in tasks if task.get("status") in ACTIVE_TASK_STATUSES]
        queued = [task for task in tasks if task.get("status") == "queued"]
        scope = "내 작업" if owner_key else "전체 작업"
        lines = [
            f"{scope} 목록",
            f"- 진행 중: {len(active)}개",
            f"- 대기열: {len(queued)}개",
        ]
        if not active and not queued:
            lines.append("현재 진행 중이거나 대기 중인 작업이 없습니다.")
            return "\n".join(lines)
        if active:
            lines.append("\n진행 중")
            lines.extend(self._format_line(task, "진행 중") for task in active)
        if queued:
            lines.append("\n대기열")
            lines.extend(self._format_line(task, "대기", index=index) for index, task in enumerate(queued, 1))
        lines.append("\n취소: `취소` 또는 `cancel`")
        return "\n".join(lines)

    @staticmethod
    def _format_line(task: dict[str, Any], status: str, *, index: int | None = None) -> str:
        metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        project = task.get("project_id") or "unassigned"
        session = task.get("codex_session_id") or "-"
        prefix = f"{index}. " if index is not None else "- "
        return (
            f"{prefix}{status}: task_id={task['id']}, project={project}, codex_session={session}\n"
            f"   mode={metadata.get('mode', '-')}, prompt={str(task.get('title') or task.get('prompt') or '')[:180]}"
        )
