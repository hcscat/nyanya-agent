"""Provision a private dashboard token before services start; standard library only."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import stat


TOKEN = "NYANYA_DASHBOARD_CONTROL_TOKEN"
TOKEN_FILE = "NYANYA_DASHBOARD_CONTROL_TOKEN_FILE"


def _configuration(env_file: Path) -> dict[str, str]:
    values = {}
    if env_file.exists():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key in {TOKEN, TOKEN_FILE}:
                # Match core.load_env: first value wins; the process environment takes precedence.
                values.setdefault(key, value.strip().strip('"').strip("'"))
    return {key: os.environ.get(key, value) for key, value in values.items()} | {
        key: os.environ[key] for key in (TOKEN, TOKEN_FILE) if key in os.environ
    }


def _is_link(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _prepare_parent(parent: Path) -> None:
    current = Path(parent.anchor)
    for part in parent.parts[1:]:
        current /= part
        try:
            current.mkdir(mode=0o700)
        except FileExistsError:
            pass
        info = current.lstat()
        if _is_link(info) or not stat.S_ISDIR(info.st_mode):
            raise ValueError("Dashboard token directory must not contain links")


def _windows_create(path: Path) -> int:
    """CREATE_NEW with a protected owner-rights DACL before any secret bytes exist."""
    import ctypes
    from ctypes import wintypes
    import msvcrt

    class SecurityAttributes(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("descriptor", wintypes.LPVOID), ("inherit", wintypes.BOOL)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    security = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.POINTER(SecurityAttributes), wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.LocalFree.argtypes = [wintypes.LPVOID]
    kernel.GetVolumePathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    kernel.GetVolumeInformationW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
                                           ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
                                           ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD]
    security.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.LPVOID), ctypes.POINTER(wintypes.DWORD),
    ]
    volume, flags = ctypes.create_unicode_buffer(32768), wintypes.DWORD()
    if (not kernel.GetVolumePathNameW(str(path.parent), volume, len(volume))
            or not kernel.GetVolumeInformationW(volume.value, None, 0, None, None, ctypes.byref(flags), None, 0)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not flags.value & 0x8:  # FILE_PERSISTENT_ACLS
        raise ValueError("Dashboard token storage requires filesystem ACL support")
    descriptor = wintypes.LPVOID()
    # OW is the well-known Owner Rights SID; P prevents inherited group access.
    if not security.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        "D:P(A;;FA;;;OW)", 1, ctypes.byref(descriptor), None,
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        attributes = SecurityAttributes(ctypes.sizeof(SecurityAttributes), descriptor, False)
        handle = kernel.CreateFileW(str(path), 0xC0000000, 0, ctypes.byref(attributes), 1, 0x80, None)
        if handle == wintypes.HANDLE(-1).value:
            code = ctypes.get_last_error()
            if code in {80, 183}:
                raise FileExistsError("Dashboard token already exists")
            raise ctypes.WinError(code)
        try:
            return msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
        except BaseException:
            kernel.CloseHandle(handle)
            raise
    finally:
        kernel.LocalFree(descriptor)


def _existing_token(path: Path) -> None:
    info = path.lstat()
    if _is_link(info):
        raise ValueError("Dashboard token must not be a link")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino)):
            raise ValueError("Dashboard token must be a single regular file")
        if os.name != "nt" and (opened.st_uid != os.getuid() or opened.st_mode & 0o077):
            raise ValueError("Existing dashboard token must be owner-only; contents were preserved")
        value = stream.read(4097)
        if len(value) > 4096 or not value.decode("utf-8").strip():
            raise ValueError("Existing dashboard token is empty or invalid; contents were preserved")


def ensure_dashboard_token(state_root: Path, env_file: Path) -> str:
    settings = _configuration(env_file)
    if settings.get(TOKEN, "").strip():
        return "configured"
    value = settings.get(TOKEN_FILE, "data/dashboard_control.token")
    if not value.strip():
        raise ValueError("Dashboard token file path must not be empty")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = state_root / path
    path = Path(os.path.abspath(path))
    _prepare_parent(path.parent)
    try:
        fd = (_windows_create(path) if os.name == "nt" else os.open(
            path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
        ))
    except FileExistsError:
        _existing_token(path)
        return "present"
    # A failed first write stays visible and held; never rotate an existing credential.
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
        if os.name != "nt":
            os.fchmod(stream.fileno(), 0o600)
        stream.write(secrets.token_urlsafe(32) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return "created"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()
    try:
        status = ensure_dashboard_token(args.state_root, args.env_file)
    except (OSError, ValueError):
        # Exceptions can include private paths or invalid credential bytes.
        parser.exit(1, "Dashboard token provisioning failed; inspect the configured file and private permissions locally.\n")
    print(f"dashboard_token={status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
