import json
import os
from pathlib import Path
import subprocess

import pytest

from nyanya_agent.distribution_copy import copy_distribution


def test_source_copy_uses_public_manifest_not_entire_checkout(tmp_path):
    source, target = tmp_path / "source", tmp_path / "install"
    source.mkdir()
    (source / "package.json").write_text(json.dumps({"files": ["public.txt"]}))
    (source / "public.txt").write_text("public")
    for name in ("sessions/private.json", "config/user_workspaces.json", "prompts/local_system.md", ".env.backup"):
        item = source / name
        item.parent.mkdir(parents=True, exist_ok=True)
        item.write_text("private fixture")
    copy_distribution(source, target)
    assert {item.name for item in target.iterdir()} == {"public.txt", "package.json"}


def test_source_copy_rejects_private_manifest_and_symlinks(tmp_path):
    source, target = tmp_path / "source", tmp_path / "install"
    source.mkdir()
    (source / ".env").write_text("private fixture")
    (source / "package.json").write_text(json.dumps({"files": [".env"]}))
    with pytest.raises(ValueError, match="Private"):
        copy_distribution(source, target)
    assert not target.exists()
    (source / "public").symlink_to(source / ".env")
    (source / "package.json").write_text(json.dumps({"files": ["public"]}))
    with pytest.raises(ValueError, match="Symlink"):
        copy_distribution(source, target)


@pytest.mark.skipif(os.name == "nt", reason="Bash source installer")
def test_clean_source_install_without_network_or_services(tmp_path):
    root = Path(__file__).resolve().parents[1]
    install = tmp_path / "code with spaces"
    state = tmp_path / "state with spaces"
    binary = tmp_path / "bin"
    completed = subprocess.run(
        ["bash", str(root / "packaging/install/install.sh"), "--source", str(root),
         "--install-dir", str(install), "--state-dir", str(state), "--bin-dir", str(binary), "--skip-deps"],
        capture_output=True, text=True, timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert not (install / "sessions").exists()
    assert not (install / "config/user_workspaces.json").exists()
    assert not (install / "prompts/local_system.md").exists()
    assert (state / ".env").is_file()
    help_result = subprocess.run([str(binary / "nyanya"), "--help"], capture_output=True, text=True, timeout=10)
    assert help_result.returncode == 0
    assert "Usage:" in help_result.stdout
