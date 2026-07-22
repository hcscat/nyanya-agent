#!/usr/bin/env python3
"""Coordinate execution adapters with the persistent NyaNya execution ledger."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nyanya_agent import execution_store as store
from nyanya_agent.execution_adapters import (
    AdapterHandle,
    AdapterObservation,
    AdapterRequest,
    AntigravityAdapter,
    CodexAdapter,
    ExecutionAdapter,
    ManagedSubprocessAdapter,
    OrcaAdapter,
    TmuxAdapter,
)


ACTIVE_EXECUTION_STATUSES = {"pending", "starting", "running", "awaiting_approval", "cancelling", "stale"}


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class ExecutionCoordinator:
    def __init__(
        self,
        *,
        db_path: str | Path | None = None,
        adapters: dict[str, ExecutionAdapter] | None = None,
    ) -> None:
        self.db_path = db_path
        self.adapters: dict[str, ExecutionAdapter] = adapters or {
            "subprocess": ManagedSubprocessAdapter(),
            "tmux": TmuxAdapter(),
            "orca": OrcaAdapter(),
            "codex": CodexAdapter(),
            "antigravity": AntigravityAdapter(),
        }

    def inventory(self) -> list[dict[str, Any]]:
        inventory = []
        for name, adapter in self.adapters.items():
            try:
                probe = adapter.probe()
            except Exception as exc:
                probe = {"available": False, "error": f"{type(exc).__name__}: {exc}"}
            inventory.append(
                {
                    "name": name,
                    "capabilities": adapter.capabilities.__dict__,
                    "probe": probe,
                }
            )
        return inventory

    def _adapter(self, adapter_type: str) -> ExecutionAdapter:
        try:
            return self.adapters[adapter_type]
        except KeyError as exc:
            raise ValueError(f"Unknown execution adapter: {adapter_type}") from exc

    def _session_for_execution(self, execution_id: str) -> dict[str, Any] | None:
        sessions = store.list_runtime_sessions(
            stale_after_seconds=90,
            offline_after_seconds=300,
            db_path=self.db_path,
        )
        return next((session for session in sessions if session.get("execution_id") == execution_id), None)

    def _release_lease(self, execution: dict[str, Any]) -> None:
        lease = execution.get("metadata", {}).get("writer_lease")
        if not isinstance(lease, dict):
            return
        try:
            store.release_writer_lease(
                resource_key=str(lease["resource_key"]),
                owner_id=execution["id"],
                fence_token=int(lease["fence_token"]),
                db_path=self.db_path,
            )
        except (KeyError, TypeError, ValueError):
            return

    def start_command(
        self,
        *,
        task_id: str,
        adapter_type: str,
        command: list[str] | tuple[str, ...],
        cwd: str | Path,
        host_id: str | None = None,
        agent_profile_id: str | None = None,
        timeout_seconds: int = 600,
        env: dict[str, str] | None = None,
        write_resource_key: str | None = None,
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        adapter = self._adapter(adapter_type)
        if write_resource_key:
            if not approval_id:
                raise PermissionError("A persisted approval is required for write-capable execution")
            approval = store.get_approval(approval_id, db_path=self.db_path)
            if approval is None or approval["status"] != "approved" or approval["task_id"] != task_id:
                raise PermissionError("The supplied approval is not approved for this task")

        execution = store.create_execution(
            task_id=task_id,
            adapter_type=adapter_type,
            host_id=host_id,
            agent_profile_id=agent_profile_id,
            status="starting",
            command_summary=" ".join(command[:3]),
            workdir=str(Path(cwd).expanduser().resolve(strict=False)),
            metadata={"timeout_seconds": timeout_seconds, "approval_id": approval_id or ""},
            db_path=self.db_path,
        )
        lease = None
        if write_resource_key:
            lease = store.acquire_writer_lease(
                resource_key=write_resource_key,
                owner_id=execution["id"],
                ttl_seconds=max(60, timeout_seconds + 30),
                metadata={"task_id": task_id, "approval_id": approval_id},
                db_path=self.db_path,
            )
            if lease is None:
                store.transition_execution(
                    execution["id"],
                    "failed",
                    error=f"Writer lease is held: {write_resource_key}",
                    db_path=self.db_path,
                )
                raise RuntimeError(f"Writer lease is held: {write_resource_key}")
            execution = store.transition_execution(
                execution["id"],
                "starting",
                metadata={
                    "writer_lease": {
                        "resource_key": write_resource_key,
                        "fence_token": lease["fence_token"],
                    }
                },
                db_path=self.db_path,
            )

        request = AdapterRequest(
            execution_id=execution["id"],
            command=tuple(command),
            cwd=Path(cwd),
            env=env or {},
            timeout_seconds=timeout_seconds,
        )
        try:
            handle = adapter.start(request)
        except Exception as exc:
            failed = store.transition_execution(
                execution["id"],
                "failed",
                error=f"{type(exc).__name__}: {exc}",
                db_path=self.db_path,
            )
            self._release_lease(failed)
            raise

        store.heartbeat_runtime_session(
            session_id=f"runtime_{execution['id']}",
            execution_id=execution["id"],
            host_id=host_id,
            adapter_type=adapter_type,
            external_id=handle.external_id,
            status="running",
            pid=handle.pid,
            tmux_session=handle.tmux_session,
            metadata={"handle": handle.to_dict()},
            db_path=self.db_path,
        )
        return store.transition_execution(
            execution["id"],
            "running",
            message=f"{adapter_type} adapter started",
            metadata={"runtime_session_id": f"runtime_{execution['id']}"},
            db_path=self.db_path,
        )

    def observe(self, execution_id: str) -> dict[str, Any]:
        execution = store.get_execution(execution_id, db_path=self.db_path)
        if execution is None:
            raise KeyError(execution_id)
        session = self._session_for_execution(execution_id)
        if session is None:
            if execution["status"] in ACTIVE_EXECUTION_STATUSES:
                execution = store.transition_execution(
                    execution_id,
                    "lost",
                    status_confidence=0.4,
                    error="Runtime session record is missing",
                    force=True,
                    db_path=self.db_path,
                )
            return execution
        handle_data = session.get("metadata", {}).get("handle")
        if not isinstance(handle_data, dict):
            raise RuntimeError(f"Runtime handle is missing for {execution_id}")
        handle = AdapterHandle(**handle_data)
        adapter = self._adapter(execution["adapter_type"])

        timeout_seconds = int(execution.get("metadata", {}).get("timeout_seconds", 600))
        started_at = _parse_iso(execution.get("started_at"))
        if started_at and execution["status"] in ACTIVE_EXECUTION_STATUSES:
            age_seconds = (datetime.now(UTC) - started_at).total_seconds()
            if age_seconds > timeout_seconds:
                adapter.cancel(handle, grace_seconds=2.0)
                timed_out = store.transition_execution(
                    execution_id,
                    "timed_out",
                    error=f"Execution exceeded {timeout_seconds} seconds",
                    status_confidence=1.0,
                    force=True,
                    db_path=self.db_path,
                )
                store.heartbeat_runtime_session(
                    session_id=session["id"],
                    execution_id=execution_id,
                    host_id=session.get("host_id"),
                    adapter_type=execution["adapter_type"],
                    external_id=handle.external_id,
                    status="failed",
                    pid=handle.pid,
                    tmux_session=handle.tmux_session,
                    metadata={"handle": handle.to_dict(), "observation": {"status": "timed_out"}},
                    db_path=self.db_path,
                )
                self._release_lease(timed_out)
                return timed_out

        observation = adapter.observe(handle)
        return self._apply_observation(execution, session, handle, observation)

    def _apply_observation(
        self,
        execution: dict[str, Any],
        session: dict[str, Any],
        handle: AdapterHandle,
        observation: AdapterObservation,
    ) -> dict[str, Any]:
        execution_id = execution["id"]
        if observation.running:
            observed_status = "stale" if observation.status == "stale" else "running"
            store.heartbeat_runtime_session(
                session_id=session["id"],
                execution_id=execution_id,
                host_id=session.get("host_id"),
                adapter_type=execution["adapter_type"],
                external_id=handle.external_id,
                status=observed_status,
                pid=handle.pid,
                tmux_session=handle.tmux_session,
                metadata={"handle": handle.to_dict(), "observation": observation.__dict__},
                db_path=self.db_path,
            )
            if observed_status == "stale" and execution["status"] != "stale":
                return store.transition_execution(
                    execution_id,
                    "stale",
                    status_confidence=observation.confidence,
                    metadata={"evidence": list(observation.evidence)},
                    db_path=self.db_path,
                )
            if observed_status == "running" and execution["status"] == "stale":
                return store.transition_execution(
                    execution_id,
                    "running",
                    status_confidence=observation.confidence,
                    db_path=self.db_path,
                )
            return execution

        status = observation.status
        if status not in store.EXECUTION_TERMINAL_STATUSES:
            status = "lost"
        transitioned = store.transition_execution(
            execution_id,
            status,
            exit_code=observation.exit_code,
            error=observation.error_tail,
            status_confidence=observation.confidence,
            metadata={"evidence": list(observation.evidence), "output_tail": observation.output_tail[-2000:]},
            force=True,
            db_path=self.db_path,
        )
        store.heartbeat_runtime_session(
            session_id=session["id"],
            execution_id=execution_id,
            host_id=session.get("host_id"),
            adapter_type=execution["adapter_type"],
            external_id=handle.external_id,
            status="stopped" if status in {"succeeded", "cancelled"} else "failed",
            pid=handle.pid,
            tmux_session=handle.tmux_session,
            metadata={"handle": handle.to_dict(), "observation": observation.__dict__},
            db_path=self.db_path,
        )
        self._release_lease(transitioned)
        return transitioned

    def cancel(self, execution_id: str, *, actor: str = "operator", reason: str = "") -> dict[str, Any]:
        execution = store.get_execution(execution_id, db_path=self.db_path)
        if execution is None:
            raise KeyError(execution_id)
        if execution["status"] in store.EXECUTION_TERMINAL_STATUSES:
            return execution
        session = self._session_for_execution(execution_id)
        if session is None:
            return store.transition_execution(
                execution_id,
                "lost",
                actor=actor,
                error="Runtime session record is missing during cancellation",
                force=True,
                db_path=self.db_path,
            )
        handle_data = session.get("metadata", {}).get("handle")
        if not isinstance(handle_data, dict):
            raise RuntimeError(f"Runtime handle is missing for {execution_id}")
        handle = AdapterHandle(**handle_data)
        adapter = self._adapter(execution["adapter_type"])
        store.transition_execution(
            execution_id,
            "cancelling",
            actor=actor,
            message=reason or "Cancellation requested",
            force=True,
            db_path=self.db_path,
        )
        observation = adapter.cancel(handle)
        confirmed = observation.status == "cancelled"
        cancelled = store.transition_execution(
            execution_id,
            "cancelled" if confirmed else "lost",
            actor=actor,
            message=(reason or "Execution cancelled")
            if confirmed
            else "Cancellation could not be confirmed",
            exit_code=observation.exit_code,
            status_confidence=observation.confidence,
            metadata={"evidence": list(observation.evidence)},
            force=True,
            db_path=self.db_path,
        )
        store.heartbeat_runtime_session(
            session_id=session["id"],
            execution_id=execution_id,
            host_id=session.get("host_id"),
            adapter_type=execution["adapter_type"],
            external_id=handle.external_id,
            status="cancelled" if confirmed else "failed",
            pid=handle.pid,
            tmux_session=handle.tmux_session,
            metadata={"handle": handle.to_dict(), "observation": observation.__dict__},
            db_path=self.db_path,
        )
        self._release_lease(cancelled)
        return cancelled

    def recover_active(self) -> list[dict[str, Any]]:
        recovered = []
        for execution in store.list_executions(limit=500, db_path=self.db_path):
            if execution["status"] in ACTIVE_EXECUTION_STATUSES:
                recovered.append(self.observe(execution["id"]))
        return recovered
