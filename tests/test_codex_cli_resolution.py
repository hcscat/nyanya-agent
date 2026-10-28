import errno
from pathlib import Path

import pytest

from nyanya_agent import codex_cli, model_routing, process_runner
from nyanya_agent.task_outcomes import OutcomeSignal, outcome_from_error


LOCAL_INVOKE = model_routing.invoke


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
    assert process_runner.run_command(
        [codex_cli.resolve_codex_cli()], cwd=executable.parent, timeout=3
    ) == (0, "ok", "")


def test_missing_binary_fails_before_spawn(monkeypatch, tmp_path):
    monkeypatch.setattr(model_routing, "resolve_codex_cli", lambda: None)
    monkeypatch.setattr(process_runner, "run_command", lambda *a, **k: pytest.fail("spawned missing binary"))
    with pytest.raises(OutcomeSignal) as caught:
        LOCAL_INVOKE("luna", "Inspect a synthetic example", tmp_path, 3, None)
    assert caught.value.outcome.status == "blocked"
    assert "대체하지" in caught.value.outcome.text


@pytest.mark.parametrize("number", [errno.ENOENT, errno.EACCES, errno.EPERM, errno.ENOEXEC, errno.EMFILE])
def test_spawn_error_is_sanitized(monkeypatch, tmp_path, number):
    monkeypatch.setattr(model_routing, "resolve_codex_cli", lambda: "/synthetic/codex")

    def fail(*args, **kwargs):
        raise OSError(number, "private detail", "/private/example/codex")

    monkeypatch.setattr(process_runner, "run_command", fail)
    with pytest.raises(OSError) as caught:
        LOCAL_INVOKE("luna", "Inspect a synthetic example", tmp_path, 3, None)
    # Normal worker failure handling screens raw spawn errors before connector delivery.
    outcome = outcome_from_error(caught.value)
    assert outcome.status == "failed"
    assert "OSError" in outcome.text or type(caught.value).__name__ in outcome.text
    assert "/private/" not in outcome.text and "private detail" not in outcome.text


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
