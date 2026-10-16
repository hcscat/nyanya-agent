"""Bounded, opt-in monthly audit archives. These are not SQLite backups.

This module deliberately does not import application configuration or stores.
Only housekeeping audit rows may be pruned; workflow evidence remains pinned.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from typing import Any
import uuid


KST = timezone(timedelta(hours=9), "Asia/Seoul")
COLUMNS = ("id", "actor", "action", "entity_type", "entity_id", "detail_json", "created_at")
HOUSEKEEPING = frozenset({("host.registered", "host"), ("host.updated", "host"), ("memory.retrieved", "memory_item")})
MAX_ROWS = 100_000
MAX_SCAN_ROWS = 500_000
MAX_SCAN_BYTES = 128 * 1024 * 1024
MAX_BYTES = 64 * 1024 * 1024
MAX_LINE_BYTES = 1024 * 1024
MAX_ARCHIVES = 240
MAX_DIRECTORY_ENTRIES = 1024
DELETE_BATCH = 100
MAX_PRUNE_ROWS = 10_000
ARCHIVE_RE = re.compile(r"audit-(\d{4}-\d{2})\.jsonl\.gz\Z")
TEMP_RE = re.compile(r"\.audit-[0-9a-f]{32}\.tmp\Z")


class ArchiveError(ValueError):
    """Unsafe or unsupported input; no automatic repair is attempted."""


def _timestamp(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError("timezone required")
        return result.astimezone(KST)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ArchiveError("Audit timestamps must be valid timezone-aware ISO timestamps") from exc


def _line(value: Any) -> bytes:
    result = (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(result) > MAX_LINE_BYTES:
        raise ArchiveError("Audit record exceeds the archive line limit")
    return result


def _housekeeping(row: dict[str, str]) -> bool:
    return (row["action"], row["entity_type"]) in HOUSEKEEPING


def _month(row: dict[str, str]) -> str:
    return _timestamp(row["created_at"]).strftime("%Y-%m")


def _absolute(path: str | Path) -> Path:
    value = Path(path)
    if not value.is_absolute() or ".." in value.parts:
        raise ArchiveError("Use absolute paths without parent traversal")
    return value


@contextmanager
def _directory(path: Path, *, create: bool = False):
    """Walk directories through descriptors; never follow a symlink component."""
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ArchiveError("Archive maintenance requires POSIX no-follow file operations")
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, mode=0o700, dir_fd=fd)
                os.fsync(fd)
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def _regular(fd: int, *, private: bool = False, links: int = 1) -> os.stat_result:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != links:
        raise ArchiveError("Expected a single-link regular file")
    if private and (info.st_mode & 0o777 != 0o600 or info.st_uid != os.getuid()):
        raise ArchiveError("Archive and lock files must be owned by this user with mode 0600")
    return info


def _db_identity(path: Path) -> tuple[int, int]:
    with _directory(path.parent) as parent:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            info = _regular(fd)
        finally:
            os.close(fd)
        for suffix in ("-wal", "-shm", "-journal"):
            try:
                sidecar = os.stat(path.name + suffix, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(sidecar.st_mode) or sidecar.st_nlink != 1:
                raise ArchiveError("Unsafe SQLite sidecar path")
    return info.st_dev, info.st_ino


@contextmanager
def _connection(path: Path, *, apply: bool, identity: tuple[int, int]):
    if _db_identity(path) != identity:
        raise ArchiveError("Database file changed during maintenance")
    conn = sqlite3.connect(path.as_uri() + ("?mode=rw" if apply else "?mode=ro"), uri=True, timeout=2)
    conn.row_factory = sqlite3.Row
    try:
        if _db_identity(path) != identity:
            raise ArchiveError("Database file changed while opening it")
        conn.execute("PRAGMA foreign_keys=ON")
        if not apply:
            conn.execute("PRAGMA query_only=ON")
        # A trigger/cascade must not turn an audit deletion into a workflow write.
        def authorize(action, arg1, arg2, database, source):
            if action in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE):
                return sqlite3.SQLITE_OK if action == sqlite3.SQLITE_DELETE and arg1 == "audit_logs" and source is None else sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        conn.set_authorizer(authorize)
        yield conn
    finally:
        conn.close()


def _read_rows(conn: sqlite3.Connection) -> list[dict[str, str]]:
    schema = tuple(row["name"] for row in conn.execute("PRAGMA table_info(audit_logs)"))
    if schema != COLUMNS:
        raise ArchiveError("Unsupported audit_logs schema; no migration is performed")
    result = []
    size = 0
    for row in conn.execute("SELECT * FROM audit_logs ORDER BY id LIMIT ?", (MAX_SCAN_ROWS + 1,)):
        record = dict(row)
        if not all(isinstance(value, str) for value in record.values()):
            raise ArchiveError("Audit records must contain text fields")
        _month(record)
        size += len(_line(record))
        if len(result) >= MAX_SCAN_ROWS or size > MAX_SCAN_BYTES:
            raise ArchiveError("Audit scan exceeds the bounded maintenance limit; no pruning performed")
        result.append(record)
    return result


def _digest(rows: list[dict[str, str]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(_line(row))
    return digest.hexdigest()


def _read_archive(directory: int, name: str, source: str, *, links: int = 1) -> tuple[dict, list[dict[str, str]], tuple[int, ...]]:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
    try:
        info = _regular(fd, private=True, links=links)
        if info.st_size > MAX_BYTES:
            raise ArchiveError("Compressed archive exceeds size limit")
        with os.fdopen(fd, "rb", closefd=False) as raw, gzip.GzipFile(fileobj=raw, mode="rb") as stream:
            first = stream.readline(MAX_LINE_BYTES + 1)
            if len(first) > MAX_LINE_BYTES:
                raise ArchiveError("Oversized archive manifest")
            manifest = json.loads(first)
            expected = ARCHIVE_RE.fullmatch(name)
            if not isinstance(manifest, dict) or manifest.get("version") != 1 or manifest.get("format") != "nyanya-audit-jsonl" or manifest.get("columns") != list(COLUMNS) or manifest.get("source") != source or not expected or manifest.get("month") != expected[1] or manifest.get("timezone") != "Asia/Seoul":
                raise ArchiveError("Archive manifest does not match this database/month")
            result = []
            size = len(first)
            previous = None
            while True:
                encoded = stream.readline(MAX_LINE_BYTES + 1)
                if not encoded:
                    break
                size += len(encoded)
                if len(encoded) > MAX_LINE_BYTES or size > MAX_BYTES or len(result) >= MAX_ROWS:
                    raise ArchiveError("Archive decompression exceeds bounds")
                row = json.loads(encoded)
                if not isinstance(row, dict) or set(row) != set(COLUMNS) or not all(isinstance(value, str) for value in row.values()) or _month(row) != manifest["month"] or (previous is not None and row["id"] <= previous) or encoded != _line(row):
                    raise ArchiveError("Invalid archive row, order, or month")
                previous = row["id"]
                result.append(row)
            if manifest.get("count") != len(result) or manifest.get("sha256") != _digest(result):
                raise ArchiveError("Archive count/hash verification failed")
        return manifest, result, _fingerprint(info)
    except (OSError, EOFError, ValueError, TypeError) as exc:
        raise ArchiveError("Archive verification failed; existing evidence retained") from exc
    finally:
        os.close(fd)


def _write_archive(directory: int, name: str, source: str, month: str, rows: list[dict[str, str]], now: datetime) -> None:
    if len(rows) > MAX_ROWS:
        raise ArchiveError("Monthly archive exceeds the 100000-row bound; no pruning performed")
    temporary = ".audit-" + uuid.uuid4().hex + ".tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        manifest = {"version": 1, "format": "nyanya-audit-jsonl", "columns": list(COLUMNS), "source": source,
                    "month": month, "timezone": "Asia/Seoul", "created_at": now.isoformat(),
                    "count": len(rows), "sha256": _digest(rows)}
        if sum(len(_line(row)) for row in rows) + len(_line(manifest)) > MAX_BYTES:
            raise ArchiveError("Monthly archive exceeds size bound")
        with os.fdopen(fd, "wb", closefd=False) as raw:
            with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as stream:
                stream.write(_line(manifest))
                for row in rows:
                    stream.write(_line(row))
            raw.flush()
            os.fsync(fd)
        # Hard-link publication is atomic and refuses to replace an existing month.
        os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
        os.unlink(temporary, dir_fd=directory)
        os.fsync(directory)
    finally:
        os.close(fd)
        # An interrupted temporary file is harmless; never remove another run's file.
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass


def _names(directory: int) -> list[str]:
    result = []
    with os.scandir(directory) as entries:
        for entry in entries:
            if len(result) >= MAX_DIRECTORY_ENTRIES:
                raise ArchiveError("Archive directory exceeds the 1024-entry bound")
            result.append(entry.name)
    return result


def _recover_publication(directory: int, source: str) -> None:
    """Finish only the verified final-link/temporary-unlink interruption window."""
    names = _names(directory)
    temporary = {}
    for name in names:
        if TEMP_RE.fullmatch(name):
            info = os.stat(name, dir_fd=directory, follow_symlinks=False)
            if stat.S_ISREG(info.st_mode) and info.st_nlink == 2:
                temporary[(info.st_dev, info.st_ino)] = name
    for name in names:
        if not ARCHIVE_RE.fullmatch(name):
            continue
        info = os.stat(name, dir_fd=directory, follow_symlinks=False)
        candidate = temporary.get((info.st_dev, info.st_ino))
        if info.st_nlink != 2 or candidate is None:
            continue
        # Corrupt or unrelated evidence is never removed during recovery.
        try:
            _, _, identity = _read_archive(directory, name, source, links=2)
        except ArchiveError:
            continue
        current = os.stat(candidate, dir_fd=directory, follow_symlinks=False)
        if _fingerprint(current) != identity or current.st_nlink != 2:
            raise ArchiveError("Interrupted publication changed during recovery")
        os.unlink(candidate, dir_fd=directory)
        os.fsync(directory)


def _fingerprint(info: os.stat_result) -> tuple[int, ...]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _assert_archive(directory: int, name: str, identity: tuple[int, ...]) -> None:
    info = os.stat(name, dir_fd=directory, follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or _fingerprint(info) != identity or info.st_nlink != 1:
        raise ArchiveError("Archive file changed before pruning")


def _durable_archive(directory: int, name: str, identity: tuple[int, ...]) -> None:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
    try:
        if _fingerprint(_regular(fd, private=True)) != identity:
            raise ArchiveError("Archive changed before durability check")
        os.fsync(fd)
        os.fsync(directory)
    finally:
        os.close(fd)


def _prune(conn: sqlite3.Connection, path: Path, identity: tuple[int, int], directory: int,
           name: str, source: str, archived: list[dict[str, str]], cutoff: datetime, budget: int, live: list[dict[str, str]]):
    candidates = [row for row in live if _housekeeping(row) and _timestamp(row["created_at"]) < cutoff]
    candidates = candidates[:budget]
    predicate = " AND ".join(f"{column} = ?" for column in COLUMNS)
    # Verify bytes and trailer once, then fence inode/size/mtime/ctime in every batch.
    _, checked, archive_identity = _read_archive(directory, name, source)
    if checked != archived:
        raise ArchiveError("Archive changed before pruning")
    _durable_archive(directory, name, archive_identity)
    for offset in range(0, len(candidates), DELETE_BATCH):
        conn.execute("BEGIN IMMEDIATE")
        try:
            if _db_identity(path) != identity:
                raise ArchiveError("Database replaced before pruning")
            _assert_archive(directory, name, archive_identity)
            batch_deleted = 0
            for row in candidates[offset:offset + DELETE_BATCH]:
                current = conn.execute("SELECT * FROM audit_logs WHERE id = ?", (row["id"],)).fetchone()
                if current is None:
                    continue
                if dict(current) != row:
                    raise ArchiveError("Audit row preimage changed; batch retained")
                batch_deleted += conn.execute("DELETE FROM audit_logs WHERE " + predicate, tuple(row[key] for key in COLUMNS)).rowcount
            _assert_archive(directory, name, archive_identity)
            conn.commit()
            yield batch_deleted
        except BaseException:
            conn.rollback()
            raise


def _run(conn: sqlite3.Connection, path: Path, identity: tuple[int, int], directory: int | None,
         now: datetime, apply: bool) -> dict[str, Any]:
    rows = _read_rows(conn)
    source = hashlib.sha256(str(path).encode()).hexdigest()
    current_month = now.strftime("%Y-%m")
    cutoff = now - timedelta(days=90)
    # The preceding 12 completed calendar months remain available.
    expiration = f"{now.year - 1:04d}-{now.month:02d}"
    months: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        month = _month(row)
        if month < current_month:
            months.setdefault(month, []).append(row)
    names = [] if directory is None else _names(directory)
    archive_names = [name for name in names if ARCHIVE_RE.fullmatch(name)]
    if len(archive_names) > MAX_ARCHIVES or len(months) > MAX_ARCHIVES:
        raise ArchiveError("Archive month count exceeds the maintenance bound")
    for name in archive_names:
        month = ARCHIVE_RE.fullmatch(name)[1]
        if month < current_month:
            months.setdefault(month, [])
    if len(months) > MAX_ARCHIVES:
        raise ArchiveError("Combined archive month count exceeds the maintenance bound")
    result: dict[str, Any] = {"mode": "apply" if apply else "dry-run", "status": "ok", "months": [],
                              "archived_rows": 0, "deleted_rows": 0, "expired_archives": 0,
                              "pinned_rows": sum(not _housekeeping(row) for row in rows), "errors": []}
    for month, live in sorted(months.items()):
        name = f"audit-{month}.jsonl.gz"
        item: dict[str, Any] = {"month": month, "status": "planned", "count": len(live), "prunable": 0,
                                "pinned": sum(not _housekeeping(row) for row in live), "deleted": 0, "expired": False}
        result["months"].append(item)
        try:
            if name in archive_names:
                _, archived, _ = _read_archive(directory, name, source)
                expected = {row["id"]: row for row in archived}
                if any(expected.get(row["id"]) != row for row in live):
                    raise ArchiveError("Late or changed audit rows conflict with the immutable monthly archive")
                item["status"] = "verified"
            else:
                archived = live
                if len(archived) > MAX_ROWS:
                    raise ArchiveError("Monthly archive exceeds the 100000-row bound; no pruning performed")
                if apply:
                    _write_archive(directory, name, source, month, archived, now)
                    _, checked, _ = _read_archive(directory, name, source)
                    if checked != archived:
                        raise ArchiveError("Archive readback differs from source rows")
                    item["status"] = "created"
                    result["archived_rows"] += len(archived)
            item["count"] = len(archived)
            item["pinned"] = sum(not _housekeeping(row) for row in archived)
            item["prunable"] = sum(_housekeeping(row) and _timestamp(row["created_at"]) < cutoff for row in live)
            if apply and item["prunable"]:
                for count in _prune(conn, path, identity, directory, name, source, archived, cutoff,
                                    MAX_PRUNE_ROWS - result["deleted_rows"], live):
                    item["deleted"] += count
                    result["deleted_rows"] += count
                item["remaining_prunable"] = item["prunable"] - item["deleted"]
            if month < expiration:
                if item["pinned"]:
                    item["retention"] = "held-pinned-evidence"
                elif item.get("remaining_prunable", 0):
                    item["retention"] = "held-pruning-pending"
                elif apply:
                    _, checked, archive_identity = _read_archive(directory, name, source)
                    if checked != archived:
                        raise ArchiveError("Archive changed before expiration")
                    conn.execute("BEGIN IMMEDIATE")
                    try:
                        remaining = conn.execute(
                            "SELECT 1 FROM audit_logs WHERE strftime('%Y-%m', created_at, '+9 hours') = ? LIMIT 1",
                            (month,),
                        ).fetchone()
                        if remaining:
                            item["retention"] = "held-pruning-pending"
                        else:
                            _assert_archive(directory, name, archive_identity)
                            os.unlink(name, dir_fd=directory)
                            os.fsync(directory)
                            item["expired"] = True
                            result["expired_archives"] += 1
                        conn.commit()
                    except BaseException:
                        conn.rollback()
                        raise
                else:
                    item["retention"] = "would-expire-housekeeping"
        except (ArchiveError, OSError, sqlite3.Error) as exc:
            item["status"] = "blocked"
            item["error"] = str(exc)
            result["status"] = "blocked"
            result["errors"].append({"month": month, "error": str(exc)})
    return result


def run_archive(*, db_path: str | Path, archive_dir: str | Path,
                now: datetime | None = None, apply: bool = False) -> dict[str, Any]:
    """Plan or apply monthly KST archives; retain 90 days and pin non-housekeeping.

    Dry runs never create directories, archives or locks. Apply is explicit and
    uses a nonblocking process lock. Corrupt/conflicting months are left intact.
    Twelve-month expiration applies only to archives containing housekeeping;
    all other archives are retained indefinitely for operator review.
    """
    now = now or datetime.now(KST)
    if now.tzinfo is None:
        raise ArchiveError("now must have an explicit timezone")
    now = now.astimezone(KST)
    path, destination = _absolute(db_path), _absolute(archive_dir)
    try:
        identity = _db_identity(path)
        with _connection(path, apply=apply, identity=identity) as conn:
            # Validate the entire bounded source before creating even a lock.
            _read_rows(conn)
            with _archive_directory(destination, apply=apply) as directory:
                if not apply:
                    return _run(conn, path, identity, directory, now, False)
                import fcntl
                lock = os.open(".archive.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=directory)
                try:
                    _regular(lock, private=True)
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError as exc:
                        raise ArchiveError("Another archive maintenance process holds the lock") from exc
                    _recover_publication(directory, hashlib.sha256(str(path).encode()).hexdigest())
                    return _run(conn, path, identity, directory, now, True)
                finally:
                    os.close(lock)
    except (OSError, sqlite3.Error) as exc:
        raise ArchiveError("Archive maintenance failed safely: " + str(exc)) from exc


@contextmanager
def _archive_directory(path: Path, *, apply: bool):
    if not apply:
        # Validate existing ancestry even when several destination directories are absent.
        try:
            with _directory(path):
                pass
        except FileNotFoundError:
            yield None
            return
    with _directory(path, create=apply) as directory:
        info = os.fstat(directory)
        if info.st_mode & 0o777 != 0o700 or info.st_uid != os.getuid():
            raise ArchiveError("Archive directory must be owned by this user with mode 0700")
        yield directory
