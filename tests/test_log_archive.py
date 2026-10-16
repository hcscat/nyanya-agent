"""Synthetic SQLite and filesystem checks; no application store initialization."""

from datetime import datetime, timedelta
import gzip
import hashlib
import json
import os
import sqlite3

import pytest

from nyanya_agent import log_archive as archive


NOW = datetime(2026, 10, 5, 12, tzinfo=archive.KST)


@pytest.fixture
def state(tmp_path):
    root = tmp_path.resolve()
    db = root / "ledger.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE audit_logs (id TEXT PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, detail_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL)")
        conn.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, state TEXT)")
        conn.execute("INSERT INTO tasks VALUES ('held-task', 'needs_review')")
    return db, root / "logs" / "archive" / "audit"


def add(db, identifier="old", *, date="2026-05-01T00:00:00+09:00", action="host.registered", entity="host", detail="{}"):
    row = dict(zip(archive.COLUMNS, (identifier, "fixture", action, entity, "fixture-entity", detail, date)))
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?, ?, ?)", tuple(row.values()))
    return row


def records(db):
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute("SELECT * FROM audit_logs ORDER BY id")]


def run(state, **kwargs):
    return archive.run_archive(db_path=state[0], archive_dir=state[1], now=kwargs.pop("now", NOW), **kwargs)


def test_dry_run_is_read_only_and_apply_roundtrip(state):
    db, directory = state
    old = add(db, detail=json.dumps({"text": "한글\nembedded newline"}))
    add(db, "held", action="task.interrupted", entity="task")
    before = db.read_bytes()
    result = run(state)
    assert result["mode"] == "dry-run"
    assert result["months"][0]["prunable"] == 1
    assert not directory.parent.parent.exists()
    assert db.read_bytes() == before

    result = run(state, apply=True)
    assert result["status"] == "ok"
    assert result["deleted_rows"] == 1
    assert result["pinned_rows"] == 1
    target = directory / "audit-2026-05.jsonl.gz"
    assert target.stat().st_mode & 0o777 == 0o600
    assert directory.stat().st_mode & 0o777 == 0o700
    with gzip.open(target, "rb") as stream:
        manifest, *encoded = stream.readlines()
    metadata = json.loads(manifest)
    assert metadata["count"] == 2
    assert metadata["sha256"] == hashlib.sha256(b"".join(encoded)).hexdigest()
    assert old in [json.loads(line) for line in encoded]
    assert [row["id"] for row in records(db)] == ["held"]
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT * FROM tasks").fetchall() == [("held-task", "needs_review")]
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0


def test_kst_month_boundary_and_90_day_boundary(state):
    add(state[0], "september", date="2026-09-30T14:59:59+00:00")
    add(state[0], "october", date="2026-09-30T15:00:00+00:00")
    add(state[0], "exact-cutoff", date=(NOW - timedelta(days=90)).isoformat())
    add(state[0], "older-cutoff", date=(NOW - timedelta(days=90, seconds=1)).isoformat())
    result = run(state, apply=True)
    assert {item["month"] for item in result["months"]} == {"2026-07", "2026-09"}
    assert result["deleted_rows"] == 1
    assert {row["id"] for row in records(state[0])} == {"september", "october", "exact-cutoff"}


@pytest.mark.parametrize("action,entity", [("task.completed", "task"), ("task.interrupted", "task"), ("approval.granted", "approval"), ("host.registered", "task"), ("unknown", "host")])
def test_only_allowlisted_housekeeping_is_pruned(state, action, entity):
    row = add(state[0], action=action, entity=entity)
    assert run(state, apply=True)["deleted_rows"] == 0
    assert records(state[0]) == [row]


@pytest.mark.parametrize("corruption", [b"not gzip", b"\x1f\x8b\x08\x00"])
def test_corrupt_archive_never_deletes_or_overwrites(state, corruption):
    add(state[0], date="2026-09-01T00:00:00+09:00")
    run(state, apply=True)
    target = state[1] / "audit-2026-09.jsonl.gz"
    target.write_bytes(corruption)
    result = run(state, now=datetime(2027, 1, 5, tzinfo=archive.KST), apply=True)
    assert result["status"] == "blocked"
    assert result["deleted_rows"] == 0
    assert len(records(state[0])) == 1
    assert target.read_bytes() == corruption


def test_valid_gzip_with_wrong_hash_never_deletes(state):
    add(state[0], date="2026-09-01T00:00:00+09:00")
    run(state, apply=True)
    target = state[1] / "audit-2026-09.jsonl.gz"
    with gzip.open(target, "rb") as stream:
        lines = stream.readlines()
    manifest = json.loads(lines[0])
    manifest["sha256"] = "0" * 64
    with gzip.open(target, "wb") as stream:
        stream.write(archive._line(manifest) + b"".join(lines[1:]))
    assert run(state, now=datetime(2027, 1, 5, tzinfo=archive.KST), apply=True)["deleted_rows"] == 0
    assert len(records(state[0])) == 1


def test_rerun_after_pruning_and_restart_after_publication(state, monkeypatch):
    add(state[0])
    original = archive._prune

    def interrupted(*args, **kwargs):
        raise OSError("synthetic process interruption after durable publication")

    monkeypatch.setattr(archive, "_prune", interrupted)
    assert run(state, apply=True)["status"] == "blocked"
    target = state[1] / "audit-2026-05.jsonl.gz"
    before = target.read_bytes()
    assert len(records(state[0])) == 1
    monkeypatch.setattr(archive, "_prune", original)
    assert run(state, apply=True)["deleted_rows"] == 1
    assert run(state, apply=True)["deleted_rows"] == 0
    assert target.read_bytes() == before


def test_late_row_and_changed_row_conflicts_keep_all_remaining_evidence(state):
    add(state[0], "held", action="task.interrupted", entity="task")
    run(state, apply=True)
    target = state[1] / "audit-2026-05.jsonl.gz"
    before = target.read_bytes()
    add(state[0], "late")
    result = run(state, apply=True)
    assert result["status"] == "blocked"
    assert result["deleted_rows"] == 0
    assert len(records(state[0])) == 2
    assert target.read_bytes() == before
    with sqlite3.connect(state[0]) as conn:
        conn.execute("DELETE FROM audit_logs WHERE id = 'late'")
        conn.execute("UPDATE audit_logs SET detail_json = '{\"changed\":true}' WHERE id = 'held'")
    assert run(state, apply=True)["status"] == "blocked"
    assert target.read_bytes() == before


def test_unsafe_paths_and_permissions(state):
    db, directory = state
    add(db)
    link = db.parent / "alias"
    link.symlink_to(db.parent, target_is_directory=True)
    with pytest.raises(archive.ArchiveError):
        archive.run_archive(db_path=link / db.name, archive_dir=directory, now=NOW)
    directory.mkdir(parents=True, mode=0o755)
    directory.chmod(0o755)
    with pytest.raises(archive.ArchiveError, match="0700"):
        run(state, apply=True)
    directory.chmod(0o700)
    (directory / ".archive.lock").symlink_to(db)
    with pytest.raises(archive.ArchiveError):
        run(state, apply=True)
    assert len(records(db)) == 1


def test_failed_write_retains_database_and_existing_files(state, monkeypatch):
    add(state[0])

    def full(*args, **kwargs):
        raise OSError("synthetic disk full")

    monkeypatch.setattr(archive.gzip.GzipFile, "write", full)
    assert run(state, apply=True)["status"] == "blocked"
    assert len(records(state[0])) == 1
    assert not list(state[1].glob("*.gz"))


def test_retention_expires_only_housekeeping_archives(state):
    add(state[0], "expired", date="2025-09-01T00:00:00+09:00")
    pinned = add(state[0], "pinned", date="2025-08-01T00:00:00+09:00", action="task.interrupted", entity="task")
    add(state[0], "boundary", date="2025-10-01T00:00:00+09:00")
    result = run(state, apply=True)
    assert result["expired_archives"] == 1
    assert not (state[1] / "audit-2025-09.jsonl.gz").exists()
    assert (state[1] / "audit-2025-08.jsonl.gz").exists()
    assert (state[1] / "audit-2025-10.jsonl.gz").exists()
    assert records(state[0]) == [pinned]
    # Even if another component removes its SQLite copy, pinned archival evidence stays.
    with sqlite3.connect(state[0]) as conn:
        conn.execute("DELETE FROM audit_logs")
    rerun = run(state, apply=True)
    assert rerun["expired_archives"] == 0
    assert (state[1] / "audit-2025-08.jsonl.gz").exists()


def test_trigger_cannot_mutate_live_state(state):
    add(state[0])
    with sqlite3.connect(state[0]) as conn:
        conn.execute("CREATE TRIGGER malicious AFTER DELETE ON audit_logs BEGIN UPDATE tasks SET state='erased'; END")
    result = run(state, apply=True)
    assert result["status"] == "blocked"
    assert result["deleted_rows"] == 0
    assert len(records(state[0])) == 1
    with sqlite3.connect(state[0]) as conn:
        assert conn.execute("SELECT state FROM tasks").fetchone()[0] == "needs_review"


def test_bounded_pruning_and_resume(state, monkeypatch):
    monkeypatch.setattr(archive, "MAX_PRUNE_ROWS", 2)
    monkeypatch.setattr(archive, "DELETE_BATCH", 1)
    for index in range(3):
        add(state[0], str(index))
    result = run(state, apply=True)
    assert result["deleted_rows"] == 2
    assert result["months"][0]["remaining_prunable"] == 1
    assert run(state, apply=True)["deleted_rows"] == 1


def test_process_lock_blocks_competing_run(state):
    import fcntl

    add(state[0])
    state[1].mkdir(parents=True, mode=0o700)
    fd = os.open(state[1] / ".archive.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(archive.ArchiveError, match="holds the lock"):
            run(state, apply=True)
    finally:
        os.close(fd)
    assert len(records(state[0])) == 1


def test_scan_bounds_fail_before_creating_archive_directory(state, monkeypatch):
    add(state[0])
    monkeypatch.setattr(archive, "MAX_SCAN_ROWS", 0)
    with pytest.raises(archive.ArchiveError, match="bounded"):
        run(state, apply=True)
    assert not state[1].exists()


def test_changed_preimage_between_archive_and_delete_is_retained(state, monkeypatch):
    add(state[0])
    original = archive._prune

    def change_before_prune(*args, **kwargs):
        with sqlite3.connect(state[0]) as conn:
            conn.execute("UPDATE audit_logs SET detail_json = '{\"changed\":true}'")
        return original(*args, **kwargs)

    monkeypatch.setattr(archive, "_prune", change_before_prune)
    result = run(state, apply=True)
    assert result["status"] == "blocked"
    assert result["deleted_rows"] == 0
    assert records(state[0])[0]["detail_json"] == '{"changed":true}'


def test_partial_batch_failure_reports_committed_progress(state, monkeypatch):
    monkeypatch.setattr(archive, "DELETE_BATCH", 1)
    add(state[0], "a")
    add(state[0], "b")
    original = archive._assert_archive
    calls = 0

    def fail_second_batch(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise archive.ArchiveError("synthetic second batch interruption")
        return original(*args, **kwargs)

    monkeypatch.setattr(archive, "_assert_archive", fail_second_batch)
    result = run(state, apply=True)
    assert result["status"] == "blocked"
    assert result["deleted_rows"] == 1
    assert [row["id"] for row in records(state[0])] == ["b"]
    monkeypatch.setattr(archive, "_assert_archive", original)
    assert run(state, apply=True)["deleted_rows"] == 1


def test_archive_symlink_cannot_read_or_delete_outside_evidence(state):
    add(state[0])
    state[1].mkdir(parents=True, mode=0o700)
    outside = state[0].parent / "outside"
    outside.write_text("keep")
    (state[1] / "audit-2026-05.jsonl.gz").symlink_to(outside)
    assert run(state, apply=True)["status"] == "blocked"
    assert outside.read_text() == "keep"
    assert len(records(state[0])) == 1


def test_database_hardlink_is_rejected(state):
    add(state[0])
    os.link(state[0], state[0].parent / "db-copy")
    with pytest.raises(archive.ArchiveError, match="single-link"):
        run(state, apply=True)


def test_only_month_publication_is_never_overwritten(state, monkeypatch):
    add(state[0])
    original = archive._write_archive

    def competing_publication(directory, name, *args):
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory)
        os.write(fd, b"competing evidence")
        os.close(fd)
        return original(directory, name, *args)

    monkeypatch.setattr(archive, "_write_archive", competing_publication)
    assert run(state, apply=True)["status"] == "blocked"
    assert (state[1] / "audit-2026-05.jsonl.gz").read_bytes() == b"competing evidence"
    assert len(records(state[0])) == 1


def test_expired_archive_is_held_until_bounded_pruning_finishes(state, monkeypatch):
    monkeypatch.setattr(archive, "MAX_PRUNE_ROWS", 1)
    add(state[0], "a", date="2025-09-01T00:00:00+09:00")
    add(state[0], "b", date="2025-09-01T00:00:00+09:00")
    first = run(state, apply=True)
    target = state[1] / "audit-2025-09.jsonl.gz"
    assert first["expired_archives"] == 0
    assert first["months"][0]["retention"] == "held-pruning-pending"
    assert target.exists()
    second = run(state, apply=True)
    assert second["deleted_rows"] == 1
    assert second["expired_archives"] == 1
    assert not target.exists()


def test_restart_finishes_verified_atomic_publication_window(state):
    add(state[0], date="2026-09-01T00:00:00+09:00")
    run(state, apply=True)
    target = state[1] / "audit-2026-09.jsonl.gz"
    # Model a process killed between final hard-link creation and temporary unlink.
    temporary = state[1] / (".audit-" + "a" * 32 + ".tmp")
    os.link(target, temporary)
    assert target.stat().st_nlink == 2
    result = run(state, now=datetime(2027, 1, 5, tzinfo=archive.KST), apply=True)
    assert result["status"] == "ok"
    assert result["deleted_rows"] == 1
    assert target.stat().st_nlink == 1
    assert not temporary.exists()


def test_restart_keeps_corrupt_interrupted_publication(state):
    add(state[0])
    state[1].mkdir(parents=True, mode=0o700)
    target = state[1] / "audit-2026-05.jsonl.gz"
    target.write_bytes(b"corrupt evidence")
    target.chmod(0o600)
    temporary = state[1] / (".audit-" + "a" * 32 + ".tmp")
    os.link(target, temporary)
    assert run(state, apply=True)["status"] == "blocked"
    assert target.read_bytes() == b"corrupt evidence"
    assert temporary.exists()
    assert len(records(state[0])) == 1
