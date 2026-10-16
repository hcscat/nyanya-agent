"""Exact, expiring, one-use consent for a locally inspected Discord document.

This module reuses the approvals ledger, but grants neither workspace writes nor
permission to skip extraction or credential checks. It stores scope and detection
counts only. The caller must safely reopen and reinspect the file, compare its
identity and frozen bytes, then consume immediately before its sole SDK send.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import PurePosixPath
import re

from nyanya_agent import database as db, execution_store as ledger
from nyanya_agent.task_outcomes import SafeOperationError


ACTION = "discord.upload.pii"
MAX_PENDING_PER_OWNER = 16
MAX_TTL_SECONDS = 300
COUNT_KINDS = frozenset({"email", "phone", "resident_id", "payment_card", "bank_account",
                         "passport", "person_name", "address", "local_path"})
_IDENTITY_KEYS = frozenset({"dev", "ino", "size", "mtime_ns", "ctime_ns"})
_SCOPE_KEYS = ("authorized_actor", "conversation_key", "workspace", "relative_path", "destination_id",
               "request_channel_id", "sha256", "file_identity", "counts")
_ERROR = "업로드 확인이 유효하지 않습니다. 파일과 대상이 같은지 확인하고 새로 요청하세요."


def _time(value):
    result = datetime.now(UTC) if value is None else value
    if not isinstance(result, datetime) or result.tzinfo is None:
        raise SafeOperationError(_ERROR)
    return result.astimezone(UTC)


def _text(value, limit=512):
    if not isinstance(value, str) or not value or len(value) > limit or any(ord(c) < 32 for c in value):
        raise SafeOperationError(_ERROR)
    return value


def _workspace(value):
    value = _text(str(value), 4096)
    path = PurePosixPath(value)
    if not path.is_absolute() or ".." in path.parts:
        raise SafeOperationError(_ERROR)
    return str(path)


def _relative(value):
    value = _text(value, 4096)
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts or "\\" in value:
        raise SafeOperationError(_ERROR)
    return str(path)


def _digest(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise SafeOperationError(_ERROR)
    return value


def _identity(value):
    if (not isinstance(value, dict) or set(value) != _IDENTITY_KEYS
            or any(type(item) is not int or item < 0 for item in value.values())):
        raise SafeOperationError(_ERROR)
    return dict(value)


def _counts(value):
    if (not isinstance(value, dict) or not value or not set(value) <= COUNT_KINDS
            or any(type(item) is not int or item < 0 or item > 1_000_000 for item in value.values())
            or not any(value.values())):
        raise SafeOperationError(_ERROR)
    return {key: item for key, item in value.items() if item}


def _scope_hash(metadata):
    scope = {key: metadata[key] for key in _SCOPE_KEYS}
    return hashlib.sha256(json.dumps(scope, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _record(row):
    return ledger._parse_record(dict(row))


def _owned(conn, approval_id, owner_key):
    row = conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
    if not row or row["action"] != ACTION or row["requested_by"] != owner_key:
        raise SafeOperationError(_ERROR)
    metadata = ledger.decode_json(row["metadata_json"], {})
    if not isinstance(metadata, dict) or metadata.get("authorized_actor") != owner_key:
        raise SafeOperationError(_ERROR)
    return row, metadata


def _event(conn, approval_id, event, status):
    # An upload confirmation has no task/execution; execution_events requires one.
    # Reuse the independent audit ledger without creating a fictitious task.
    db.log_audit(conn, actor="upload-privacy", action=f"upload.{event}",
                 entity_type="upload_approval", entity_id=approval_id,
                 detail={"action": ACTION, "status": status})


def _close(conn, row, metadata, status, timestamp):
    metadata = {**metadata, "phase": status}
    changed = conn.execute(
        "UPDATE approvals SET status=?,decided_by=?,decided_at=?,metadata_json=? "
        "WHERE id=? AND action=? AND status='pending'",
        (status, row["requested_by"], timestamp.isoformat(), ledger.encode_json(metadata), row["id"], ACTION),
    ).rowcount
    if changed:
        _event(conn, row["id"], status, status)


def request_upload(db_path, *, owner_key, conversation_key, workspace, relative_path,
                   destination_id, request_channel_id, sha256, file_identity, counts,
                   now=None, ttl=300):
    """Request confirmation without changing any task/execution state."""
    timestamp = _time(now)
    if type(ttl) is not int or not 1 <= ttl <= MAX_TTL_SECONDS:
        raise SafeOperationError(_ERROR)
    metadata = {
        "schema_version": 1, "phase": "pending", "authorized_actor": _text(owner_key),
        "conversation_key": _text(conversation_key), "workspace": _workspace(workspace),
        "relative_path": _relative(relative_path), "destination_id": _text(destination_id, 128),
        "request_channel_id": _text(request_channel_id, 128), "sha256": _digest(sha256),
        "file_identity": _identity(file_identity), "counts": _counts(counts),
    }
    metadata["scope_hash"] = _scope_hash(metadata)
    ledger.apply_migrations(db_path)
    approval_id = ledger.new_id("upload")
    with db.connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        old = conn.execute("SELECT * FROM approvals WHERE action=? AND requested_by=? AND status='pending'",
                           (ACTION, owner_key)).fetchall()
        for row in old:
            expiry = ledger._parse_iso(row["expires_at"])
            if expiry is None or expiry <= timestamp:
                old_metadata = ledger.decode_json(row["metadata_json"], {})
                _close(conn, row, old_metadata if isinstance(old_metadata, dict) else {}, "expired", timestamp)
        pending = conn.execute("SELECT COUNT(*) FROM approvals WHERE action=? AND requested_by=? AND status='pending'",
                               (ACTION, owner_key)).fetchone()[0]
        if pending >= MAX_PENDING_PER_OWNER:
            conn.commit()
            raise SafeOperationError("대기 중인 업로드 확인이 많습니다. 기존 확인을 취소하거나 만료 후 요청하세요.")
        conn.execute(
            "INSERT INTO approvals(id,action,status,requested_by,reason,metadata_json,requested_at,expires_at) "
            "VALUES (?,?,'pending',?,'Document privacy confirmation required',?,?,?)",
            (approval_id, ACTION, owner_key, ledger.encode_json(metadata), timestamp.isoformat(),
             (timestamp + timedelta(seconds=ttl)).isoformat()),
        )
        _event(conn, approval_id, "requested", "pending")
        return _record(conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone())


def get_upload(db_path, approval_id, *, owner_key, conversation_key):
    """Read only this authenticated requester's confirmation in its conversation."""
    ledger.apply_migrations(db_path)
    with db.connect(db_path) as conn:
        row, metadata = _owned(conn, approval_id, owner_key)
        if metadata.get("conversation_key") != conversation_key:
            raise SafeOperationError(_ERROR)
        return _record(row)


def consume_upload(db_path, approval_id, *, owner_key, conversation_key, sha256,
                   destination_id, workspace, relative_path, file_identity, now=None):
    """Atomically grant one send claim; failures never include document values."""
    ledger.apply_migrations(db_path)
    with db.connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        timestamp = _time(now)
        row, metadata = _owned(conn, approval_id, owner_key)
        if row["status"] != "pending" or metadata.get("phase") != "pending":
            raise SafeOperationError(_ERROR)
        expiry = ledger._parse_iso(row["expires_at"])
        if expiry is None or expiry <= timestamp:
            _close(conn, row, metadata, "expired", timestamp)
            conn.commit()
            raise SafeOperationError("업로드 확인이 만료되었습니다. 파일을 다시 검사해 새로 요청하세요.")
        try:
            expected = {"conversation_key": _text(conversation_key), "sha256": _digest(sha256),
                        "destination_id": _text(destination_id, 128), "workspace": _workspace(workspace),
                        "relative_path": _relative(relative_path), "file_identity": _identity(file_identity)}
            valid = (metadata.get("schema_version") == 1 and row["task_id"] is None and row["execution_id"] is None
                     and all(metadata.get(key) == value for key, value in expected.items())
                     and _scope_hash(metadata) == metadata.get("scope_hash"))
        except (SafeOperationError, KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            _close(conn, row, metadata, "rejected", timestamp)
            conn.commit()
            raise SafeOperationError(_ERROR)
        metadata = {**metadata, "phase": "consumed"}
        changed = conn.execute(
            "UPDATE approvals SET status='approved',decided_by=?,decided_at=?,metadata_json=? "
            "WHERE id=? AND action=? AND status='pending'",
            (owner_key, timestamp.isoformat(), ledger.encode_json(metadata), approval_id, ACTION),
        ).rowcount
        if changed != 1:
            raise SafeOperationError(_ERROR)
        _event(conn, approval_id, "consumed", "approved")
        return _record(conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone())


def reject_upload(db_path, approval_id, *, owner_key, conversation_key, now=None):
    """Reject/cancel before a send claim; consumed uploads cannot be called unsent."""
    ledger.apply_migrations(db_path)
    with db.connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        timestamp = _time(now)
        row, metadata = _owned(conn, approval_id, owner_key)
        if metadata.get("conversation_key") != conversation_key:
            if row["status"] == "pending":
                _close(conn, row, metadata, "rejected", timestamp)
                conn.commit()
            raise SafeOperationError(_ERROR)
        if row["status"] == "rejected":
            return _record(row)
        if row["status"] != "pending" or metadata.get("phase") != "pending":
            raise SafeOperationError(_ERROR)
        expiry = ledger._parse_iso(row["expires_at"])
        _close(conn, row, metadata, "expired" if expiry is None or expiry <= timestamp else "rejected", timestamp)
        return _record(conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone())
