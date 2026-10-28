"""Synthetic, isolated checks for managed service logs."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tarfile
import time

import pytest

from nyanya_agent import service_logs


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    root = tmp_path / "state"
    root.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NYANYA_HOME", str(root))
    monkeypatch.setenv("NYANYA_PROJECT_ROOT", str(tmp_path / "code"))
    monkeypatch.setenv("NYANYA_ENV_FILE", str(root / ".env"))
    monkeypatch.setenv("NYANYA_DASHBOARD_DB_PATH", str(root / "data" / "test.db"))
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[1] / "src"))


def _closed(log_dir, name, when, content):
    stamp = when.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = log_dir / f"discord.stdout.{stamp}.{name:0>32}.log"
    path.write_bytes(content)
    path.chmod(0o600)
    return path


def test_run_rolls_unbroken_output_and_preserves_exit(tmp_path):
    logs = tmp_path / "logs"
    rc = service_logs.run_service(
        logs, "discord", [sys.executable, "-c", "import sys;sys.stdout.buffer.write(b'x'*19);sys.exit(7)"],
        segment_bytes=7, raw_limit_bytes=1000,
    )
    assert rc == 7
    segments = list(logs.glob("discord.stdout.*.log"))
    assert sorted(path.stat().st_size for path in segments) == [5, 7, 7]
    assert b"".join(path.read_bytes() for path in segments) == b"x" * 19
    assert not (logs / "discord.stdout.current").exists()
    assert json.loads((logs / "discord.last-status.json").read_text())["exit_code"] == 7
    assert logs.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in segments)


def test_run_raw_limit_stops_service_without_deleting_evidence(tmp_path):
    logs = tmp_path / "logs"
    rc = service_logs.run_service(
        logs, "dashboard", [sys.executable, "-c", "import sys,time;sys.stdout.buffer.write(b'x'*30000);sys.stdout.flush();time.sleep(5)"],
        segment_bytes=8192, raw_limit_bytes=20000,
    )
    assert rc == 75
    assert sum(path.stat().st_size for path in logs.glob("dashboard.stdout.*.log")) >= 20000
    assert b"Raw log limit reached" in b"".join(path.read_bytes() for path in logs.glob("dashboard.stderr.*.log"))
    assert json.loads((logs / "dashboard.last-status.json").read_text())["exit_code"] == 75


@pytest.mark.parametrize("phase", ["startup", "rescan"])
def test_concurrent_retirement_does_not_interrupt_service(tmp_path, monkeypatch, phase):
    logs = tmp_path / "logs"
    logs.mkdir(mode=0o700)
    segment = logs / ("discord.stdout.20260101T000000000000Z." + "a" * 32 + ".log")
    segment.write_bytes(b"x" * 63)
    segment.chmod(0o600)
    original = service_logs._safe_file
    scans = 0

    def retire_before_stat(path, **kwargs):
        nonlocal scans
        if path == segment:
            scans += 1
            if scans == (1 if phase == "startup" else 2):
                path.unlink()  # Maintenance retired a closed segment already yielded by iterdir.
        return original(path, **kwargs)

    monkeypatch.setattr(service_logs, "_safe_file", retire_before_stat)
    result = service_logs.run_service(
        logs, "discord", [sys.executable, "-c", "import sys;sys.stdout.write('y');sys.exit(7)"],
        segment_bytes=16, raw_limit_bytes=64,
    )
    assert result == 7 and not segment.exists()
    assert b"".join(path.read_bytes() for path in logs.glob("discord.stdout.*.log")) == b"y"
    assert json.loads((logs / "discord.last-status.json").read_text())["error_class"] == ""


def test_raw_accounting_does_not_ignore_missing_current_file(tmp_path, monkeypatch):
    current = tmp_path / "discord.stdout.current"
    monkeypatch.setattr(Path, "iterdir", lambda _: iter([current]))
    with pytest.raises(FileNotFoundError):
        service_logs._raw_bytes(tmp_path, "discord")


@pytest.mark.parametrize("unsafe", ["permissions", "symlink"])
def test_raw_accounting_keeps_unsafe_closed_segments_blocked(tmp_path, unsafe):
    segment = tmp_path / ("discord.stdout.20260101T000000000000Z." + "b" * 32 + ".log")
    if unsafe == "symlink":
        segment.symlink_to(tmp_path / "absent")
    else:
        segment.write_bytes(b"x")
        segment.chmod(0o644)
    with pytest.raises(ValueError):
        service_logs._raw_bytes(tmp_path, "discord")


def test_wrapper_forwards_signal_and_reaps_child(tmp_path):
    logs = tmp_path / "logs"
    env = os.environ.copy()
    process = subprocess.Popen(
        [sys.executable, "-m", "nyanya_agent.service_logs", "run", "--log-dir", str(logs), "--name", "memory-worker", "--",
         sys.executable, "-c", "import time;print('started',flush=True);time.sleep(30)"],
        cwd=tmp_path, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            if (logs / "memory-worker.stdout.current").exists() and (logs / "memory-worker.stdout.current").stat().st_size:
                break
            time.sleep(0.05)
        else:
            pytest.fail("wrapper did not start child output")
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=8) == 143
        assert b"started" in b"".join(path.read_bytes() for path in logs.glob("memory-worker.stdout.*.log"))
        assert json.loads((logs / "memory-worker.last-status.json").read_text())["exit_code"] == 143
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_exited_leader_cannot_leave_inherited_pipe_open(tmp_path):
    logs = tmp_path / "logs"
    program = (
        "import subprocess,sys;"
        "subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);"
        "print('leader exited',flush=True)"
    )
    started = time.monotonic()
    rc = service_logs.run_service(logs, "discord", [sys.executable, "-c", program])
    assert rc == 0
    assert time.monotonic() - started < 5
    assert b"leader exited" in b"".join(path.read_bytes() for path in logs.glob("discord.stdout.*.log"))


def test_same_service_wrapper_refuses_concurrent_writer(tmp_path):
    logs = tmp_path / "logs"
    process = subprocess.Popen(
        [sys.executable, "-m", "nyanya_agent.service_logs", "run", "--log-dir", str(logs), "--name", "discord", "--",
         sys.executable, "-c", "import time;print('started',flush=True);time.sleep(30)"],
        cwd=tmp_path, env=os.environ.copy(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            if (logs / "discord.stdout.current").exists() and (logs / "discord.stdout.current").stat().st_size:
                break
            time.sleep(0.05)
        else:
            pytest.fail("first wrapper did not start")
        with pytest.raises(BlockingIOError):
            service_logs.run_service(logs, "discord", [sys.executable, "-c", "print('other')"])
        assert process.poll() is None
    finally:
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=8)


def test_missing_log_directory_is_reported_without_creation(tmp_path):
    logs = tmp_path / "missing"
    result = service_logs.maintain_service_logs(logs, tmp_path / "archives", apply=True)
    assert result["status"] == "absent"
    assert result["deleted_files"] == 0
    assert not logs.exists()


def test_interrupted_close_with_two_links_recovers_without_copying(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    current = logs / "discord.stdout.current"
    current.write_bytes(b"previous")
    current.chmod(0o600)
    closed = logs / f"discord.stdout.20260901T000000000000Z.{'a' * 32}.log"
    os.link(current, closed)
    assert current.stat().st_nlink == 2
    assert service_logs.run_service(logs, "discord", [sys.executable, "-c", "print('next')"]) == 0
    assert closed.read_bytes() == b"previous"
    assert not current.exists()


def test_monthly_archive_readback_and_retention(tmp_path):
    logs, archives = tmp_path / "logs", tmp_path / "archives"
    logs.mkdir()
    old = _closed(logs, "a", datetime(2026, 9, 1, tzinfo=timezone.utc), b"old")
    recent = _closed(logs, "b", datetime(2026, 9, 30, tzinfo=timezone.utc), b"recent")
    unrelated = logs / "discord.launchd.out.log"
    unrelated.write_text("legacy")
    now = datetime(2026, 10, 5, tzinfo=timezone.utc)
    planned = service_logs.maintain_service_logs(logs, archives, now=now)
    assert planned["dry_run"] is True
    assert old.exists() and recent.exists() and not archives.exists()
    applied = service_logs.maintain_service_logs(logs, archives, now=now, apply=True)
    assert applied["archives_create"] == ["service-logs-2026-09.tar.gz"]
    assert (applied["status"], applied["archived_files"], applied["deleted_files"]) == ("ok", 2, 1)
    assert not old.exists() and recent.exists() and unrelated.read_text() == "legacy"
    archive = archives / "service-logs-2026-09.tar.gz"
    assert service_logs._verify_archive(archive, "2026-09")
    with tarfile.open(archive, "r:gz") as content:
        assert content.extractfile(old.name).read() == b"old"
    assert archive.stat().st_mode & 0o777 == 0o600
    later = service_logs.maintain_service_logs(
        logs, archives, now=datetime(2027, 1, 5, tzinfo=timezone.utc), apply=True
    )
    assert recent.name in later["raw_expire"]
    assert archive.name in later["archives_expire"]
    assert not archive.exists() and not recent.exists()


def test_corrupt_archive_and_symlink_fail_closed(tmp_path):
    logs, archives = tmp_path / "logs", tmp_path / "archives"
    logs.mkdir()
    archives.mkdir()
    segment = _closed(logs, "c", datetime(2026, 9, 1, tzinfo=timezone.utc), b"preserve")
    archive = archives / "service-logs-2026-09.tar.gz"
    archive.write_bytes(b"not gzip")
    with pytest.raises(ValueError):
        service_logs.maintain_service_logs(logs, archives, now=datetime(2026, 10, 5, tzinfo=timezone.utc), apply=True)
    assert segment.exists()
    archive.unlink()
    other = tmp_path / "outside.log"
    other.write_text("untouched")
    (logs / f"discord.stdout.20260901T000000000000Z.{'d' * 32}.log").symlink_to(other)
    with pytest.raises(ValueError):
        service_logs.maintain_service_logs(logs, archives, now=datetime(2026, 10, 5, tzinfo=timezone.utc), apply=True)
    assert other.read_text() == "untouched"


def test_truncated_gzip_trailer_cannot_authorize_raw_removal(tmp_path):
    logs, archives = tmp_path / "logs", tmp_path / "archives"
    logs.mkdir()
    raw = _closed(logs, "e", datetime(2026, 9, 30, tzinfo=timezone.utc), b"retain")
    now = datetime(2026, 10, 5, tzinfo=timezone.utc)
    service_logs.maintain_service_logs(logs, archives, now=now, apply=True)
    archive = archives / "service-logs-2026-09.tar.gz"
    archive.write_bytes(archive.read_bytes()[:-8])
    with pytest.raises(ValueError):
        service_logs.maintain_service_logs(logs, archives, now=datetime(2026, 11, 5, tzinfo=timezone.utc), apply=True)
    assert raw.exists()


def test_archive_removal_before_prune_preserves_raw_and_pin(tmp_path, monkeypatch):
    logs, archives = tmp_path / "logs", tmp_path / "archives"
    logs.mkdir()
    raw = _closed(logs, "f", datetime(2026, 9, 1, tzinfo=timezone.utc), b"retain")
    archive = archives / "service-logs-2026-09.tar.gz"
    original = service_logs._linked_fingerprint
    calls = 0

    def remove_at_prune(path):
        nonlocal calls
        calls += 1
        if calls == 3:
            archive.unlink()
        return original(path)

    monkeypatch.setattr(service_logs, "_linked_fingerprint", remove_at_prune)
    with pytest.raises((ValueError, FileNotFoundError)):
        service_logs.maintain_service_logs(
            logs, archives, now=datetime(2026, 10, 5, tzinfo=timezone.utc), apply=True
        )
    assert raw.exists()
    pins = list(archives.glob(".service-logs-2026-09.tar.gz.*.pin"))
    assert len(pins) == 1
    assert service_logs._verify_archive(pins[0], "2026-09")


def test_archive_mutation_during_pin_cannot_authorize_raw_removal(tmp_path, monkeypatch):
    logs, archives = tmp_path / "logs", tmp_path / "archives"
    logs.mkdir()
    raw = _closed(logs, "a", datetime(2026, 9, 1, tzinfo=timezone.utc), b"retain")
    original_link = service_logs.os.link

    def corrupt_before_pin(source, target, **kwargs):
        if str(target).endswith(".pin"):
            Path(source).write_bytes(b"corrupt replacement")
        return original_link(source, target, **kwargs)

    monkeypatch.setattr(service_logs.os, "link", corrupt_before_pin)
    with pytest.raises(ValueError):
        service_logs.maintain_service_logs(
            logs, archives, now=datetime(2026, 10, 5, tzinfo=timezone.utc), apply=True
        )
    assert raw.exists()


def test_archive_mutation_after_pin_verification_preserves_raw(tmp_path, monkeypatch):
    logs, archives = tmp_path / "logs", tmp_path / "archives"
    logs.mkdir()
    raw = _closed(logs, "b", datetime(2026, 9, 1, tzinfo=timezone.utc), b"retain")
    original_verify = service_logs._verify_archive

    def mutate_after_verify(path, month, **kwargs):
        result = original_verify(path, month, **kwargs)
        if kwargs.get("allow_two_links"):
            Path(path).write_bytes(b"changed after verification")
        return result

    monkeypatch.setattr(service_logs, "_verify_archive", mutate_after_verify)
    with pytest.raises(ValueError):
        service_logs.maintain_service_logs(
            logs, archives, now=datetime(2026, 10, 5, tzinfo=timezone.utc), apply=True
        )
    assert raw.exists()
