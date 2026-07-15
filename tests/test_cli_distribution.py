from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "dist" / "bin" / "nyanya.js"


def test_npm_manifest_includes_dashboard_assets():
    manifest = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))

    assert "src/nyanya_agent/dashboard_static/**/*" in manifest["files"]
    for name in ("index.html", "styles.css", "app.js"):
        assert (ROOT / "src" / "nyanya_agent" / "dashboard_static" / name).is_file()


def run_cli(state_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["NYANYA_HOME"] = str(state_root)
    env["NYANYA_PROJECT_ROOT"] = str(ROOT)
    env.pop("NYANYA_ENV_FILE", None)
    return subprocess.run(
        ["node", str(CLI), *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.skipif(not CLI.exists(), reason="run npm build before pytest")
def test_config_show_creates_separate_state(tmp_path):
    state_root = tmp_path / "state"

    result = run_cli(state_root, "config", "show")

    assert result.returncode == 0, result.stderr
    assert f"state_root={state_root}" in result.stdout
    assert "state_mode=user" in result.stdout
    assert (state_root / ".env").exists()
    assert (state_root / ".env").stat().st_mode & 0o077 == 0
    assert not (state_root / ".venv").exists()


@pytest.mark.skipif(not CLI.exists(), reason="run npm build before pytest")
def test_config_validate_rejects_invalid_port(tmp_path):
    state_root = tmp_path / "state"
    state_root.mkdir()
    (state_root / ".env").write_text("NYANYA_DASHBOARD_PORT=99999\n", encoding="utf-8")

    result = run_cli(state_root, "config", "validate")

    assert result.returncode == 1
    assert "NYANYA_DASHBOARD_PORT" in result.stderr
    assert "config_valid=false" in result.stdout


@pytest.mark.skipif(not CLI.exists(), reason="run npm build before pytest")
def test_update_command_preserves_user_state_policy(tmp_path):
    result = run_cli(tmp_path / "state", "update")

    assert result.returncode == 0
    assert "npm update -g @hcscat-dev/nyanya-agent" in result.stdout
    assert "NYANYA_HOME is preserved" in result.stdout


@pytest.mark.skipif(not CLI.exists(), reason="run npm build before pytest")
def test_state_backup_copies_only_durable_items(tmp_path):
    state_root = tmp_path / "state"
    backup_root = tmp_path / "backup"
    (state_root / "config").mkdir(parents=True)
    (state_root / "data").mkdir()
    (state_root / "logs").mkdir()
    (state_root / ".env").write_text("NYANYA_PROVIDER=gemini_cli\n", encoding="utf-8")
    (state_root / "config" / "user_workspaces.json").write_text("{}\n", encoding="utf-8")
    (state_root / "data" / "dashboard.db").write_bytes(b"db")
    (state_root / "logs" / "runtime.log").write_text("log\n", encoding="utf-8")

    result = run_cli(state_root, "state", "backup", f"--to={backup_root}")

    assert result.returncode == 0, result.stderr
    assert (backup_root / ".env").exists()
    assert (backup_root / "config" / "user_workspaces.json").exists()
    assert (backup_root / "data" / "dashboard.db").exists()
    assert not (backup_root / "logs").exists()


@pytest.mark.skipif(not CLI.exists(), reason="run npm build before pytest")
def test_state_migrate_excludes_venv_and_run(tmp_path):
    source = tmp_path / "legacy"
    target = tmp_path / "user-state"
    (source / "data").mkdir(parents=True)
    (source / "run").mkdir()
    (source / ".venv").mkdir()
    (source / ".env").write_text("NYANYA_PROVIDER=gemini_cli\n", encoding="utf-8")
    (source / "data" / "dashboard.db").write_bytes(b"db")
    (source / "run" / "worker.pid").write_text("1\n", encoding="utf-8")

    result = run_cli(source, "state", "migrate", f"--to={target}")

    assert result.returncode == 0, result.stderr
    assert (target / ".env").exists()
    assert (target / "data" / "dashboard.db").exists()
    assert not (target / "run").exists()
    assert not (target / ".venv").exists()
