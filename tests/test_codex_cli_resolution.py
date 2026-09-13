import errno
from pathlib import Path

import pytest

from nyanya_agent import bridge_runtime, codex_cli


@pytest.fixture
def executable(tmp_path):
    path = tmp_path / "codex"
    path.write_text("#!/bin/sh\nprintf ok\n")
    path.chmod(0o755)
    return path


def test_path_discovery(monkeypatch, executable):
    monkeypatch.delenv("NYANYA_CODEX_CLI", raising=False)
    monkeypatch.setenv("PATH", str(executable.parent))
    assert codex_cli.resolve_codex_cli() == str(executable)


def test_broken_override_does_not_fallback(monkeypatch, executable):
    monkeypatch.setenv("PATH", str(executable.parent))
    monkeypatch.setenv("NYANYA_CODEX_CLI", str(executable.parent / "missing"))
    assert codex_cli.resolve_codex_cli() is None


def test_non_executable_and_directory_rejected(monkeypatch, executable):
    monkeypatch.setenv("NYANYA_CODEX_CLI", str(executable))
    executable.chmod(0o644)
    assert codex_cli.resolve_codex_cli() is None
    monkeypatch.setenv("NYANYA_CODEX_CLI", str(executable.parent))
    assert codex_cli.resolve_codex_cli() is None


def test_broken_symlink_rejected(monkeypatch, tmp_path):
    path = tmp_path / "codex"
    path.symlink_to(tmp_path / "gone")
    monkeypatch.setenv("NYANYA_CODEX_CLI", str(path))
    assert codex_cli.resolve_codex_cli() is None


def test_resolved_binary_starts(monkeypatch, executable):
    monkeypatch.setenv("NYANYA_CODEX_CLI", str(executable))
    assert bridge_runtime.run_subprocess_cancellable(
        [codex_cli.resolve_codex_cli()], cwd=executable.parent, timeout=3
    ) == (0, "ok", "")


def test_missing_binary_fails_before_spawn(monkeypatch):
    monkeypatch.setenv("NYANYA_CODEX_ENABLED", "true")
    monkeypatch.setattr(bridge_runtime, "resolve_codex_cli", lambda: None)
    with pytest.raises(RuntimeError, match="NYANYA_CODEX_CLI"):
        bridge_runtime.run_codex_task("inspect")


@pytest.mark.parametrize("number", [errno.ENOENT, errno.EACCES, errno.EPERM, errno.ENOEXEC, errno.EMFILE])
def test_spawn_error_is_sanitized(monkeypatch, tmp_path, number):
    monkeypatch.setenv("NYANYA_CODEX_ENABLED", "true")
    monkeypatch.setattr(bridge_runtime, "resolve_codex_cli", lambda: "/private/example/codex")
    monkeypatch.setattr(bridge_runtime, "is_allowed_workspace_path", lambda _: True)
    monkeypatch.setattr(bridge_runtime, "workspace_roots", lambda: [tmp_path])
    monkeypatch.setattr(bridge_runtime, "protected_delete_violation", lambda *a, **k: None)
    monkeypatch.setattr(bridge_runtime, "classify_request_risk", lambda *a, **k: {
        "severity": "low", "requires_approval": False, "approval_granted": False,
        "reasons": [], "stop": False,
    })
    def fail(*args, **kwargs):
        raise OSError(number, "private detail", "/private/example/codex")
    monkeypatch.setattr(bridge_runtime, "run_subprocess_cancellable", fail)
    with pytest.raises(RuntimeError) as caught:
        bridge_runtime.run_codex_task("inspect", workdir=tmp_path)
    assert f"errno={number}" in str(caught.value)
    assert "/private/" not in str(caught.value)
    assert "private detail" not in str(caught.value)


def test_manager_uses_same_resolution(monkeypatch, executable):
    from nyanya_agent import manager
    monkeypatch.setattr(manager, "load_env", lambda: None)
    monkeypatch.setenv("NYANYA_CODEX_CLI", str(executable))
    assert manager.configured_codex_cli() == codex_cli.resolve_codex_cli()
    monkeypatch.setenv("NYANYA_CODEX_CLI", str(Path(executable).with_name("missing")))
    assert manager.configured_codex_cli() is None


@pytest.mark.parametrize("enabled,expected", [("true", 1), ("false", 0)])
def test_preflight_checks_enabled_codex(monkeypatch, enabled, expected):
    import subprocess
    from nyanya_agent import manager
    monkeypatch.setattr(manager, "load_env", lambda: None)
    monkeypatch.setenv("NYANYA_CODEX_ENABLED", enabled)
    monkeypatch.setattr(manager, "configured_codex_cli", lambda: None)
    monkeypatch.setattr(manager, "run", lambda *a, **k: subprocess.CompletedProcess([], 0, "", ""))
    assert manager.check_config(include_backend=False) == expected
