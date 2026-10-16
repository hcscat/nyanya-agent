#!/usr/bin/env python3
# ruff: noqa: F403,F405
"""Conversation store and task queue for NyaNya bridges."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import pathlib
import threading
import time
import secrets
from typing import Any, Callable

from nyanya_agent import core as nyanya
from nyanya_agent import dashboard_store
from nyanya_agent.bridge_policy import *
from nyanya_agent.bridge_runtime import *
from nyanya_agent.task_service import DurableTaskService
from nyanya_agent.task_outcomes import TaskOutcome, OutcomeSignal, as_outcome, outcome_from_error

@dataclass
class NyaNyaTask:
    owner_key: str
    conversation_key: str
    prompt: str
    mode: str
    responder: Callable[[str], None]
    request_id: str | None = None
    task_id: str | None = None
    project_id: str | None = None
    codex_session_id: str | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    created_at: float = field(default_factory=time.monotonic)
    started_at: float | None = None


class NyaNyaConversationStore:
    """Conversation context with a durable SQLite task queue."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.task_queue_max = int(os.getenv("NYANYA_TASK_QUEUE_MAX", DEFAULT_TASK_QUEUE_MAX))
        self._workspace_lock = threading.Lock()
        self.durable_tasks = DurableTaskService(status_callback=self._durable_status)
        from nyanya_agent.operation_service import OperationService
        self.operations = OperationService(self.durable_tasks.db_path)

    def _durable_status(self, record: dict[str, Any], status: str, message: str) -> None:
        """Keep the legacy dashboard projection readable during migration."""
        request_id = record.get("source_request_id")
        if not request_id:
            return
        mode = ""
        metadata = record.get("metadata")
        if isinstance(metadata, dict):
            mode = str(metadata.get("mode") or "")
        try:
            dashboard_store.mark_request_status(
                str(request_id),
                status,
                event_type=f"task_{status}",
                message=message,
                result_summary=message if status not in {"queued", "running"} else None,
                mode=mode or None,
                metadata={"task_id": record.get("id"), "project_id": record.get("project_id")},
            )
        except Exception as exc:  # noqa: BLE001 - compatibility telemetry must not break execution.
            print(f"NyaNya dashboard update failed: {type(exc).__name__}: {exc}", flush=True)

    def reset(self, key: str, *, owner_key: str | None = None) -> None:
        from nyanya_agent import conversation_store
        owner = owner_key or key
        conversation_store.reset(self.operations.path, owner, key, self.execution_workspace(owner))

    def answer(self, key: str, prompt: str) -> str:
        control = self.operations.control(prompt, key)
        if control is not None:
            return control
        workspace = self.execution_workspace(key)
        task = self.operations.submit(prompt, workspace, key, conversation_key=key)
        return self.operations.wait(task['id'], key).text

    def close(self):
        self.operations.close()
        self.durable_tasks.close()

    def _dashboard_mark(self, task: NyaNyaTask, status: str, **kwargs: Any) -> None:
        if not task.request_id:
            return
        try:
            dashboard_store.mark_request_status(task.request_id, status, **kwargs)
        except Exception as exc:  # noqa: BLE001 - telemetry must not break messenger handling.
            print(f"NyaNya dashboard update failed: {type(exc).__name__}: {exc}", flush=True)

    def _dashboard_event(self, task: NyaNyaTask, event_type: str, message: str, **metadata: Any) -> None:
        if not task.request_id:
            return
        try:
            dashboard_store.append_request_event(task.request_id, event_type, message, metadata=metadata)
        except Exception as exc:  # noqa: BLE001
            print(f"NyaNya dashboard event failed: {type(exc).__name__}: {exc}", flush=True)

    def save(self, key: str, *, owner_key: str | None = None) -> pathlib.Path | None:
        owner = owner_key or key
        return save_conversation(self.config, self.operations.path, owner, key, self.execution_workspace(owner))

    def status_text(self) -> str:
        status = visible_config(self.config)
        status["bridge_runtime"] = {
            "callback_queue_max_per_user": self.task_queue_max,
            "execution_path": "OperationService",
            "routing_policy": "bounded assessment selects configured Flash, Luna or Sol profiles",
            "external_callbacks": "durable upload callbacks do not invoke a model",
            "protected_delete_paths": [str(path) for path in protected_delete_paths()],
            "workspace_roots": [str(root) for root in workspace_roots()],
            "trusted_workspace_roots": [str(root) for root in trusted_workspace_roots()],
            "default_codex_workdir": str(default_codex_workdir()),
            "workspace_assignments": self.workspace_assignment_count(),
        }
        return json.dumps(status, ensure_ascii=False, indent=2)

    def task_status_text(self, owner_key: str | None = None) -> str:
        if owner_key is None:
            return self.durable_tasks.status_text(None)
        from nyanya_agent import operation_store

        rows = operation_store.incomplete(self.operations.path, owner_key)
        counts = {
            "running": sum(row["status"] in {"running", "cancelling"} for row in rows),
            "queued": sum(row["status"] == "queued" for row in rows),
        }
        return (
            f"진행 중: {counts['running']}개\n대기열: {counts['queued']}개\n"
            + operation_store.list_text(self.operations.path, owner_key)
        )

    def resources(self) -> str:
        return system_resource_report()

    def _load_workspace_config_unlocked(self) -> dict[str, Any]:
        path = workspace_config_path()
        if not path.exists():
            return {"version": 1, "users": {}}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"version": 1, "users": {}}
        if not isinstance(data, dict):
            return {"version": 1, "users": {}}
        users = data.get("users")
        if not isinstance(users, dict):
            data["users"] = {}
        data.setdefault("version", 1)
        return data

    def _save_workspace_config_unlocked(self, data: dict[str, Any]) -> None:
        path = workspace_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp_path.replace(path)

    def workspace_assignment_count(self) -> int:
        with self._workspace_lock:
            return len(self._load_workspace_config_unlocked().get("users", {}))

    def workspace_for_owner(self, owner_key: str) -> pathlib.Path | None:
        with self._workspace_lock:
            entry = self._load_workspace_config_unlocked().get("users", {}).get(owner_key)
        if not isinstance(entry, dict):
            return None
        raw_path = str(entry.get("workspace", "")).strip()
        if not raw_path:
            return None
        path = pathlib.Path(raw_path).expanduser().resolve(strict=False)
        if not is_allowed_workspace_path(path):
            return None
        return path

    def execution_workspace(self, owner_key: str) -> pathlib.Path:
        workspace = self.workspace_for_owner(owner_key)
        if workspace is None:
            raise OutcomeSignal("blocked", "등록된 사용자 작업공간이 없습니다. 관리자가 홈워크스페이스를 등록한 뒤 다시 요청하세요.")
        if not workspace.is_dir():
            raise OutcomeSignal("blocked", "등록된 작업공간이 없거나 디렉터리가 아닙니다.")
        return workspace

    def set_home(self, target_owner_key: str, workspace_value: str, *, set_by: str) -> str:
        try:
            workspace = resolve_workspace_path(workspace_value)
        except ValueError as exc:
            return f"홈워크스페이스 설정 실패: {exc}"
        workspace.mkdir(parents=True, exist_ok=True)
        with self._workspace_lock:
            data = self._load_workspace_config_unlocked()
            users = data.setdefault("users", {})
            users[target_owner_key] = {
                "workspace": str(workspace),
                "set_by": set_by,
                "set_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
            self._save_workspace_config_unlocked(data)
        return (
            "홈워크스페이스를 설정했습니다.\n"
            f"user={target_owner_key}\n"
            f"workspace={workspace}\n"
            "이 사용자의 Codex 작업은 해당 경로를 작업 디렉토리로 사용합니다."
        )

    def unset_home(self, target_owner_key: str) -> str:
        with self._workspace_lock:
            data = self._load_workspace_config_unlocked()
            users = data.setdefault("users", {})
            removed = users.pop(target_owner_key, None)
            self._save_workspace_config_unlocked(data)
        if removed is None:
            return f"설정된 홈워크스페이스가 없습니다: {target_owner_key}"
        return f"홈워크스페이스 설정을 해제했습니다: {target_owner_key}"

    def home_text(self, owner_key: str) -> str:
        workspace = self.workspace_for_owner(owner_key)
        if workspace is None:
            return (
                f"user={owner_key}\n"
                "전용 홈워크스페이스가 설정되어 있지 않습니다.\n"
                f"default_codex_workdir={default_codex_workdir()}\n"
                f"allowed_workspace_roots={', '.join(str(root) for root in workspace_roots())}\n"
                f"trusted_workspace_roots={', '.join(str(root) for root in trusted_workspace_roots())}"
            )
        return (
            f"user={owner_key}\n"
            f"home_workspace={workspace}\n"
            f"allowed_workspace_roots={', '.join(str(root) for root in workspace_roots())}\n"
            f"trusted_workspace_roots={', '.join(str(root) for root in trusted_workspace_roots())}"
        )

    def submit(
        self,
        *,
        owner_key: str,
        conversation_key: str,
        prompt: str,
        mode: str,
        responder: Callable[[str], None],
        request_id: str | None = None,
        operation: Callable[[NyaNyaTask, threading.Event], str] | None = None,
    ) -> str:
        task = NyaNyaTask(owner_key, conversation_key, prompt, mode, responder, request_id=request_id)
        if operation is None:
            try:
                workspace = self.execution_workspace(owner_key)
                profile = 'luna' if mode in {'codex', 'codex_write'} else 'flash' if mode == 'gemini' else 'auto'
                record = self.operations.submit(prompt, workspace, owner_key, profile=profile,
                                                source_request_id=request_id, conversation_key=conversation_key,
                                                responder=responder)
                if record["status"] == "blocked":
                    return f"요청을 보존하고 실행을 보류했습니다: {record['id']}\nwhy {record['id']}로 원인을 확인하세요."
                return f"요청을 접수했습니다. 확인해서 이어서 답할게요. ({record['id']})"
            except OutcomeSignal as exc:
                self._dashboard_mark(
                    task,
                    exc.outcome.status,
                    event_type="prerequisite_failed",
                    message=exc.outcome.text,
                    result_summary=exc.outcome.text,
                )
                return exc.outcome.text
            except (ValueError, OSError, RuntimeError) as exc:
                message = f"작업 접수 보류: {type(exc).__name__}. 워크스페이스와 worker 준비 상태를 확인하세요."
                self._dashboard_mark(
                    task,
                    "blocked",
                    event_type="prerequisite_failed",
                    message=message,
                    result_summary=message,
                )
                return message
        existing = self.durable_tasks.tasks_for_owner(owner_key)
        active = [item for item in existing if item.get("status") in {"running", "awaiting_approval", "blocked"}]
        queued_tasks = [item for item in existing if item.get("status") == "queued"]
        if len(queued_tasks) >= self.task_queue_max:
            self._dashboard_mark(
                task,
                "failed",
                event_type="queue_rejected",
                message="Task queue is full",
                error="Task queue is full",
            )
            return (
                "이미 처리 중인 작업과 대기 중인 작업이 있습니다. "
                "취소 후 다시 요청하세요. 취소하려면 `취소`라고 보내세요."
            )
        try:
            workspace = self.execution_workspace(owner_key)
        except OutcomeSignal as exc:
            self._dashboard_mark(task, "blocked", message=exc.outcome.text)
            return exc.outcome.text
        task_record = self.durable_tasks.submit(
            title=preview_text(prompt, limit=160),
            prompt=prompt,
            requested_by=owner_key,
            owner_key=owner_key,
            conversation_key=conversation_key,
            mode=mode,
            workspace_root=str(workspace),
            source_request_id=request_id,
            runner=lambda record, cancel_event: self._run_task_with_event(task, cancel_event, record, operation),
            responder=responder,
            metadata={"execution_adapter": "codex_cli" if mode.startswith("codex") else "provider"},
        )
        task.task_id = str(task_record["id"])
        task.project_id = task_record.get("project_id")
        started = not active and not queued_tasks
        queued = len(queued_tasks) + 1 if not started else 0
        return self._task_ack_text(task, queued=queued, started=started)

    def cancel_owner(self, owner_key: str) -> str:
        result = self.durable_tasks.cancel_owner(owner_key, actor=owner_key, reason="Cancel requested by owner")
        current = result["current"]
        queued = result["queued"]
        if current == 0 and queued == 0:
            return "취소할 진행 중/대기 작업이 없습니다."
        if current:
            return f"진행 중인 작업에 취소를 요청하고, 대기 작업 {queued}개를 제거했습니다."
        return f"대기 작업 {queued}개를 제거했습니다."

    def cancel_all(self) -> str:
        result = self.durable_tasks.cancel_all(actor="operator", reason="Cancel requested for all tasks")
        if result["current"] == 0 and result["queued"] == 0:
            return "취소할 전체 작업이 없습니다."
        return f"전체 작업 취소 요청 완료: 진행 중 {result['current']}개, 대기 {result['queued']}개."

    def is_owner(self, user_id: str) -> bool:
        owner_ids = parse_id_set(os.getenv("NYANYA_OWNER_USER_IDS"))
        return user_id in owner_ids

    def _run_task_with_event(
        self,
        task: NyaNyaTask,
        cancel_event: threading.Event,
        record: dict[str, Any] | None = None,
        operation: Callable[[NyaNyaTask, threading.Event], str] | None = None,
    ) -> str:
        task.cancel_event = cancel_event
        if record is not None:
            task.task_id = str(record["id"])
            task.project_id = record.get("project_id")
        if operation is not None:
            return self._run_operation(task, operation)
        return TaskOutcome("blocked", "외부 작업 callback이 없습니다. 일반 요청은 OperationService로 접수하세요.")

    def _run_operation(
        self,
        task: NyaNyaTask,
        operation: Callable[[NyaNyaTask, threading.Event], str],
    ) -> str:
        task.started_at = time.monotonic()
        self._dashboard_mark(
            task,
            "running",
            event_type="task_started",
            message="Worker thread started",
            mode=task.mode,
        )
        failed = False
        try:
            answer = operation(task, task.cancel_event)
        except Exception as exc:  # noqa: BLE001 - durable operation reports failure to the caller.
            answer = outcome_from_error(exc)
            failed = True
        return self._finish_task_result(task, answer, failed=failed)

    def _finish_task_result(self, task: NyaNyaTask, answer: str | TaskOutcome, *, failed: bool = False) -> TaskOutcome:
        outcome = as_outcome(answer)
        return outcome

    def _task_ack_text(self, task: NyaNyaTask, *, queued: int, started: bool) -> str:
        state_line = "즉시 실행을 시작합니다." if started else f"대기열에 등록했습니다. 현재 위치 {queued}/{self.task_queue_max}."
        route_line = "등록된 외부 작업 callback을 실행합니다."
        return (
            "요청을 접수했습니다.\n"
            f"task_id: {task.task_id or '-'}\n"
            f"project_id: {task.project_id or '-'}\n"
            f"목표: {preview_text(task.prompt, limit=240)}\n"
            "범위: 요청에 명시된 대상과 허용된 작업공간만 처리합니다. 명시되지 않은 외부 변경은 제외합니다.\n"
            "단계 일정:\n"
            "1. 요청·첨부·작업공간과 현재 상태를 확인합니다.\n"
            f"2. {route_line}\n"
            "3. 구현 또는 분석 결과를 검증합니다.\n"
            "4. 완료 결과, 남은 일, 사용자 조치를 구분해 보고합니다.\n"
            "상세 절차: 각 단계 시작과 장시간 진행 상태를 알리고, 확인 가능한 근거를 기록합니다.\n"
            "목표 변경 규칙: 목표·범위·위험이 달라지면 작업을 멈추고 변경 사유와 수정 계획의 승인을 요청합니다.\n"
            f"현재 상태: {state_line}\n"
            "상태 확인: `tasks`, `queue`, `작업목록`\n"
            "취소: `취소` 또는 `cancel`"
        )


def split_message(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = text
    while len(current) > limit:
        split_at = current.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(current[:split_at].rstrip())
        current = current[split_at:].lstrip()
    if current:
        chunks.append(current)
    return chunks


def preview_text(text: str, limit: int = 96) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def save_conversation(config, path, owner, key, workspace):
    """Shared screened, bounded and no-follow private export for all entry points."""
    if not config.get("save_transcripts", True):
        return None
    from nyanya_agent import conversation_store
    content = conversation_store.snapshot(path, owner, key, workspace)
    sessions = pathlib.Path(config.get("sessions_dir", "sessions"))
    if not sessions.is_absolute():
        sessions = nyanya.STATE_ROOT / sessions
    if os.name != "posix":
        raise ValueError("Private conversation exports require no-follow file operations")
    sessions = pathlib.Path(os.path.abspath(sessions))
    folder = os.open(sessions.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in sessions.parts[1:]:
            try:
                os.mkdir(part, mode=0o700, dir_fd=folder)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=folder)
            os.close(folder)
            folder = child
        name = f"nyanya-conversation-{secrets.token_hex(12)}.json"
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
        return sessions / name
    finally:
        os.close(folder)
