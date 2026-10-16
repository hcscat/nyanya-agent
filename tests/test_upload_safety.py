"""Validate the exact descriptor supplied to upload; no Discord network access."""

import os

import pytest

from nyanya_agent.context_security import open_upload_file
from nyanya_agent.task_outcomes import SafeOperationError
from nyanya_agent.workspace_paths import scoped_path


def test_file_replaced_with_symlink_after_preflight_is_rejected(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    upload = root / "upload.txt"
    upload.write_text("allowed")
    outside = tmp_path / "outside.txt"
    outside.write_text("synthetic-private-value")
    assert scoped_path(root, "upload.txt").is_file()
    upload.unlink()
    upload.symlink_to(outside)
    with pytest.raises(OSError):
        with open_upload_file(root, "upload.txt"):
            pytest.fail("Unsafe descriptor supplied to sender")


def test_parent_directory_replaced_with_symlink_is_rejected(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    folder = root / "folder"
    folder.mkdir()
    (folder / "upload.txt").write_text("allowed")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "upload.txt").write_text("synthetic-private-value")
    assert scoped_path(root, "folder/upload.txt").is_file()
    folder.rename(root / "saved")
    folder.symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        with open_upload_file(root, "folder/upload.txt"):
            pytest.fail("Unsafe descriptor supplied to sender")


def test_sender_reads_validated_inode_even_if_path_is_replaced(tmp_path):
    upload = tmp_path / "upload.txt"
    upload.write_text("allowed")
    with open_upload_file(tmp_path, "upload.txt") as stream:
        upload.unlink()
        upload.write_text("replacement")
        assert stream.read() == b"allowed"
    assert stream.closed


@pytest.mark.parametrize("kind", ["hardlink", "fifo", "directory", "outside"])
def test_upload_rejects_non_regular_or_outside_paths(tmp_path, kind):
    root = tmp_path / "workspace"
    root.mkdir()
    upload = root / "upload.txt"
    target = tmp_path / "target"
    target.write_text("synthetic-private-value")
    if kind == "hardlink":
        os.link(target, upload)
    elif kind == "fifo":
        os.mkfifo(upload)
    elif kind == "directory":
        upload.mkdir()
    else:
        upload = target
    with pytest.raises(SafeOperationError):
        with open_upload_file(root, str(upload)):
            pytest.fail("Unsafe descriptor supplied to sender")
