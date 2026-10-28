"""Scheduling and CLI boundaries use synthetic state only."""

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from nyanya_agent import log_maintenance as maintenance


def test_help_and_status_never_initialize_missing_state(tmp_path):
    source = Path(__file__).resolve().parents[1]
    state = tmp_path / "unused-state"
    environment = {key: value for key, value in os.environ.items() if not key.startswith("NYANYA_")}
    environment.update({"NYANYA_HOME": str(state), "NYANYA_PROJECT_ROOT": str(source),
                        "NYANYA_ENV_FILE": str(tmp_path / "absent.env"),
                        "NYANYA_DASHBOARD_DB_PATH": str(state / "absent.db"),
                        "PYTHONPATH": str(source / "src"), "PYTHONNOUSERSITE": "1"})
    for arguments in (["--help"], ["status"]):
        result = subprocess.run([sys.executable, "-m", "nyanya_agent.log_maintenance", *arguments],
                                cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stderr
    assert not state.exists()


def test_database_setting_matches_explicit_state_and_environment(tmp_path, monkeypatch):
    environment = tmp_path / "local.env"
    environment.write_text('NYANYA_DASHBOARD_DB_PATH="data/custom database.db"\nUNRELATED_SECRET=private\n')
    monkeypatch.setenv("NYANYA_ENV_FILE", str(environment))
    monkeypatch.delenv("NYANYA_DASHBOARD_DB_PATH", raising=False)
    root, database = maintenance.configured_paths(tmp_path)
    assert root == tmp_path
    assert database == tmp_path / "data/custom database.db"
    monkeypatch.setenv("NYANYA_DASHBOARD_DB_PATH", "data/from-process.db")
    assert maintenance.configured_paths(tmp_path)[1] == tmp_path / "data/from-process.db"
    assert maintenance.configured_paths(tmp_path, "explicit.db")[1] == tmp_path / "explicit.db"
    assert os.getenv("UNRELATED_SECRET") is None


def test_status_cannot_enable_mutations(capsys):
    with pytest.raises(SystemExit) as raised:
        maintenance.main(["status", "--apply"])
    assert raised.value.code == 2
    assert "--apply requires maintain" in capsys.readouterr().err


def test_stale_database_override_cannot_cross_state_root(tmp_path, monkeypatch, capsys):
    state = tmp_path / "development"
    foreign = tmp_path / "operating.db"
    foreign.write_bytes(b"must remain untouched")
    before = foreign.read_bytes()
    monkeypatch.setenv("NYANYA_DASHBOARD_DB_PATH", str(foreign))
    assert maintenance.main(["maintain", "--apply", "--state-root", str(state)]) == 1
    assert json.loads(capsys.readouterr().out)["error_type"] == "DatabaseOutsideStateRoot"
    assert foreign.read_bytes() == before
    assert not state.exists()


@pytest.mark.skipif(os.name != "posix", reason="fixture interpreter uses a POSIX script")
def test_npm_log_command_does_not_forward_provider_credentials(tmp_path):
    source = Path(__file__).resolve().parents[1]
    cli = source / "dist/bin/nyanya.js"
    if not cli.exists():
        pytest.skip("npm build is required")
    python = tmp_path / "fixture-python"
    python.write_text(f"#!{sys.executable}\nimport json, os\n"
                      "print(json.dumps({'inherited': any(k in os.environ for k in "
                      "['OPENAI_API_KEY', 'NYANYA_DISCORD_BOT_TOKEN', 'GITHUB_TOKEN'])}))\n")
    python.chmod(0o700)
    state = tmp_path / "state"
    environment = dict(os.environ)
    environment.update(NYANYA_HOME=str(state), NYANYA_PROJECT_ROOT=str(source),
                       NYANYA_ENV_FILE=str(state / "absent.env"),
                       NYANYA_DASHBOARD_DB_PATH=str(state / "test.db"),
                       PYTHON=str(python))
    environment.update({key: "fixture-only" for key in (
        "OPENAI_API_KEY", "GITHUB_TOKEN", "NYANYA_DISCORD_BOT_TOKEN",
    )})
    result = subprocess.run(["node", str(cli), "logs", "status"], cwd=tmp_path, env=environment,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"inherited": False}
    assert not state.exists()


def test_summary_is_bounded_and_does_not_include_log_contents():
    report = {"status": "blocked", "audit": {"status": "blocked", "errors": ["private path or prompt"],
              "months": [{"month": "2020-01", "status": "conflict", "rows": [{"prompt": "private"}]}] * 50}}
    summary = maintenance.report_summary(report)
    assert len(summary["audit"]["months"]) == 24
    assert summary["audit"]["month_count"] == 50
    assert summary["audit"]["error_count"] == 1
    assert "private" not in json.dumps(summary)


def test_scheduler_cancellation_reaps_child_without_credentials(tmp_path, monkeypatch):
    class Process:
        returncode = None
        killed = False
        waited = False

        async def communicate(self):
            raise asyncio.CancelledError

        def kill(self):
            self.killed = True
            self.returncode = -9

        async def wait(self):
            self.waited = True
            return self.returncode

    process = Process()
    invocation = {}

    async def spawn(*args, **kwargs):
        invocation.update(kwargs)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setenv("NYANYA_DISCORD_BOT_TOKEN", "fixture-only-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "fixture-only-secret")
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(maintenance.scheduled_run(tmp_path, tmp_path / "ledger.db"))
    assert process.killed and process.waited
    assert "NYANYA_DISCORD_BOT_TOKEN" not in invocation["env"]
    assert "OPENAI_API_KEY" not in invocation["env"]
    assert invocation["env"]["NYANYA_DASHBOARD_DB_PATH"] == str(tmp_path / "ledger.db")
    assert invocation["cwd"] == tmp_path


def test_dashboard_exposes_authenticated_last_maintenance_result(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from nyanya_agent import dashboard_api

    monkeypatch.setenv("NYANYA_DASHBOARD_CONTROL_TOKEN", "fixture-local-token")
    monkeypatch.setenv("NYANYA_DASHBOARD_ALLOWED_HOSTS", "testserver")
    monkeypatch.setenv("NYANYA_LOG_MAINTENANCE_ENABLED", "true")
    monkeypatch.setattr(dashboard_api.core, "STATE_ROOT", tmp_path)
    seen = []

    async def background(root, database, *, publish):
        seen.append((root, database))
        publish({"status": "ok", "audit": {"deleted_rows": 0}})
        await asyncio.Event().wait()

    monkeypatch.setattr(maintenance, "maintenance_loop", background)
    database = tmp_path / "test.db"
    with TestClient(dashboard_api.create_app(database)) as client:
        assert client.get("/v1/log-maintenance").status_code == 401
        response = client.get("/v1/log-maintenance", headers={"X-Nyanya-Control-Token": "fixture-local-token"})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    assert seen == [(tmp_path, database)]
