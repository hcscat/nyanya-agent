from __future__ import annotations

import sys
import time

import pytest

from nyanya_agent import execution_adapters as adapters
from nyanya_agent import execution_runtime
from nyanya_agent import execution_store as store


def test_coordinator_recovers_from_persisted_handle_and_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "is_allowed_workspace_path", lambda path: True)
    db_path = tmp_path / "runtime.db"
    task = store.create_task(title="Recoverable", db_path=db_path)
    first = execution_runtime.ExecutionCoordinator(
        db_path=db_path,
        adapters={"subprocess": adapters.ManagedSubprocessAdapter()},
    )
    execution = first.start_command(
        task_id=task["id"],
        adapter_type="subprocess",
        command=[sys.executable, "-c", "print('recover-ok')"],
        cwd=tmp_path,
    )

    time.sleep(0.15)
    restarted = execution_runtime.ExecutionCoordinator(
        db_path=db_path,
        adapters={"subprocess": adapters.ManagedSubprocessAdapter()},
    )
    observed = restarted.observe(execution["id"])

    assert observed["status"] == "succeeded"
    assert store.get_task(task["id"], db_path=db_path)["status"] == "completed"
    assert store.list_runtime_sessions(db_path=db_path)[0]["status"] == "stopped"


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

    time.sleep(0.15)
    completed = coordinator.observe(execution["id"])
    assert completed["status"] == "succeeded"
    assert store.acquire_writer_lease(resource_key="repo:test", owner_id="next", db_path=db_path) is not None


def test_coordinator_cancels_active_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "is_allowed_workspace_path", lambda path: True)
    db_path = tmp_path / "runtime.db"
    task = store.create_task(title="Cancel", db_path=db_path)
    coordinator = execution_runtime.ExecutionCoordinator(
        db_path=db_path,
        adapters={"subprocess": adapters.ManagedSubprocessAdapter()},
    )
    execution = coordinator.start_command(
        task_id=task["id"],
        adapter_type="subprocess",
        command=[sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=tmp_path,
    )

    cancelled = coordinator.cancel(execution["id"], reason="test")

    assert cancelled["status"] == "cancelled"
    assert store.get_task(task["id"], db_path=db_path)["status"] == "cancelled"
