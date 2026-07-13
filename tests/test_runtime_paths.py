from __future__ import annotations

import plistlib

from nyanya_agent import dashboard_store
from nyanya_agent import manager
from nyanya_agent import runtime_paths


def test_default_user_state_root_uses_macos_application_support(tmp_path):
    result = runtime_paths.default_user_state_root(platform="darwin", home=tmp_path, env={})

    assert result == tmp_path / "Library" / "Application Support" / "NyaNya Agent"


def test_resolve_state_root_preserves_legacy_source_env(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("NYANYA_PROVIDER=gemini_cli\n", encoding="utf-8")
    monkeypatch.delenv("NYANYA_HOME", raising=False)
    monkeypatch.delenv("NYANYA_ENV_FILE", raising=False)

    assert runtime_paths.resolve_state_root(tmp_path) == tmp_path.resolve(strict=False)


def test_resolve_state_root_honors_explicit_home(tmp_path, monkeypatch):
    code_root = tmp_path / "code"
    state_root = tmp_path / "state"
    code_root.mkdir()
    (code_root / ".env").write_text("legacy=true\n", encoding="utf-8")
    monkeypatch.setenv("NYANYA_HOME", str(state_root))

    assert runtime_paths.resolve_state_root(code_root) == state_root.resolve(strict=False)


def test_dashboard_relative_db_path_uses_state_root(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_store.nyanya, "STATE_ROOT", tmp_path)
    monkeypatch.setenv("NYANYA_DASHBOARD_DB_PATH", "data/dashboard.db")

    assert dashboard_store.resolve_db_path() == (tmp_path / "data" / "dashboard.db").resolve(strict=False)


def test_launchagent_uses_separate_code_and_state_paths(tmp_path, monkeypatch):
    code_root = tmp_path / "code"
    state_root = tmp_path / "state"
    launch_dir = tmp_path / "LaunchAgents"
    code_root.mkdir()
    (state_root / ".venv" / "bin").mkdir(parents=True)
    python = state_root / ".venv" / "bin" / "python"
    python.write_text("", encoding="utf-8")
    python.chmod(0o700)
    monkeypatch.setattr(manager, "project_root", lambda: code_root)
    monkeypatch.setattr(manager, "state_root", lambda: state_root)
    monkeypatch.setattr(manager, "launch_agents_dir", lambda: launch_dir)
    monkeypatch.setattr(manager.nyanya, "DEFAULT_ENV", state_root / ".env")

    plist_path = manager.write_dashboard_plist()
    with plist_path.open("rb") as stream:
        payload = plistlib.load(stream)

    assert payload["ProgramArguments"] == [str(python), "-m", "nyanya_agent.dashboard_api"]
    assert payload["EnvironmentVariables"]["NYANYA_PROJECT_ROOT"] == str(code_root)
    assert payload["EnvironmentVariables"]["NYANYA_HOME"] == str(state_root)
    assert payload["StandardOutPath"].startswith(str(state_root / "logs"))
