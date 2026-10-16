"""Public manifests cannot override local-only installation boundaries."""

import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tarfile

import pytest

from nyanya_agent.distribution_copy import copy_distribution


ROOT = Path(__file__).resolve().parents[1]
CHECKS = runpy.run_path(str(ROOT / "packaging/release/package_checks.py"))
PRIVATE_PATHS = (
    "AGENTS.md", "nested/AGENTS.md", "nested/AGENTS.override.md",
    "node_modules/fixture.txt", "nested/node_modules/fixture.txt",
    ".env", ".env.production", "nested/.env.local", ".env.example.backup", ".env.EXAMPLE",
    "config/local.json", "config/nyanya.local.json", "config/credentials.dev.json",
    "config/secrets.json", "config/user_workspaces.json.backup", "config/private/settings.json",
    "nested/credentials/token.json", "nested/auth.json", "keys/operator.pem",
    "id_rsa", "nested/id_ed25519", "client.key", "certificate.p12", "certificate.pfx",
    "state.db", "state.db-wal", "state.db-shm", "state.sqlite", "state.sqlite3",
    "state.sqlite3-journal", "state.sqlite.backup", "state.db.tar.gz",
    "backups/archive.zip", "tmp/output.txt", "reports/review.html",
    "docs/reports/review.html", "docs/private/evidence.md",
    "docs/operational_rollout_20260913.md", "prompts/local_system.md", "prompts/local_policy.md",
)
PUBLIC_PATHS = (
    ".env.example", ".env.sample", "config/nyanya.json", "config/user_workspaces.example.json",
    "packaging/launchd/com.example.agent.plist.template",
    "src/nyanya_agent/dashboard_static/index.html", "src/nyanya_agent/database.py",
    "docs/architecture_and_roadmap.md",
)


def write_fixture(root, path, text="public fixture"):
    item = root / path
    item.parent.mkdir(parents=True, exist_ok=True)
    item.write_text(text, encoding="utf-8")


def fixture_git_env():
    env = os.environ.copy()
    for name in tuple(env):
        if name.startswith("GIT_"):
            env.pop(name)
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    return env


def fixture_git(root, *args):
    return subprocess.run(
        ["git", "-c", f"core.excludesFile={os.devnull}", *args],
        cwd=root,
        env=fixture_git_env(),
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )


@pytest.mark.parametrize("private_path", PRIVATE_PATHS)
def test_private_manifest_rejected_before_any_copy(tmp_path, private_path):
    source, target = tmp_path / "source", tmp_path / "install"
    write_fixture(source, "package.json", json.dumps({"files": ["public.txt", private_path]}))
    write_fixture(source, "public.txt")
    write_fixture(source, private_path, "private fixture")
    with pytest.raises(ValueError, match="Private state"):
        copy_distribution(source, target)
    assert not target.exists()


@pytest.mark.parametrize("private_path", PRIVATE_PATHS)
def test_package_audit_rejects_same_private_paths_without_reading_them(tmp_path, private_path):
    paths = CHECKS["REQUIRED_ASSETS"] | {private_path}
    for path in CHECKS["REQUIRED_ASSETS"]:
        write_fixture(tmp_path, path)
    assert CHECKS["package_errors"](tmp_path, paths) == [
        f"private/generated package path: {private_path}",
    ]


def test_required_public_templates_copy_and_pass_package_audit(tmp_path):
    source, target = tmp_path / "source", tmp_path / "install"
    paths = CHECKS["REQUIRED_ASSETS"] | set(PUBLIC_PATHS)
    write_fixture(source, "package.json", json.dumps({"files": sorted(paths)}))
    for path in paths:
        write_fixture(source, path)
    copy_distribution(source, target)
    copied = {path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()}
    assert copied == paths | {"package.json"}
    assert CHECKS["package_errors"](target, copied) == []


def test_package_checker_runs_standalone_without_pythonpath(tmp_path):
    # Isolated Python ignores user-site packages and PYTHONPATH.
    result = subprocess.run(
        [sys.executable, "-I", str(ROOT / "packaging/release/package_checks.py"), "privacy", str(tmp_path)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "personal-data-scan.txt").read_text() == ""
    assert (tmp_path / "secret-scan.txt").read_text() == ""


def test_fresh_git_fixture_ignores_root_and_nested_node_modules_without_global_ignore(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".gitignore").write_text((ROOT / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8")
    dependency_paths = (
        "node_modules/@types/node/process.d.ts",
        "nested/node_modules/example/index.js",
    )
    for path in dependency_paths:
        write_fixture(repo, path)

    fixture_git(repo, "init", "-q")
    (repo / ".git" / "info" / "exclude").write_text("", encoding="utf-8")
    fixture_git(repo, "add", ".gitignore")
    assert fixture_git(repo, "ls-files", "--others", "--exclude-standard").stdout == ""
    for path in dependency_paths:
        assert fixture_git(repo, "check-ignore", "-q", path).returncode == 0


@pytest.mark.parametrize(
    "dependency_path",
    ("node_modules/neutral-fixture.txt", "nested/node_modules/neutral-fixture.txt"),
)
def test_release_gate_rejects_forced_staged_node_modules(tmp_path, dependency_path):
    fixture = tmp_path / "release-fixture"
    fixture.mkdir()
    archive = subprocess.run(
        ["git", "archive", "HEAD"],
        cwd=ROOT,
        env=fixture_git_env(),
        capture_output=True,
        check=True,
        timeout=20,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
        bundle.extractall(fixture)
    for relative in (".gitignore", "packaging/release/package-denylist.txt"):
        (fixture / relative).write_text(
            (ROOT / relative).read_text(encoding="utf-8"), encoding="utf-8",
        )

    fixture_git(fixture, "init", "-q")
    (fixture / ".git" / "info" / "exclude").write_text("", encoding="utf-8")
    fixture_git(fixture, "add", "-A")
    write_fixture(fixture, dependency_path, "neutral dependency fixture")
    fixture_git(fixture, "add", "-f", dependency_path)

    env = fixture_git_env()
    isolated_home = tmp_path / "home"
    isolated_home.mkdir()
    env.update(
        {
            "HOME": str(isolated_home),
            "TMPDIR": str(tmp_path),
            "NPM_CONFIG_CACHE": str(tmp_path / "npm-cache"),
            "NPM_CONFIG_USERCONFIG": str(tmp_path / "npmrc"),
            "NYANYA_HOME": str(tmp_path / "state"),
            "NYANYA_ENV_FILE": str(tmp_path / ".env"),
        },
    )
    result = subprocess.run(
        ["bash", "packaging/release/verify_release.sh", "--skip-build"],
        cwd=fixture,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert dependency_path in output
    assert "denylisted path is tracked by git" in output


def test_project_ignore_keeps_all_local_instructions_private(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / '.gitignore').write_text((ROOT / '.gitignore').read_text())
    fixture_git(repo, 'init', '-q')
    for path in ('AGENTS.md', 'nested/AGENTS.md', 'AGENTS.override.md', 'nested/AGENTS.override.md'):
        write_fixture(repo, path)
    public = set(fixture_git(repo, 'ls-files', '--others', '--exclude-standard').stdout.splitlines())
    assert public == {'.gitignore'}
    assert CHECKS['is_private_distribution_path']('AGENTS.md')
