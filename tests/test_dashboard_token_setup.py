"""Installation token regressions; synthetic state only, no services or providers."""

import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

from nyanya_agent.dashboard_token import TOKEN, TOKEN_FILE, ensure_dashboard_token


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.delenv(TOKEN, raising=False)
    monkeypatch.delenv(TOKEN_FILE, raising=False)
    # macOS exposes the system temp directory through /var -> /private/var.
    return tmp_path.resolve()


def token_path(state):
    return state / "data/dashboard_control.token"


def assert_private(path):
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.stat().st_uid == os.getuid()
        return
    # A protected DACL grants only the well-known Owner Rights SID, not an
    # inherited Users/Everyone group. No real account identifiers are emitted.
    script = path.parent / "check-acl.ps1"
    script.write_text(
        "param([string]$TokenPath)\n"
        "$acl = Get-Acl -LiteralPath $TokenPath\n"
        "$rules = @($acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))\n"
        "if (-not $acl.AreAccessRulesProtected -or $rules.Count -ne 1) { exit 1 }\n"
        "if ($rules[0].IdentityReference.Value -ne 'S-1-3-4' -or $rules[0].IsInherited -or "
        "$rules[0].AccessControlType -ne 'Allow' -or $rules[0].FileSystemRights -ne 'FullControl') { exit 2 }\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(script), "-TokenPath", str(path)],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_fresh_token_is_private_unique_and_preserved(state):
    assert ensure_dashboard_token(state, state / ".env") == "created"
    path = token_path(state)
    original, inode = path.read_bytes(), path.stat().st_ino
    assert re.fullmatch(rb"[A-Za-z0-9_-]{43}\n", original)
    assert_private(path)
    assert ensure_dashboard_token(state, state / ".env") == "present"
    assert (path.read_bytes(), path.stat().st_ino) == (original, inode)
    other = state / "other"
    ensure_dashboard_token(other, other / ".env")
    assert token_path(other).read_bytes() != original


@pytest.mark.parametrize("process_value", [False, True])
def test_explicit_token_is_preserved_without_creating_file(state, monkeypatch, process_value):
    (state / ".env").write_text(f'{TOKEN}="synthetic-existing-token"\n')
    if process_value:
        monkeypatch.setenv(TOKEN, "synthetic-process-token")
    assert ensure_dashboard_token(state, state / ".env") == "configured"
    assert not token_path(state).exists()


@pytest.mark.parametrize("absolute", [False, True])
def test_configured_token_file_is_used_and_preserved(state, absolute):
    value = str(state / "custom/token") if absolute else "custom/token"
    (state / ".env").write_text(f'{TOKEN_FILE}="{value}"\n', encoding="utf-8")
    assert ensure_dashboard_token(state, state / ".env") == "created"
    path = state / "custom/token"
    before = path.read_bytes()
    assert not token_path(state).exists()
    assert ensure_dashboard_token(state, state / ".env") == "present"
    assert path.read_bytes() == before
    assert_private(path)


def test_env_precedence_matches_runtime_first_duplicate_wins(state, monkeypatch):
    (state / ".env").write_text(f"{TOKEN_FILE}=first/token\n{TOKEN_FILE}=second/token\n")
    ensure_dashboard_token(state, state / ".env")
    assert (state / "first/token").is_file()
    assert not (state / "second").exists()
    monkeypatch.setenv(TOKEN_FILE, "process/token")
    ensure_dashboard_token(state, state / ".env")
    assert (state / "process/token").is_file()


@pytest.mark.parametrize("content", [b"", b" \n", b"x" * 4097, b"\xff"])
def test_invalid_existing_token_is_not_rotated(state, content):
    path = token_path(state)
    path.parent.mkdir()
    path.write_bytes(content)
    path.chmod(0o600)
    with pytest.raises(ValueError):
        ensure_dashboard_token(state, state / ".env")
    assert path.read_bytes() == content


@pytest.mark.skipif(os.name == "nt", reason="POSIX modes and links")
@pytest.mark.parametrize("kind", ["symlink", "hardlink", "directory", "fifo", "permissions", "parent-link"])
def test_unsafe_existing_path_fails_without_replacement(state, kind):
    path = token_path(state)
    target = state / "existing"
    target.write_text("synthetic-existing-token")
    target.chmod(0o600)
    if kind == "parent-link":
        (state / "data").symlink_to(state / "other", target_is_directory=True)
    else:
        path.parent.mkdir()
        if kind == "symlink":
            path.symlink_to(target)
        elif kind == "hardlink":
            os.link(target, path)
        elif kind == "directory":
            path.mkdir()
        elif kind == "fifo":
            os.mkfifo(path)
        else:
            path.write_text("synthetic-existing-token")
            path.chmod(0o644)
    with pytest.raises((OSError, ValueError)):
        ensure_dashboard_token(state, state / ".env")
    assert target.read_text() == "synthetic-existing-token"
    assert not (state / "other").exists()


def test_command_never_prints_token_or_private_path_on_failure(state):
    command = [sys.executable, str(ROOT / "src/nyanya_agent/dashboard_token.py"),
               "--state-root", str(state), "--env-file", str(state / ".env")]
    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert result.stdout == "dashboard_token=created\n"
    assert token_path(state).read_text().strip() not in result.stdout + result.stderr
    token_path(state).write_bytes(b"\xff")
    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    assert str(state) not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr


def test_setup_all_provisions_before_service_admission_and_reuses_token(state):
    # Exercise the real compiled setup and token subprocess. Stub only doctor
    # and lifecycle/dependency side effects; never start an operational service.
    wrapper = r"""
const fs = require('fs'), path = require('path');
const root = process.argv[1];
const python = require(path.join(root, 'dist/runtime/python.js'));
python.findPython = () => ({command: process.env.TEST_PYTHON, major: 3, minor: 12, versionText: '3.12'});
python.satisfiesPython = () => true;
python.runPythonModule = () => {
  if (!fs.existsSync(path.join(process.env.NYANYA_HOME, 'data/dashboard_control.token'))) throw Error('missing token');
  return 0;
};
require(path.join(root, 'dist/commands/doctor.js')).doctor = () => 0;
const rc = require(path.join(root, 'dist/commands/setup.js')).setup(root, ['--all', '--skip-deps', '--non-interactive']);
process.exit(rc);
"""
    env = dict(os.environ, NYANYA_HOME=str(state), NYANYA_PROJECT_ROOT=str(ROOT),
               NYANYA_ENV_FILE=str(state / ".env"), TEST_PYTHON=sys.executable)
    command = ["node", "-e", wrapper, str(ROOT)]
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert "dashboard_token=created" in result.stdout
    path = token_path(state)
    assert_private(path)
    before = path.read_bytes()
    assert before.decode().strip() not in result.stdout + result.stderr
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert "dashboard_token=present" in result.stdout
    assert path.read_bytes() == before
    path.write_bytes(b"")
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 1
    assert path.read_bytes() == b""


def test_generated_token_unlocks_api_without_weakening_auth(state, monkeypatch):
    from fastapi.testclient import TestClient
    from nyanya_agent import core, dashboard_api

    monkeypatch.setattr(core, "STATE_ROOT", state)
    monkeypatch.setattr(core, "DEFAULT_ENV", state / ".env")
    app = dashboard_api.create_app(state / "isolated.db")
    client = TestClient(app, base_url="http://localhost")
    assert client.get("/v1/summary").status_code == 503
    ensure_dashboard_token(state, state / ".env")
    assert client.get("/v1/summary").status_code == 401
    assert client.get("/v1/summary", headers={"X-NyaNya-Control-Token": "incorrect"}).status_code == 401
    token = token_path(state).read_text().strip()
    assert client.get("/v1/summary", headers={"X-NyaNya-Control-Token": token}).status_code == 200
    assert client.get("/v1/summary", headers={"Host": "untrusted.invalid", "X-NyaNya-Control-Token": token}).status_code == 400
    assert client.get("/v1/summary", headers={"Origin": "https://untrusted.invalid", "X-NyaNya-Control-Token": token}).status_code == 403
    app.state.operations.close()


@pytest.mark.skipif(os.name != "nt", reason="Real Windows installer and ACL verification")
def test_windows_installer_provisions_private_token_and_preserves_it(state):
    command = ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(ROOT / "packaging/install/install.ps1"),
               "-Source", str(ROOT), "-InstallDir", str(state / "code with spaces"),
               "-StateDir", str(state / "state with spaces"), "-BinDir", str(state / "bin"), "-SkipDeps"]
    # Ensure the installer's `python` resolves to this test interpreter.
    env = dict(os.environ, PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"])
    path = token_path(state / "state with spaces")
    for expected in ("created", "present"):
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=120)
        assert result.returncode == 0, result.stderr
        assert f"dashboard_token={expected}" in result.stdout
        if expected == "created":
            before = path.read_bytes()
        assert path.read_bytes() == before
        assert before.decode().strip() not in result.stdout + result.stderr
        assert_private(path)
