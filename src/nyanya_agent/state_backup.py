"""Consistent SQLite snapshot for the distribution CLI, including WAL commits."""

from pathlib import Path
import sqlite3
import sys
import time


def backup_database(source: Path, destination: Path) -> None:
    source = source.resolve(strict=True)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Backup destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb"):
        pass
    destination.chmod(0o600)
    deadline = time.monotonic() + 30
    def progress(_status, _remaining, _total):
        if time.monotonic() >= deadline:
            raise TimeoutError("SQLite backup timed out")
    try:
        src = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=5)
        try:
            dst = sqlite3.connect(destination)
            try:
                src.backup(dst, pages=128, progress=progress)
                if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Backup integrity check failed")
            finally:
                dst.close()
        finally:
            src.close()
    except Exception:
        destination.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    try:
        backup_database(Path(sys.argv[1]), Path(sys.argv[2]))
    except Exception as exc:
        print(f"Database backup failed ({type(exc).__name__})", file=sys.stderr)
        raise SystemExit(1) from None
