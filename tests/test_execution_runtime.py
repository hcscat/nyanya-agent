from __future__ import annotations

import sys
import time

import pytest

from nyanya_agent.approval_contract import command_scope
from nyanya_agent import execution_adapters as adapters
from nyanya_agent import execution_runtime
from nyanya_agent import execution_store as store


def recorded_execution(tmp_path, db_path, command):
    """Seed an owned legacy handle; the coordinator only reconciles stored work."""
    task = store.create_task(title="Recorded adapter", db_path=db_path)
    execution = store.create_execution(task_id=task["id"], adapter_type="subprocess",
                                       status="starting", db_path=db_path)
    adapter = adapters.ManagedSubprocessAdapter()
    handle = adapter.start(adapters.AdapterRequest(
        execution_id=execution["id"], command=tuple(command), cwd=tmp_path,
        output_dir=tmp_path / execution["id"],
    ))
    store.heartbeat_runtime_session(
        session_id=f"runtime_{execution['id']}", execution_id=execution["id"],
        adapter_type="subprocess", external_id=handle.external_id, status="running",
        pid=handle.pid, metadata={"handle": handle.to_dict()}, db_path=db_path,
    )
    execution = store.transition_execution(execution["id"], "running", db_path=db_path)
    return task, execution, adapter, handle


def wait_for_marker(handle):
    deadline = time.monotonic() + 5
    while not adapters._read_marker(handle.status_file) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert adapters._read_marker(handle.status_file)


def test_coordinator_recovers_from_persisted_handle_and_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "is_allowed_workspace_path", lambda path: True)
    db_path = tmp_path / "runtime.db"
    task, execution, adapter, handle = recorded_execution(
        tmp_path, db_path, [sys.executable, "-c", "print('recover-ok')"],
    )
    try:
        wait_for_marker(handle)
        restarted = execution_runtime.ExecutionCoordinator(
            db_path=db_path, adapters={"subprocess": adapters.ManagedSubprocessAdapter()},
        )
        observed = restarted.recover_active()
        assert len(observed) == 1
        assert observed[0]["id"] == execution["id"]
        assert observed[0]["status"] == "succeeded"
        assert store.get_task(task["id"], db_path=db_path)["status"] == "completed"
        assert store.list_runtime_sessions(db_path=db_path)[0]["status"] == "stopped"
    finally:
        adapter.cancel(handle)


def test_recovery_releases_persisted_writer_lease(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "is_allowed_workspace_path", lambda path: True)
    db_path = tmp_path / "runtime.db"
    _, execution, adapter, handle = recorded_execution(
        tmp_path, db_path, [sys.executable, "-c", "print('finished')"],
    )
    try:
        lease = store.acquire_writer_lease(resource_key="repo:test", owner_id=execution["id"], db_path=db_path)
        assert lease is not None
        store.transition_execution(execution["id"], "running", metadata={
            "writer_lease": {"resource_key": "repo:test", "fence_token": lease["fence_token"]},
        }, db_path=db_path)
        wait_for_marker(handle)
        coordinator = execution_runtime.ExecutionCoordinator(
            db_path=db_path, adapters={"subprocess": adapters.ManagedSubprocessAdapter()},
        )
        assert coordinator.observe(execution["id"])["status"] == "succeeded"
        assert store.acquire_writer_lease(resource_key="repo:test", owner_id="next", db_path=db_path) is not None
    finally:
        adapter.cancel(handle)


def test_coordinator_cancels_active_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "is_allowed_workspace_path", lambda path: True)
    db_path = tmp_path / "runtime.db"
    task, execution, adapter, handle = recorded_execution(
        tmp_path, db_path, [sys.executable, "-c", "import time; time.sleep(30)"],
    )
    try:
        coordinator = execution_runtime.ExecutionCoordinator(
            db_path=db_path, adapters={"subprocess": adapter},
        )
        cancelled = coordinator.cancel(execution["id"], reason="test")
        assert cancelled["status"] == "cancelled"
        assert store.get_task(task["id"], db_path=db_path)["status"] == "cancelled"
    finally:
        adapter.cancel(handle)


def test_write_execution_requires_matching_persisted_approval(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "is_allowed_workspace_path", lambda path: True)
    db_path = tmp_path / "runtime.db"
    task = store.create_task(title="Write", db_path=db_path)
    coordinator = execution_runtime.ExecutionCoordinator(
        db_path=db_path,
        adapters={"subprocess": adapters.ManagedSubprocessAdapter()},
    )

    with pytest.raises(PermissionError, match="persisted approval"):
        coordinator.start_command(
            task_id=task["id"],
            adapter_type="subprocess",
            command=[sys.executable, "-c", "print('write')"],
            cwd=tmp_path,
            write_resource_key="repo:test",
        )

    approval = store.request_approval(
        task_id=task["id"],
        action="workspace.write",
        requested_by="agent",
        metadata={"authorized_actor": "operator", "scope_hash": command_scope(
            command=[sys.executable, "-c", "print('write-ok')"], cwd=tmp_path,
            adapter_type="subprocess", write_resource_key="repo:test")},
        db_path=db_path,
    )
    store.decide_approval(
        approval["id"],
        decision="approved",
        decided_by="operator",
        db_path=db_path,
    )
    execution = coordinator.start_command(
        task_id=task["id"],
        adapter_type="subprocess",
        command=[sys.executable, "-c", "print('write-ok')"],
        cwd=tmp_path,
        write_resource_key="repo:test",
        approval_id=approval["id"],
    )

    session = store.list_runtime_sessions(db_path=db_path)[0]
    wait_for_marker(adapters.AdapterHandle(**session["metadata"]["handle"]))
    completed = coordinator.observe(execution["id"])
    assert completed["status"] == "succeeded"
    assert store.acquire_writer_lease(resource_key="repo:test", owner_id="next", db_path=db_path) is not None
