"""OPS-DEPLOY-01 package completeness and explicit workspace trust regressions."""

import json
from pathlib import Path
import runpy

import pytest

from nyanya_agent import bridge_policy as policy
from nyanya_agent.distribution_copy import copy_distribution


ROOT = Path(__file__).resolve().parents[1]
CHECKS = runpy.run_path(str(ROOT / "packaging/release/package_checks.py"))


@pytest.mark.parametrize("configured", [None, "", "  ", ", ,", "/"])
def test_no_implicit_trust_preserves_registered_workspace_and_approval(monkeypatch, tmp_path, configured):
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(tmp_path))
    if configured is None:
        monkeypatch.delenv("NYANYA_TRUSTED_WORKSPACE_ROOTS", raising=False)
    else:
        monkeypatch.setenv("NYANYA_TRUSTED_WORKSPACE_ROOTS", configured)

    assert policy.trusted_workspace_roots() == []
    assert not policy.is_trusted_workspace_path(policy.nyanya.PROJECT_ROOT)
    assert policy.resolve_workspace_path(str(tmp_path)) == tmp_path.resolve()
    risk = policy.classify_request_risk("README.md 파일을 수정해줘", workdir=tmp_path)
    assert risk["workspace_tier"] == "extended"
    assert risk["requires_approval"] is True
    assert risk["approval_granted"] is False


def test_explicit_trust_never_grants_unregistered_access(monkeypatch, tmp_path):
    allowed, outside = tmp_path / "registered", tmp_path / "unregistered"
    allowed.mkdir()
    outside.mkdir()
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(allowed))
    monkeypatch.setenv("NYANYA_TRUSTED_WORKSPACE_ROOTS", f"{allowed}, {allowed}, /, {outside}")
    assert policy.trusted_workspace_roots() == [allowed.resolve(), outside.resolve()]
    assert policy.workspace_risk_tier(allowed) == "trusted"
    assert policy.workspace_risk_tier(outside) == "blocked"
    with pytest.raises(ValueError):
        policy.resolve_workspace_path(str(outside))
    shortcut = allowed / "shortcut"
    shortcut.symlink_to(outside, target_is_directory=True)
    assert policy.workspace_risk_tier(shortcut) == "blocked"
    with pytest.raises(ValueError):
        policy.resolve_workspace_path(str(shortcut))


def test_trust_alone_cannot_replace_workspace_registration(monkeypatch, tmp_path):
    monkeypatch.delenv("NYANYA_WORKSPACE_ROOTS", raising=False)
    monkeypatch.delenv("NYANYA_WORKSPACE_ROOT", raising=False)
    monkeypatch.setenv("NYANYA_TRUSTED_WORKSPACE_ROOTS", str(tmp_path))
    assert policy.workspace_risk_tier(tmp_path) == "blocked"
    with pytest.raises(ValueError, match="explicit workspace root"):
        policy.workspace_root()


def test_privacy_scan_detects_defaults_without_blacklisting_author_names():
    folder = "FIXTURE_ROOT"
    scan = CHECKS["scan_text"]
    examples = (
        f'roots = [pathlib.Path.home() / "{folder}"]',
        f'roots = [Path.home() / "{folder}"]',
        f"Trusted roots are normally `~/{folder}`.",
        f"사용법: set_home discord_user_id {folder}",
        f"사용법: /set_home telegram_user_id {folder}",
        f"set_home discord-user:discord_user_id {folder}",
    )
    for example in examples:
        assert scan(example) == {"personal"}
    for public in (
        f'authors = [{{ name = "{folder}" }}]',
        f"Copyright {folder}",
        "NYANYA_TRUSTED_WORKSPACE_ROOTS=/absolute/trusted/path",
        "set_home discord_user_id /absolute/workspace/path",
        "/set_home telegram_user_id <workspace>",
        'pathlib.Path.home() / "Library"',
    ):
        assert scan(public) == set()


def test_privacy_reports_keep_matching_values_out_of_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    folder = "FIXTURE_ROOT"
    value = f"~/{folder}"
    Path("public.md").write_text(value, encoding="utf-8")
    Path("binary.bin").write_bytes(b"\0" + value.encode())
    CHECKS["write_privacy_reports"](tmp_path, ["public.md", "binary.bin"])
    assert Path("personal-data-scan.txt").read_text() == "public.md\n"
    assert Path("secret-scan.txt").read_text() == ""


def test_manifest_requires_packaged_link_targets_even_if_they_exist_in_checkout(tmp_path):
    for asset in CHECKS["REQUIRED_ASSETS"]:
        path = tmp_path / asset
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
    (tmp_path / "guide.md").write_text("[source](test.py#L1) [web](https://example.com) [section](#usage)")
    (tmp_path / "test.py").write_text("# public test fixture")
    paths = CHECKS["REQUIRED_ASSETS"] | {"guide.md"}
    assert CHECKS["package_errors"](tmp_path, paths) == ["unpackaged relative link: guide.md:1"]
    assert CHECKS["package_errors"](tmp_path, paths | {"test.py"}) == []
    errors = CHECKS["package_errors"](tmp_path, (paths | {"test.py", "sessions/state.json"}) - {
        "scripts/mark_dist_executable.js",
    })
    assert "missing package asset: scripts/mark_dist_executable.js" in errors
    assert "private/generated package path: sessions/state.json" in errors


def test_public_distribution_has_build_helper_and_resolvable_documentation(tmp_path):
    target = tmp_path / "distribution"
    copy_distribution(ROOT, target)
    paths = {path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()}
    assert CHECKS["package_errors"](target, paths) == []
    assert "scripts/mark_dist_executable.js" in paths
    assert "docs/test_catalog_ko.md" in paths
    assert "tests/conftest.py" in paths
    manifest = json.loads((target / "package.json").read_text())
    assert not any(pattern in {"docs/", "docs/**", "docs/**/*"} for pattern in manifest["files"])
