"""Private, bounded service output and conservative monthly log maintenance."""

from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta, timezone
import fcntl
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import tarfile
import time
from uuid import uuid4
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")
UTC = timezone.utc
SEGMENT_BYTES = 4 * 1024 * 1024
RAW_LIMIT_BYTES = 128 * 1024 * 1024  # Per managed service, not a stale cross-process total.
CHUNK_BYTES = 64 * 1024
MAX_ARCHIVE_FILES = 20_000
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_MEMBER_BYTES = 16 * 1024 * 1024
MAX_DIRECTORY_ENTRIES = 100_000
SERVICES = frozenset({"discord", "dashboard", "memory-worker"})
SEGMENT_RE = re.compile(
    r"^(discord|dashboard|memory-worker)\.(stdout|stderr)\."
    r"(\d{8}T\d{12}Z)\.([0-9a-f]{32})\.log$"
)
ARCHIVE_RE = re.compile(r"^service-logs-(\d{4}-\d{2})\.tar\.gz$")


def _clock() -> datetime:
    return datetime.now(UTC)


def _instant(value: datetime | None) -> datetime:
    if value is None:
        return _clock()
    if value.tzinfo is None:
        raise ValueError("now must have a timezone")
    return value.astimezone(UTC)


def _private_dir(path: Path, *, create: bool) -> None:
    absolute = path.absolute()
    for part in (absolute, *absolute.parents):
        if part.is_symlink():
            raise ValueError(f"Symlink directory refused: {part}")
    if create:
        absolute.mkdir(parents=True, exist_ok=True, mode=0o700)
        absolute.chmod(0o700)
    if not absolute.is_dir():
        raise ValueError(f"Directory missing: {absolute}")


def _safe_file(path: Path, *, allow_two_links: bool = False) -> os.stat_result:
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink not in ({1, 2} if allow_two_links else {1})
            or info.st_mode & 0o077):
        raise ValueError(f"Unsafe log file: {path.name}")
    return info


def _fingerprint(path: Path) -> tuple[int, int, int, int, int]:
    info = _safe_file(path)
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _linked_fingerprint(path: Path) -> tuple[int, int, int, int, int]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 2:
        raise ValueError(f"Archive fence changed: {path.name}")
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _open_existing(path: Path, *, allow_two_links: bool = False):
    before = _safe_file(path, allow_two_links=allow_two_links)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    after = os.fstat(fd)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
    ):
        os.close(fd)
        raise ValueError(f"Log file changed: {path.name}")
    return os.fdopen(fd, "rb"), before


def _digest_file(path: Path) -> dict[str, object]:
    digest = hashlib.sha256()
    with _open_existing(path)[0] as source:
        before = os.fstat(source.fileno())
        while chunk := source.read(CHUNK_BYTES):
            digest.update(chunk)
        after = os.fstat(source.fileno())
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError(f"Log file changed while reading: {path.name}")
    return {"name": path.name, "size": before.st_size, "sha256": digest.hexdigest()}


def _segment_date(name: str) -> datetime:
    matched = SEGMENT_RE.fullmatch(name)
    if not matched:
        raise ValueError(f"Unrecognized segment: {name}")
    return datetime.strptime(matched.group(3), "%Y%m%dT%H%M%S%fZ").replace(tzinfo=UTC).astimezone(KST)


def _month(value: datetime) -> str:
    return value.astimezone(KST).strftime("%Y-%m")


def _months_before(month: str, count: int) -> str:
    year, number = map(int, month.split("-"))
    index = year * 12 + number - 1 - count
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


class _Stream:
    def __init__(self, log_dir: Path, name: str, stream: str, clock, segment_bytes: int):
        self.directory = log_dir
        self.name = name
        self.stream = stream
        self.clock = clock
        self.segment_bytes = segment_bytes
        self.current = log_dir / f"{name}.{stream}.current"
        if self.current.exists() or self.current.is_symlink():
            info = self.current.lstat()
            if stat.S_ISREG(info.st_mode) and info.st_nlink == 2:
                # Recover a crash after the closed segment link but before unlinking .current.
                matches = [item for item in log_dir.iterdir() if SEGMENT_RE.fullmatch(item.name)
                           and item.name.startswith(f"{name}.{stream}.")
                           and (other := item.lstat()).st_dev == info.st_dev and other.st_ino == info.st_ino]
                if len(matches) != 1:
                    raise ValueError(f"Ambiguous interrupted segment: {self.current.name}")
                self.current.unlink()
            else:
                _safe_file(self.current)
                self._close_segment()
        self.fd = os.open(self.current, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        self.size = 0
        self.day = self.clock().astimezone(KST).date()

    def _close_segment(self) -> None:
        _safe_file(self.current)
        stamp = self.clock().astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        target = self.directory / f"{self.name}.{self.stream}.{stamp}.{uuid4().hex}.log"
        os.link(self.current, target, follow_symlinks=False)
        self.current.unlink()

    def rotate(self) -> None:
        os.fsync(self.fd)
        os.close(self.fd)
        self._close_segment()
        self.fd = os.open(self.current, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        self.size = 0
        self.day = self.clock().astimezone(KST).date()

    def write(self, data: bytes) -> None:
        view = memoryview(data)
        while view:
            if self.size == self.segment_bytes or self.clock().astimezone(KST).date() != self.day:
                self.rotate()
            part_length = min(len(view), self.segment_bytes - self.size)
            portion = view[:part_length]
            while portion:
                count = os.write(self.fd, portion)
                if count <= 0:
                    raise OSError("Service log write made no progress")
                self.size += count
                portion = portion[count:]
            view = view[part_length:]

    def close(self) -> None:
        if self.fd is None:
            return
        os.fsync(self.fd)
        os.close(self.fd)
        self.fd = None
        if self.size:
            self._close_segment()
        else:
            self.current.unlink()


def _raw_bytes(directory: Path, name: str) -> int:
    total = 0
    for index, entry in enumerate(directory.iterdir()):
        if index >= MAX_DIRECTORY_ENTRIES:
            raise ValueError("Service log directory has too many entries")
        if entry.name.startswith(f"{name}.") and (
            SEGMENT_RE.fullmatch(entry.name) or entry.name in {f"{name}.stdout.current", f"{name}.stderr.current"}
        ):
            total += _safe_file(entry).st_size
    return total


def _write_status(directory: Path, name: str, exit_code: int, error_class: str = "") -> None:
    target = directory / f"{name}.last-status.json"
    if target.exists() or target.is_symlink():
        _safe_file(target)
    temp = directory / f".{name}.last-status.{uuid4().hex}.tmp"
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump({"exit_code": exit_code, "error_class": error_class, "ended_at": _clock().isoformat()}, output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def _signal_group(pid: int, signum: int) -> None:
    try:
        os.killpg(pid, signum)
    except ProcessLookupError:
        pass


def run_service(
    log_dir: str | Path,
    name: str,
    command: list[str],
    *,
    segment_bytes: int = SEGMENT_BYTES,
    raw_limit_bytes: int = RAW_LIMIT_BYTES,
    clock=_clock,
) -> int:
    """Capture both pipes without line buffering; stop the child if raw evidence fills the budget."""
    if (name not in SERVICES or not command or segment_bytes < 1 or segment_bytes > MAX_ARCHIVE_MEMBER_BYTES
            or raw_limit_bytes < segment_bytes):
        raise ValueError("Invalid service logging arguments")
    directory = Path(log_dir)
    _private_dir(directory, create=True)
    lock_path = directory / f".{name}.service-logs.lock"
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
            raise ValueError("Unsafe service log lock")
        streams = {}
        child = None
        received_signal = None
        sent_at = None
        old_handlers = {}
        limit_hit = False
        result_code = 1
        error_class = ""

        def forward(signum, _frame):
            nonlocal received_signal, sent_at
            received_signal = signum
            if child is not None and child.poll() is None and sent_at is None:
                _signal_group(child.pid, signum)
                sent_at = time.monotonic()

        try:
            for kind in ("stdout", "stderr"):
                streams[kind] = _Stream(directory, name, kind, clock, segment_bytes)
            total = _raw_bytes(directory, name)
            if total >= raw_limit_bytes:
                result_code = 75
                error_class = "RawLogLimit"
                return result_code
            for signum in (signal.SIGTERM, signal.SIGINT):
                old_handlers[signum] = signal.signal(signum, forward)
            child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            if received_signal is not None:
                _signal_group(child.pid, received_signal)
                sent_at = time.monotonic()
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ, "stdout")
                selector.register(child.stderr, selectors.EVENT_READ, "stderr")
                while selector.get_map() or child.poll() is None:
                    if sent_at is not None and time.monotonic() - sent_at > 5:
                        _signal_group(child.pid, signal.SIGKILL)
                    if sent_at is not None and time.monotonic() - sent_at > 8:
                        raise TimeoutError("Child process group retained output pipes after shutdown")
                    for key, _ in selector.select(timeout=0.2):
                        chunk = os.read(key.fileobj.fileno(), CHUNK_BYTES)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                            continue
                        streams[key.data].write(chunk)
                        total += len(chunk)
                        if total >= raw_limit_bytes:
                            total = _raw_bytes(directory, name)
                        if total >= raw_limit_bytes and not limit_hit:
                            message = b"\n[service_logs] Raw log limit reached; service stopped with evidence preserved.\n"
                            streams["stderr"].write(message)
                            limit_hit = True
                            error_class = "RawLogLimit"
                            _signal_group(child.pid, signal.SIGKILL)
                            sent_at = time.monotonic()
                    if child.poll() is not None and sent_at is None and selector.get_map():
                        # A descendant holding a pipe open must not keep launchd's wrapper alive forever.
                        _signal_group(child.pid, signal.SIGTERM)
                        sent_at = time.monotonic()
            result = child.wait()
            _signal_group(child.pid, signal.SIGTERM)
            time.sleep(0.05)
            _signal_group(child.pid, signal.SIGKILL)
            result_code = 128 + received_signal if received_signal else (75 if limit_hit else (128 - result if result < 0 else result))
            return result_code
        except Exception as exc:
            error_class = type(exc).__name__
            raise
        finally:
            for signum, handler in old_handlers.items():
                signal.signal(signum, handler)
            if child is not None and child.poll() is None:
                _signal_group(child.pid, signal.SIGKILL)
                child.wait()
            elif child is not None:
                _signal_group(child.pid, signal.SIGKILL)
            for stream in streams.values():
                stream.close()
            _write_status(directory, name, result_code, error_class)
    finally:
        os.close(lock_fd)


def _verify_archive(path: Path, month: str, *, allow_two_links: bool = False) -> dict[str, dict[str, object]]:
    _safe_file(path, allow_two_links=allow_two_links)
    try:
        seen: dict[str, dict[str, object]] = {}
        manifest = None
        total = 0
        with _open_existing(path, allow_two_links=allow_two_links)[0] as compressed, gzip.GzipFile(
            fileobj=compressed, mode="rb"
        ) as unpacked:
            with tarfile.open(fileobj=unpacked, mode="r|") as archive:
                for member in archive:
                    if not member.isfile() or member.name in seen or manifest is not None:
                        raise ValueError("Archive members are invalid")
                    if member.name == "manifest.json":
                        if member.size > 4 * 1024 * 1024:
                            raise ValueError("Archive manifest is too large")
                        manifest = json.loads(archive.extractfile(member).read(member.size + 1))
                        continue
                    if (len(seen) >= MAX_ARCHIVE_FILES or member.size > MAX_ARCHIVE_MEMBER_BYTES
                            or _month(_segment_date(member.name)) != month):
                        raise ValueError("Archive contains excessive or unrecognized log")
                    total += member.size
                    if total > MAX_ARCHIVE_BYTES:
                        raise ValueError("Archive uncompressed data exceeds limit")
                    digest = hashlib.sha256()
                    source = archive.extractfile(member)
                    while chunk := source.read(CHUNK_BYTES):
                        digest.update(chunk)
                    seen[member.name] = {"name": member.name, "size": member.size, "sha256": digest.hexdigest()}
            # Tar stops at its end marker; draining gzip is required to validate CRC/ISIZE.
            trailing = 0
            while chunk := unpacked.read(CHUNK_BYTES):
                trailing += len(chunk)
                if trailing > 8 * 1024 * 1024:
                    raise ValueError("Archive has excessive trailing data")
        if not isinstance(manifest, dict) or manifest.get("version") != 1 or manifest.get("month") != month:
            raise ValueError("Archive manifest contract mismatch")
        records = manifest.get("files")
        if not isinstance(records, list) or len(records) != len(seen):
            raise ValueError("Archive manifest entries mismatch")
        expected = {record["name"]: record for record in records}
        if len(expected) != len(records) or expected != seen:
            raise ValueError("Archive checksum mismatch")
        return expected
    except (OSError, EOFError, tarfile.TarError, KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Archive validation failed: {path.name}") from exc


def _create_archive(path: Path, month: str, records: list[dict[str, object]], log_dir: Path) -> None:
    if len(records) > MAX_ARCHIVE_FILES or sum(record["size"] for record in records) > MAX_ARCHIVE_BYTES:
        raise ValueError("Archive input exceeds limit")
    temp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as output:
            with tarfile.open(fileobj=output, mode="w:gz") as archive:
                for record in records:
                    source_path = log_dir / record["name"]
                    with _open_existing(source_path)[0] as source:
                        info = tarfile.TarInfo(record["name"])
                        info.size = record["size"]
                        info.mode = 0o600
                        archive.addfile(info, source)
                    if _digest_file(source_path) != record:
                        raise ValueError(f"Log changed during archive: {record['name']}")
                payload = json.dumps({"version": 1, "month": month, "files": records}, sort_keys=True).encode()
                info = tarfile.TarInfo("manifest.json")
                info.size = len(payload)
                info.mode = 0o600
                archive.addfile(info, io.BytesIO(payload))
            output.flush()
            os.fsync(output.fileno())
        _verify_archive(temp, month)
        os.link(temp, path, follow_symlinks=False)
    finally:
        temp.unlink(missing_ok=True)
    _fsync_dir(path.parent)


def _retire_raw(path: Path, record: dict[str, object]) -> None:
    before = _fingerprint(path)
    if _digest_file(path) != record:
        raise ValueError(f"Log changed before removal: {path.name}")
    quarantine = path.with_name(f".{path.name}.{uuid4().hex}.retiring")
    if quarantine.exists() or quarantine.is_symlink():
        raise ValueError("Log quarantine path already exists")
    os.rename(path, quarantine)
    try:
        # rename updates ctime on some filesystems; inode and content must remain stable.
        digest = _digest_file(quarantine)
        if (_fingerprint(quarantine)[:4] != before[:4] or digest["size"] != record["size"]
                or digest["sha256"] != record["sha256"]):
            raise ValueError(f"Log changed during retirement: {path.name}")
        quarantine.unlink()
    except Exception:
        # A concurrent replacement of the original name must not be overwritten.
        if quarantine.exists() and not path.exists() and not path.is_symlink():
            os.rename(quarantine, path)
        raise


@contextmanager
def _maintenance_lock(directory: Path):
    path = directory / ".service-logs-maintenance.lock"
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("Unsafe service log maintenance lock")
        yield
    finally:
        os.close(fd)


def maintain_service_logs(
    log_dir: str | Path, archive_dir: str | Path, *, now: datetime | None = None, apply: bool = False
) -> dict[str, object]:
    """Plan by default; apply only complete-month archives and verified retention actions."""
    logs, archives = Path(log_dir), Path(archive_dir)
    instant = _instant(now)
    current_month = _month(instant)
    raw_cutoff = instant.astimezone(KST) - timedelta(days=30)
    archive_floor = _months_before(current_month, 3)
    if not logs.exists() and not logs.is_symlink():
        return {
            "status": "absent", "dry_run": not apply, "archives_create": [], "archives_expire": [],
            "raw_expire": [], "raw_preserved": [], "archive_count": 0,
            "archived_files": 0, "deleted_files": 0, "expired_archives": 0,
        }
    _private_dir(logs, create=apply)
    if archives.exists() or archives.is_symlink():
        _private_dir(archives, create=apply)
    elif apply:
        _private_dir(archives, create=True)
    with _maintenance_lock(archives) if apply else nullcontext():
        segments: dict[str, list[Path]] = {}
        for index, entry in enumerate(logs.iterdir()):
            if index >= MAX_DIRECTORY_ENTRIES:
                raise ValueError("Service log directory has too many entries")
            if SEGMENT_RE.fullmatch(entry.name):
                _safe_file(entry)
                segments.setdefault(_month(_segment_date(entry.name)), []).append(entry)
        existing: dict[str, Path] = {}
        if archives.exists():
            for index, entry in enumerate(archives.iterdir()):
                if index >= MAX_DIRECTORY_ENTRIES:
                    raise ValueError("Service archive directory has too many entries")
                match = ARCHIVE_RE.fullmatch(entry.name)
                if match:
                    _safe_file(entry)
                    existing[match.group(1)] = entry
        # Validate every existing archive before any deletion or publication.
        verified = {month: _verify_archive(path, month) for month, path in sorted(existing.items())}
        planned: dict[str, list[dict[str, object]]] = {}
        report: dict[str, object] = {
            "status": "ok", "dry_run": not apply, "archives_create": [], "archives_expire": [], "raw_expire": [],
            "raw_preserved": [], "archive_count": len(existing),
        }
        for month, paths in sorted(segments.items()):
            paths = sorted(paths)
            if month >= current_month:
                report["raw_preserved"].extend(path.name for path in paths)
                continue
            if month in verified:
                records = verified[month]
                if not all(path.name in records and _digest_file(path) == records[path.name] for path in paths):
                    raise ValueError(f"Late or changed segment conflicts with archive: {month}")
            elif month >= archive_floor:
                planned[month] = [_digest_file(path) for path in paths]
                records = {record["name"]: record for record in planned[month]}
                report["archives_create"].append(f"service-logs-{month}.tar.gz")
            else:
                # Old raw data without an archive stays visible until explicitly reconciled.
                report["raw_preserved"].extend(path.name for path in paths)
                continue
            for path in paths:
                if _segment_date(path.name) < raw_cutoff:
                    report["raw_expire"].append(path.name)
                else:
                    report["raw_preserved"].append(path.name)
        expiring_raw = set(report["raw_expire"])
        for month, path in sorted(existing.items()):
            if month < archive_floor and all(item.name in expiring_raw for item in segments.get(month, [])):
                report["archives_expire"].append(path.name)
        report["archived_files"] = sum(len(records) for records in planned.values())
        report["deleted_files"] = len(report["raw_expire"])
        report["expired_archives"] = len(report["archives_expire"])
        if apply:
            for month, records in planned.items():
                path = archives / f"service-logs-{month}.tar.gz"
                _create_archive(path, month, records, logs)
                verified[month] = _verify_archive(path, month)
            pins = {}
            handles = {}
            try:
                for month in sorted({_month(_segment_date(name)) for name in report["raw_expire"]}):
                    path = archives / f"service-logs-{month}.tar.gz"
                    pin = archives / f".{path.name}.{uuid4().hex}.pin"
                    os.link(path, pin, follow_symlinks=False)
                    pins[month] = pin
                    fence = _linked_fingerprint(path)
                    if _linked_fingerprint(pin) != fence:
                        raise ValueError(f"Archive changed while pinning: {month}")
                    if _verify_archive(pin, month, allow_two_links=True) != verified[month]:
                        raise ValueError(f"Archive changed while pinning: {month}")
                    if _linked_fingerprint(path) != fence or _linked_fingerprint(pin) != fence:
                        raise ValueError(f"Archive changed during pin verification: {month}")
                    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                    handles[month] = fd
                    os.fsync(fd)
                    if _linked_fingerprint(pin) != fence:
                        raise ValueError(f"Archive changed while pinning: {month}")
                    pins[month] = (pin, fence)
                _fsync_dir(archives)
                for name in report["raw_expire"]:
                    month = _month(_segment_date(name))
                    archive_path = archives / f"service-logs-{month}.tar.gz"
                    pin, fence = pins[month]
                    if _linked_fingerprint(archive_path) != fence or _linked_fingerprint(pin) != fence:
                        raise ValueError(f"Archive changed before raw removal: {month}")
                    held = os.fstat(handles[month])
                    if (held.st_dev, held.st_ino, held.st_size, held.st_mtime_ns, held.st_ctime_ns) != fence:
                        raise ValueError(f"Archive handle changed before raw removal: {month}")
                    _retire_raw(logs / name, verified[month][name])
                _fsync_dir(logs)
                for month, (pin, fence) in pins.items():
                    if _linked_fingerprint(archives / f"service-logs-{month}.tar.gz") != fence:
                        raise ValueError(f"Archive changed during raw removal: {month}; pin preserved")
                    pin.unlink()
                _fsync_dir(archives)
            finally:
                for fd in handles.values():
                    os.close(fd)
            for name in report["archives_expire"]:
                path = archives / name
                _verify_archive(path, ARCHIVE_RE.fullmatch(name).group(1))
                path.unlink()
            if report["archives_expire"]:
                _fsync_dir(archives)
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bounded private service output")
    command = parser.add_subparsers(dest="action", required=True)
    run = command.add_parser("run")
    run.add_argument("--log-dir", required=True)
    run.add_argument("--name", choices=sorted(SERVICES), required=True)
    run.add_argument("child", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    child = args.child[1:] if args.child and args.child[0] == "--" else args.child
    return run_service(args.log_dir, args.name, child)


if __name__ == "__main__":
    raise SystemExit(main())
