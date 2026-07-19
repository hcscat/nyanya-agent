from __future__ import annotations

from pathlib import Path
import json
import shutil
import sys
import time

import pytest

from nyanya_agent import execution_adapters as adapters


def wait_for_terminal(adapter, handle, timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    observation = adapter.observe(handle)
    while observation.running and time.monotonic() < deadline:
        time.sleep(0.05)
        observation = adapter.observe(handle)
    return observation


def test_managed_subprocess_persists_completion_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "is_allowed_workspace_path", lambda path: True)
    adapter = adapters.ManagedSubprocessAdapter()
    request = adapters.AdapterRequest(
        execution_id="managed-test",
        command=(sys.executable, "-c", "print('adapter-ok')"),
        cwd=tmp_path,
        output_dir=tmp_path / "output",
    )

    handle = adapter.start(request)
    observation = wait_for_terminal(adapter, handle)

    assert observation.status == "succeeded"
    assert observation.exit_code == 0
    assert "adapter-ok" in observation.output_tail
    assert Path(handle.status_file).exists()


def test_managed_subprocess_can_cancel_process_group(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "is_allowed_workspace_path", lambda path: True)
    adapter = adapters.ManagedSubprocessAdapter()
    request = adapters.AdapterRequest(
        execution_id="cancel-test",
        command=(sys.executable, "-c", "import time; time.sleep(30)"),
        cwd=tmp_path,
        output_dir=tmp_path / "output",
    )

    handle = adapter.start(request)
    cancelled = adapter.cancel(handle, grace_seconds=0.2)

    assert cancelled.status == "cancelled"
    assert cancelled.running is False


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is not installed")
def test_tmux_adapter_discovers_and_completes_session(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "is_allowed_workspace_path", lambda path: True)
    adapter = adapters.TmuxAdapter()
    request = adapters.AdapterRequest(
        execution_id="tmux-adapter-test",
        command=(sys.executable, "-c", "print('tmux-ok')"),
        cwd=tmp_path,
        output_dir=tmp_path / "output",
    )

    handle = adapter.start(request)
    observation = wait_for_terminal(adapter, handle)

    assert observation.status == "succeeded"
    assert observation.exit_code == 0
    assert "tmux-ok" in observation.output_tail


def test_cli_adapters_build_explicit_safety_commands(tmp_path):
    codex = adapters.CodexAdapter(binary="codex")
    readonly = codex.build_request(execution_id="read", prompt="inspect", cwd=tmp_path)
    writable = codex.build_request(execution_id="write", prompt="edit", cwd=tmp_path, write=True)
    antigravity = adapters.AntigravityAdapter(binary="agy").build_request(
        execution_id="agy", prompt="inspect", cwd=tmp_path
    )

    assert readonly.command[readonly.command.index("--profile") + 1] == "nyanya-readonly"
    assert readonly.command[readonly.command.index("--sandbox") + 1] == "read-only"
    assert writable.command[writable.command.index("--profile") + 1] == "nyanya-approved-write"
    assert writable.command[writable.command.index("--sandbox") + 1] == "workspace-write"
    assert "--sandbox" in antigravity.command


def test_orca_adapter_maps_terminal_and_reports_runtime_state(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "is_allowed_workspace_path", lambda path: True)
    fake_orca = tmp_path / "orca"
    fake_orca.write_text(
        """#!/bin/sh
case \"$1 $2\" in
  \"status --json\")
    printf '%s\\n' '{\"ok\":true,\"result\":{\"runtime\":{\"state\":\"ready\",\"reachable\":true,\"runtimeId\":\"runtime-test\"}}}' ;;
  \"terminal create\")
    printf '%s\\n' '{\"ok\":true,\"result\":{\"terminal\":{\"handle\":\"term-test\",\"tabId\":\"tab-test\",\"worktreeId\":\"repo::path\"}}}' ;;
  \"terminal show\")
    printf '%s\\n' '{\"ok\":true,\"result\":{\"terminal\":{\"handle\":\"term-test\",\"connected\":true}}}' ;;
  \"terminal close\"|\"worktree set\")
    printf '%s\\n' '{\"ok\":true,\"result\":{}}' ;;
  *)
    printf '%s\\n' '{\"ok\":false,\"error\":{\"message\":\"unexpected command\"}}'; exit 1 ;;
esac
""",
        encoding="utf-8",
    )
    fake_orca.chmod(0o755)
    adapter = adapters.OrcaAdapter(binary=str(fake_orca), fallback_to_tmux=False)
    request = adapters.AdapterRequest(
        execution_id="orca-test",
        command=(sys.executable, "-c", "print('orca-ok')"),
        cwd=tmp_path,
        output_dir=tmp_path / "output",
    )

    assert adapter.probe()["runtime_state"] == "ready"
    handle = adapter.start(request)
    observation = adapter.observe(handle)
    cancelled = adapter.cancel(handle)

    assert handle.external_id == "term-test"
    assert handle.metadata["transport"] == "orca"
    assert observation.status == "running"
    assert cancelled.status == "cancelled"


def test_orca_adapter_uses_completion_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "is_allowed_workspace_path", lambda path: True)
    status_file = tmp_path / "status.json"
    status_file.write_text(json.dumps({"returncode": 0}), encoding="utf-8")
    handle = adapters.AdapterHandle(
        adapter_type="orca",
        execution_id="done",
        external_id="term-done",
        pid=None,
        tmux_session="",
        started_at=adapters.now_iso(),
        status_file=str(status_file),
        stdout_file=str(tmp_path / "stdout.log"),
        stderr_file=str(tmp_path / "stderr.log"),
        metadata={"transport": "orca"},
    )
    adapter = adapters.OrcaAdapter(binary="missing-orca", fallback_to_tmux=False)

    observation = adapter.observe(handle)

    assert observation.status == "succeeded"
    assert "Orca terminal completion marker" in observation.evidence


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is not installed")
def test_orca_adapter_falls_back_to_tmux_when_runtime_is_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "is_allowed_workspace_path", lambda path: True)
    fake_orca = tmp_path / "orca-offline"
    fake_orca.write_text(
        """#!/bin/sh
printf '%s\\n' '{\"ok\":false,\"error\":{\"message\":\"runtime offline\"}}'
exit 1
""",
        encoding="utf-8",
    )
    fake_orca.chmod(0o755)
    adapter = adapters.OrcaAdapter(binary=str(fake_orca), fallback_to_tmux=True)
    request = adapters.AdapterRequest(
        execution_id="orca-fallback-test",
        command=(sys.executable, "-c", "print('fallback-ok')"),
        cwd=tmp_path,
        output_dir=tmp_path / "output",
    )

    handle = adapter.start(request)
    observation = wait_for_terminal(adapter, handle)

    assert handle.metadata["transport"] == "tmux-fallback"
    assert observation.status == "succeeded"
    assert "fallback-ok" in observation.output_tail
    assert "Orca offline tmux fallback" in observation.evidence


def test_artifact_collector_rejects_escape_and_records_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(adapters, "is_allowed_workspace_path", lambda path: True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    artifact = workspace / "report.txt"
    artifact.write_text("result", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    collector = adapters.ArtifactCollector(workspace)

    evidence = collector.inspect(artifact)

    assert evidence["size_bytes"] == 6
    assert len(evidence["sha256"]) == 64
    with pytest.raises(PermissionError):
        collector.inspect(outside)
