"""Isolation and command-boundary tests for scripts/dev.py."""

from __future__ import annotations

import json
from pathlib import Path
import stat

import pytest

from nyanya_agent.distribution_copy import copy_distribution, is_private_distribution_path
from scripts import dev


def _fake_source(tmp_path: Path, *, venv: bool = True) -> Path:
    root = tmp_path / "source"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "scripts").mkdir()
    if venv:
        python = root / ".venv" / "bin" / "python"
        python.parent.mkdir(parents=True)
        python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        python.chmod(python.stat().st_mode | stat.S_IXUSR)
    return root


def test_environment_scrubs_inherited_runtime_settings(monkeypatch, tmp_path):
    root = _fake_source(tmp_path)
    monkeypatch.setenv("HOME", "/operator/home")
    monkeypatch.setenv("NYANYA_HOME", "/production/state")
    monkeypatch.setenv("NYANYA_DASHBOARD_PORT", "8765")
    monkeypatch.setenv("NYANYA_PROVIDER", "production-provider")
    monkeypatch.setenv("PYTHONHOME", "/production/python")
    monkeypatch.setenv("PYTHONPATH", "/production/modules")
    monkeypatch.setenv("VIRTUAL_ENV", "/production/venv")
    for key in dev._REMOVED_CREDENTIAL_KEYS:
        monkeypatch.setenv(key, "operator-secret")

    environment = dev.isolated_environment(dev.layout(root))

    assert not any(key.startswith("NYANYA_") for key in environment if key not in {
        "NYANYA_PROJECT_ROOT", "NYANYA_HOME", "NYANYA_ENV_FILE", "NYANYA_SERVICE_LABEL_PREFIX",
        "NYANYA_DASHBOARD_HOST", "NYANYA_DASHBOARD_PORT", "NYANYA_DASHBOARD_DB_PATH", "NYANYA_SESSIONS_DIR",
    })
    assert environment["NYANYA_PROJECT_ROOT"] == str(root)
    assert environment["NYANYA_HOME"] == str(root / ".dev-state")
    assert environment["NYANYA_ENV_FILE"] == str(root / ".dev-state" / ".env")
    assert environment["NYANYA_SERVICE_LABEL_PREFIX"] == dev.DEV_SERVICE_PREFIX
    assert environment["NYANYA_DASHBOARD_HOST"] == "127.0.0.1"
    assert environment["NYANYA_DASHBOARD_PORT"] == "8875"
    assert environment["HOME"] == "/operator/home"
    assert environment["PYTHONPATH"] == str(root / "src")
    assert environment["PYTHONNOUSERSITE"] == "1"
    for key in ("PYTHONHOME", "VIRTUAL_ENV"):
        assert key not in environment
    for key in dev._REMOVED_CREDENTIAL_KEYS:
        assert key not in environment


def test_paths_report_is_json_safe_and_does_not_create_state(tmp_path, capsys):
    root = _fake_source(tmp_path, venv=False)

    assert dev.run_command("paths", project_root=root) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["project_root"] == str(root)
    assert payload["state_exists"] is False
    assert payload["venv_exists"] is False
    assert not (root / ".dev-state").exists()


def test_unknown_commands_and_service_controls_are_rejected(tmp_path):
    root = _fake_source(tmp_path)

    with pytest.raises(dev.DevLauncherError, match="unsupported"):
        dev.run_command("service", project_root=root)
    with pytest.raises(dev.DevLauncherError, match="unsupported"):
        dev.command_argv("setup")


def test_symlinked_state_root_is_rejected_before_execution(tmp_path):
    root = _fake_source(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / ".dev-state").symlink_to(outside, target_is_directory=True)

    with pytest.raises(dev.DevLauncherError, match="must not be a symlink"):
        dev.run_command("paths", project_root=root)


def test_fixed_command_vectors_and_cwd_are_isolated(tmp_path):
    root = _fake_source(tmp_path)
    captured: dict[str, object] = {}

    def fake_executor(argv, *, cwd, env):
        captured.update(argv=list(argv), cwd=cwd, env=dict(env))
        return 7

    result = dev.run_command("test", project_root=root, executor=fake_executor)

    assert result == 7
    assert captured["argv"] == [str(root / ".venv" / "bin" / "python"), "-m", "pytest", "tests/"]
    assert captured["cwd"] == root
    assert captured["env"]["NYANYA_HOME"] == str(root / ".dev-state")
    assert not (root / ".dev-state").exists()


def test_runtime_state_is_created_lazily_for_dashboard_only(tmp_path):
    root = _fake_source(tmp_path)

    def fake_executor(argv, *, cwd, env):
        return 0

    assert dev.run_command("lint", project_root=root, executor=fake_executor) == 0
    assert not (root / ".dev-state").exists()
    assert dev.run_command("dashboard", project_root=root, executor=fake_executor) == 0
    assert (root / ".dev-state" / "data").is_dir()
    assert (root / ".dev-state" / "sessions").is_dir()


def test_missing_venv_fails_without_install_or_executor(tmp_path):
    root = _fake_source(tmp_path, venv=False)
    called = False

    def fake_executor(argv, *, cwd, env):
        nonlocal called
        called = True
        return 0

    with pytest.raises(dev.DevLauncherError, match=r"local \.venv is required"):
        dev.run_command("test", project_root=root, executor=fake_executor)
    assert called is False
    assert not (root / ".dev-state").exists()


@pytest.mark.parametrize("private_path", (".dev-state/cache.json", "nested/.dev-state/cache.json"))
def test_dev_state_manifest_is_rejected_before_copy(tmp_path, private_path):
    source, target = tmp_path / "source", tmp_path / "install"
    source.mkdir()
    (source / "package.json").write_text(json.dumps({"files": [private_path]}), encoding="utf-8")
    private = source / private_path
    private.parent.mkdir(parents=True)
    private.write_text("private fixture", encoding="utf-8")

    assert is_private_distribution_path(private_path)
    with pytest.raises(ValueError, match="Private state"):
        copy_distribution(source, target)
    assert not target.exists()
