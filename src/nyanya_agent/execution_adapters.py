#!/usr/bin/env python3
"""Execution adapter contract and local subprocess/tmux/CLI implementations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from typing import Any, Protocol

from nyanya_agent import core
from nyanya_agent import execution_store
from nyanya_agent.bridge_policy import is_allowed_workspace_path


SESSION_NAME_RE = re.compile(r"[^a-zA-Z0-9_.-]+")
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class AdapterCapabilities:
    persistent: bool
    reconnect: bool
    cancel: bool
    output_tail: bool
    artifact_collection: bool
    requires_interactive_auth: bool = False


@dataclass(frozen=True)
class AdapterRequest:
    execution_id: str
    command: tuple[str, ...]
    cwd: Path
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 600
    output_dir: Path | None = None


@dataclass(frozen=True)
class AdapterHandle:
    adapter_type: str
    execution_id: str
    external_id: str
    pid: int | None
    tmux_session: str
    started_at: str
    status_file: str
    stdout_file: str
    stderr_file: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AdapterObservation:
    status: str
    confidence: float
    running: bool
    exit_code: int | None = None
    output_tail: str = ""
    error_tail: str = ""
    evidence: tuple[str, ...] = ()
    observed_at: str = field(default_factory=now_iso)


class ExecutionAdapter(Protocol):
    name: str
    capabilities: AdapterCapabilities

    def probe(self) -> dict[str, Any]: ...

    def start(self, request: AdapterRequest) -> AdapterHandle: ...

    def observe(self, handle: AdapterHandle) -> AdapterObservation: ...

    def cancel(self, handle: AdapterHandle, grace_seconds: float = 5.0) -> AdapterObservation: ...


def _validate_request(request: AdapterRequest) -> tuple[Path, Path]:
    if not request.command:
        raise ValueError("Adapter command cannot be empty")
    cwd = request.cwd.expanduser().resolve(strict=True)
    if not cwd.is_dir():
        raise ValueError(f"Adapter cwd is not a directory: {cwd}")
    if not is_allowed_workspace_path(cwd):
        raise PermissionError(f"Adapter cwd is outside allowed workspace roots: {cwd}")
    output_dir = request.output_dir or core.STATE_ROOT / "run" / "executions" / request.execution_id
    output_dir = output_dir.expanduser().resolve(strict=False)
    if not is_allowed_workspace_path(output_dir):
        raise PermissionError(f"Adapter output directory is outside allowed workspace roots: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)
    return cwd, output_dir


def _runner_command(request: AdapterRequest, status_file: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "nyanya_agent.adapter_runner",
        "--status-file",
        str(status_file),
        "--started-at",
        now_iso(),
        "--",
        *request.command,
    ]


def _tail(path: str, limit: int = 8000) -> str:
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return ""
    with file_path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(0, size - limit))
        return handle.read().decode("utf-8", errors="replace").strip()


def _read_marker(path: str) -> dict[str, Any] | None:
    marker_path = Path(path)
    if not marker_path.exists():
        return None
    try:
        return json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _marker_observation(handle: AdapterHandle, marker: dict[str, Any]) -> AdapterObservation:
    returncode = int(marker.get("returncode", 1))
    return AdapterObservation(
        status="succeeded" if returncode == 0 else "failed",
        confidence=1.0,
        running=False,
        exit_code=returncode,
        output_tail=_tail(handle.stdout_file),
        error_tail=_tail(handle.stderr_file),
        evidence=("atomic completion marker",),
    )


def _pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class ManagedSubprocessAdapter:
    name = "subprocess"
    capabilities = AdapterCapabilities(
        persistent=False,
        reconnect=True,
        cancel=True,
        output_tail=True,
        artifact_collection=True,
    )

    def __init__(self) -> None:
        self._processes: dict[int, subprocess.Popen[bytes]] = {}

    def probe(self) -> dict[str, Any]:
        return {"available": True, "python": sys.version.split()[0], "adapter": self.name}

    def start(self, request: AdapterRequest) -> AdapterHandle:
        cwd, output_dir = _validate_request(request)
        status_file = output_dir / "status.json"
        stdout_file = output_dir / "stdout.log"
        stderr_file = output_dir / "stderr.log"
        command = _runner_command(request, status_file)
        environment = os.environ.copy()
        environment.update(request.env)
        started_at = now_iso()
        with stdout_file.open("ab") as stdout, stderr_file.open("ab") as stderr:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
        self._processes[process.pid] = process
        return AdapterHandle(
            adapter_type=self.name,
            execution_id=request.execution_id,
            external_id=str(process.pid),
            pid=process.pid,
            tmux_session="",
            started_at=started_at,
            status_file=str(status_file),
            stdout_file=str(stdout_file),
            stderr_file=str(stderr_file),
            metadata={"timeout_seconds": request.timeout_seconds},
        )

    def observe(self, handle: AdapterHandle) -> AdapterObservation:
        marker = _read_marker(handle.status_file)
        if marker:
            return _marker_observation(handle, marker)
        process = self._processes.get(handle.pid or -1)
        if process is not None:
            returncode = process.poll()
            if returncode is None:
                return AdapterObservation(
                    status="running",
                    confidence=0.98,
                    running=True,
                    output_tail=_tail(handle.stdout_file),
                    error_tail=_tail(handle.stderr_file),
                    evidence=("managed child process is running",),
                )
            time.sleep(0.02)
            marker = _read_marker(handle.status_file)
            if marker:
                return _marker_observation(handle, marker)
            return AdapterObservation(
                status="succeeded" if returncode == 0 else "failed",
                confidence=0.8,
                running=False,
                exit_code=returncode,
                output_tail=_tail(handle.stdout_file),
                error_tail=_tail(handle.stderr_file),
                evidence=("managed child process exit code", "completion marker missing"),
            )
        if _pid_alive(handle.pid):
            return AdapterObservation(
                status="running",
                confidence=0.7,
                running=True,
                output_tail=_tail(handle.stdout_file),
                error_tail=_tail(handle.stderr_file),
                evidence=("pid exists after adapter restart",),
            )
        return AdapterObservation(
            status="lost",
            confidence=0.45,
            running=False,
            output_tail=_tail(handle.stdout_file),
            error_tail=_tail(handle.stderr_file),
            evidence=("pid absent", "completion marker missing"),
        )

    def cancel(self, handle: AdapterHandle, grace_seconds: float = 5.0) -> AdapterObservation:
        process = self._processes.get(handle.pid or -1)

        def alive() -> bool:
            if process is not None:
                return process.poll() is None
            return _pid_alive(handle.pid)

        if handle.pid and alive():
            try:
                os.killpg(handle.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            deadline = time.monotonic() + max(0.0, grace_seconds)
            while alive() and time.monotonic() < deadline:
                time.sleep(0.05)
            if alive():
                try:
                    os.killpg(handle.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
        return AdapterObservation(
            status="cancelled",
            confidence=0.95,
            running=False,
            exit_code=-15,
            output_tail=_tail(handle.stdout_file),
            error_tail=_tail(handle.stderr_file),
            evidence=("process group termination requested",),
        )


class TmuxAdapter:
    name = "tmux"
    capabilities = AdapterCapabilities(
        persistent=True,
        reconnect=True,
        cancel=True,
        output_tail=True,
        artifact_collection=True,
    )

    def __init__(self, tmux_binary: str = "tmux") -> None:
        resolved = shutil.which(tmux_binary)
        self.tmux_binary = resolved or tmux_binary

    def probe(self) -> dict[str, Any]:
        completed = subprocess.run(
            [self.tmux_binary, "-V"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        return {
            "available": completed.returncode == 0,
            "version": (completed.stdout or completed.stderr).strip(),
            "adapter": self.name,
        }

    @staticmethod
    def session_name(execution_id: str) -> str:
        safe = SESSION_NAME_RE.sub("-", execution_id).strip("-._") or "execution"
        return f"nyanya-{safe}"[:64]

    def start(self, request: AdapterRequest) -> AdapterHandle:
        cwd, output_dir = _validate_request(request)
        status_file = output_dir / "status.json"
        stdout_file = output_dir / "stdout.log"
        stderr_file = output_dir / "stderr.log"
        session = self.session_name(request.execution_id)
        runner = _runner_command(request, status_file)
        command_text = (
            shlex.join(runner)
            + " >> "
            + shlex.quote(str(stdout_file))
            + " 2>> "
            + shlex.quote(str(stderr_file))
        )
        environment = os.environ.copy()
        environment.update(request.env)
        completed = subprocess.run(
            [self.tmux_binary, "new-session", "-d", "-s", session, "-c", str(cwd), command_text],
            env=environment,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout).strip() or "tmux new-session failed")
        return AdapterHandle(
            adapter_type=self.name,
            execution_id=request.execution_id,
            external_id=session,
            pid=None,
            tmux_session=session,
            started_at=now_iso(),
            status_file=str(status_file),
            stdout_file=str(stdout_file),
            stderr_file=str(stderr_file),
            metadata={"timeout_seconds": request.timeout_seconds},
        )

    def has_session(self, session: str) -> bool:
        completed = subprocess.run(
            [self.tmux_binary, "has-session", "-t", session],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        return completed.returncode == 0

    def capture(self, session: str, lines: int = 120) -> str:
        completed = subprocess.run(
            [self.tmux_binary, "capture-pane", "-p", "-t", session, "-S", f"-{max(1, lines)}"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        return completed.stdout.strip() if completed.returncode == 0 else ""

    def discover(self) -> list[dict[str, Any]]:
        completed = subprocess.run(
            [
                self.tmux_binary,
                "list-sessions",
                "-F",
                "#{session_name}\t#{session_created}\t#{session_attached}",
            ],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        if completed.returncode != 0:
            return []
        sessions = []
        for line in completed.stdout.splitlines():
            name, created, attached = (line.split("\t") + ["", ""])[:3]
            if name.startswith("nyanya-"):
                sessions.append({"name": name, "created": created, "attached": attached == "1"})
        return sessions

    def observe(self, handle: AdapterHandle) -> AdapterObservation:
        marker = _read_marker(handle.status_file)
        if marker:
            return _marker_observation(handle, marker)
        if self.has_session(handle.tmux_session):
            pane = self.capture(handle.tmux_session)
            output = _tail(handle.stdout_file)
            if pane and pane not in output:
                output = (output + "\n" + pane).strip()
            return AdapterObservation(
                status="running",
                confidence=0.92,
                running=True,
                output_tail=output[-8000:],
                error_tail=_tail(handle.stderr_file),
                evidence=("tmux session exists",),
            )
        return AdapterObservation(
            status="lost",
            confidence=0.55,
            running=False,
            output_tail=_tail(handle.stdout_file),
            error_tail=_tail(handle.stderr_file),
            evidence=("tmux session absent", "completion marker missing"),
        )

    def cancel(self, handle: AdapterHandle, grace_seconds: float = 5.0) -> AdapterObservation:
        if self.has_session(handle.tmux_session):
            subprocess.run(
                [self.tmux_binary, "kill-session", "-t", handle.tmux_session],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=max(5.0, grace_seconds),
                check=False,
            )
        return AdapterObservation(
            status="cancelled",
            confidence=0.98,
            running=False,
            exit_code=-15,
            output_tail=_tail(handle.stdout_file),
            error_tail=_tail(handle.stderr_file),
            evidence=("tmux kill-session completed",),
        )


class OrcaAdapter:
    """Run commands in Orca-managed terminals with a tmux offline fallback."""

    name = "orca"
    capabilities = AdapterCapabilities(
        persistent=True,
        reconnect=True,
        cancel=True,
        output_tail=True,
        artifact_collection=True,
        requires_interactive_auth=True,
    )

    def __init__(
        self,
        binary: str = "orca",
        *,
        fallback_to_tmux: bool | None = None,
        tmux_adapter: TmuxAdapter | None = None,
    ) -> None:
        self.binary = shutil.which(binary) or binary
        if fallback_to_tmux is None:
            fallback_to_tmux = os.getenv("NYANYA_ORCA_TMUX_FALLBACK", "true").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        self.fallback_to_tmux = fallback_to_tmux
        self.tmux_adapter = tmux_adapter or TmuxAdapter()

    def _run_json(self, args: list[str], *, timeout: float = 10.0) -> dict[str, Any]:
        completed = subprocess.run(
            [self.binary, *args, "--json"],
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        raw = (completed.stdout or completed.stderr).strip()
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Orca returned non-JSON output: {raw[:300]}") from exc
        if completed.returncode != 0 or not payload.get("ok", False):
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            detail = error.get("message") or raw or f"Orca exited with {completed.returncode}"
            raise RuntimeError(str(detail))
        return payload

    def probe(self) -> dict[str, Any]:
        if shutil.which(self.binary) is None and not Path(self.binary).exists():
            return {"available": False, "reachable": False, "adapter": self.name}
        try:
            payload = self._run_json(["status"], timeout=8)
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            return {
                "available": True,
                "reachable": False,
                "error": f"{type(exc).__name__}: {exc}",
                "fallback_available": self.fallback_to_tmux
                and bool(self.tmux_adapter.probe().get("available")),
                "adapter": self.name,
            }
        result = payload.get("result", {})
        runtime = result.get("runtime", {})
        return {
            "available": True,
            "reachable": bool(runtime.get("reachable")),
            "runtime_state": runtime.get("state", "unknown"),
            "runtime_id": runtime.get("runtimeId", ""),
            "fallback_available": self.fallback_to_tmux
            and bool(self.tmux_adapter.probe().get("available")),
            "adapter": self.name,
        }

    @staticmethod
    def _command_text(request: AdapterRequest, status_file: Path, stdout_file: Path, stderr_file: Path) -> str:
        environment = []
        for key, value in sorted(request.env.items()):
            if not ENV_NAME_RE.fullmatch(key):
                raise ValueError(f"Invalid environment variable name: {key}")
            environment.append(f"{key}={shlex.quote(value)}")
        runner = _runner_command(request, status_file)
        command = " ".join([*environment, shlex.join(runner)]).strip()
        return (
            command
            + " >> "
            + shlex.quote(str(stdout_file))
            + " 2>> "
            + shlex.quote(str(stderr_file))
        )

    def _set_progress(self, selector: str, *, comment: str, status: str) -> None:
        try:
            self._run_json(
                [
                    "worktree",
                    "set",
                    "--worktree",
                    selector,
                    "--comment",
                    comment,
                    "--workspace-status",
                    status,
                ],
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError, RuntimeError):
            pass

    def _fallback_handle(self, request: AdapterRequest) -> AdapterHandle:
        fallback = self.tmux_adapter.start(request)
        return AdapterHandle(
            adapter_type=self.name,
            execution_id=fallback.execution_id,
            external_id=fallback.external_id,
            pid=fallback.pid,
            tmux_session=fallback.tmux_session,
            started_at=fallback.started_at,
            status_file=fallback.status_file,
            stdout_file=fallback.stdout_file,
            stderr_file=fallback.stderr_file,
            metadata={
                **fallback.metadata,
                "transport": "tmux-fallback",
                "fallback_handle": fallback.to_dict(),
            },
        )

    def start(self, request: AdapterRequest) -> AdapterHandle:
        cwd, output_dir = _validate_request(request)
        probe = self.probe()
        if not probe.get("reachable"):
            if self.fallback_to_tmux and self.tmux_adapter.probe().get("available"):
                return self._fallback_handle(request)
            raise RuntimeError(f"Orca runtime is unavailable: {probe.get('error', probe.get('runtime_state'))}")

        status_file = output_dir / "status.json"
        stdout_file = output_dir / "stdout.log"
        stderr_file = output_dir / "stderr.log"
        worktree_selector = f"path:{cwd}"
        payload = self._run_json(
            [
                "terminal",
                "create",
                "--worktree",
                worktree_selector,
                "--title",
                f"NyaNya {request.execution_id}"[:80],
                "--command",
                self._command_text(request, status_file, stdout_file, stderr_file),
            ]
        )
        terminal = payload.get("result", {}).get("terminal", {})
        terminal_handle = str(terminal.get("handle", ""))
        if not terminal_handle:
            raise RuntimeError("Orca terminal create response omitted the terminal handle")
        self._set_progress(
            worktree_selector,
            comment=f"NyaNya execution {request.execution_id} is running",
            status="in-progress",
        )
        return AdapterHandle(
            adapter_type=self.name,
            execution_id=request.execution_id,
            external_id=terminal_handle,
            pid=None,
            tmux_session="",
            started_at=now_iso(),
            status_file=str(status_file),
            stdout_file=str(stdout_file),
            stderr_file=str(stderr_file),
            metadata={
                "timeout_seconds": request.timeout_seconds,
                "transport": "orca",
                "worktree_selector": worktree_selector,
                "worktree_id": terminal.get("worktreeId", ""),
                "tab_id": terminal.get("tabId", ""),
            },
        )

    def observe(self, handle: AdapterHandle) -> AdapterObservation:
        if handle.metadata.get("transport") == "tmux-fallback":
            fallback = AdapterHandle(**handle.metadata["fallback_handle"])
            observation = self.tmux_adapter.observe(fallback)
            return AdapterObservation(
                **{
                    **observation.__dict__,
                    "evidence": (*observation.evidence, "Orca offline tmux fallback"),
                }
            )

        marker = _read_marker(handle.status_file)
        if marker:
            observation = _marker_observation(handle, marker)
            selector = str(handle.metadata.get("worktree_selector", ""))
            if selector:
                self._set_progress(
                    selector,
                    comment=f"NyaNya execution {handle.execution_id} {observation.status}",
                    status="completed" if observation.status == "succeeded" else "in-review",
                )
            return AdapterObservation(
                **{
                    **observation.__dict__,
                    "evidence": (*observation.evidence, "Orca terminal completion marker"),
                }
            )
        try:
            payload = self._run_json(
                ["terminal", "show", "--terminal", handle.external_id], timeout=8
            )
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            return AdapterObservation(
                status="stale",
                confidence=0.35,
                running=True,
                output_tail=_tail(handle.stdout_file),
                error_tail=_tail(handle.stderr_file),
                evidence=(f"Orca runtime unavailable: {type(exc).__name__}",),
            )
        terminal = payload.get("result", {}).get("terminal", {})
        if terminal.get("connected", False):
            return AdapterObservation(
                status="running",
                confidence=0.9,
                running=True,
                output_tail=_tail(handle.stdout_file),
                error_tail=_tail(handle.stderr_file),
                evidence=("Orca terminal is connected",),
            )
        return AdapterObservation(
            status="stale",
            confidence=0.55,
            running=True,
            output_tail=_tail(handle.stdout_file),
            error_tail=_tail(handle.stderr_file),
            evidence=("Orca terminal exists but is disconnected",),
        )

    def cancel(self, handle: AdapterHandle, grace_seconds: float = 5.0) -> AdapterObservation:
        if handle.metadata.get("transport") == "tmux-fallback":
            fallback = AdapterHandle(**handle.metadata["fallback_handle"])
            observation = self.tmux_adapter.cancel(fallback, grace_seconds=grace_seconds)
            return AdapterObservation(
                **{
                    **observation.__dict__,
                    "evidence": (*observation.evidence, "Orca offline tmux fallback"),
                }
            )
        try:
            self._run_json(
                ["terminal", "close", "--terminal", handle.external_id, "--tab"],
                timeout=max(5.0, grace_seconds),
            )
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            return AdapterObservation(
                status="lost",
                confidence=0.35,
                running=False,
                output_tail=_tail(handle.stdout_file),
                error_tail=_tail(handle.stderr_file),
                evidence=(f"Orca cancellation could not be confirmed: {type(exc).__name__}",),
            )
        selector = str(handle.metadata.get("worktree_selector", ""))
        if selector:
            self._set_progress(
                selector,
                comment=f"NyaNya execution {handle.execution_id} cancelled",
                status="in-review",
            )
        return AdapterObservation(
            status="cancelled",
            confidence=0.98,
            running=False,
            exit_code=-15,
            output_tail=_tail(handle.stdout_file),
            error_tail=_tail(handle.stderr_file),
            evidence=("Orca terminal tab close completed",),
        )


class CodexAdapter(ManagedSubprocessAdapter):
    name = "codex"
    capabilities = AdapterCapabilities(
        persistent=False,
        reconnect=True,
        cancel=True,
        output_tail=True,
        artifact_collection=True,
        requires_interactive_auth=True,
    )

    def __init__(self, binary: str = "codex") -> None:
        super().__init__()
        self.binary = shutil.which(binary) or binary

    def probe(self) -> dict[str, Any]:
        version = subprocess.run(
            [self.binary, "--version"], text=True, capture_output=True, timeout=5, check=False
        )
        auth = subprocess.run(
            [self.binary, "login", "status"], text=True, capture_output=True, timeout=10, check=False
        )
        return {
            "available": version.returncode == 0,
            "version": (version.stdout or version.stderr).strip(),
            "authenticated": auth.returncode == 0,
            "auth_summary": (auth.stdout or auth.stderr).strip()[:300],
            "adapter": self.name,
        }

    def build_request(
        self,
        *,
        execution_id: str,
        prompt: str,
        cwd: Path,
        write: bool = False,
        model: str = "",
        timeout_seconds: int = 600,
        output_dir: Path | None = None,
    ) -> AdapterRequest:
        profile = "nyanya-approved-write" if write else "nyanya-readonly"
        sandbox = "workspace-write" if write else "read-only"
        command = [
            self.binary,
            "exec",
            "--cd",
            str(cwd),
            "--skip-git-repo-check",
            "--ephemeral",
            "--profile",
            profile,
            "--sandbox",
            sandbox,
        ]
        if model:
            command.extend(["--model", model])
        command.append(prompt)
        return AdapterRequest(
            execution_id=execution_id,
            command=tuple(command),
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            output_dir=output_dir,
        )


class AntigravityAdapter(ManagedSubprocessAdapter):
    name = "antigravity"
    capabilities = AdapterCapabilities(
        persistent=False,
        reconnect=True,
        cancel=True,
        output_tail=True,
        artifact_collection=True,
        requires_interactive_auth=True,
    )

    def __init__(self, binary: str = "agy") -> None:
        super().__init__()
        self.binary = shutil.which(binary) or binary

    def probe(self) -> dict[str, Any]:
        version = subprocess.run(
            [self.binary, "--version"], text=True, capture_output=True, timeout=5, check=False
        )
        models = subprocess.run(
            [self.binary, "models"], text=True, capture_output=True, timeout=15, check=False
        )
        detail = (models.stdout or models.stderr).strip()
        return {
            "available": version.returncode == 0,
            "version": (version.stdout or version.stderr).strip(),
            "authenticated": models.returncode == 0 and "not signed in" not in detail.lower(),
            "auth_summary": detail[:300],
            "adapter": self.name,
        }

    def build_request(
        self,
        *,
        execution_id: str,
        prompt: str,
        cwd: Path,
        model: str = "",
        timeout_seconds: int = 600,
        output_dir: Path | None = None,
    ) -> AdapterRequest:
        command = [
            self.binary,
            "--prompt",
            prompt,
            "--print-timeout",
            f"{timeout_seconds}s",
            "--sandbox",
        ]
        if model:
            command.extend(["--model", model])
        return AdapterRequest(
            execution_id=execution_id,
            command=tuple(command),
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            output_dir=output_dir,
        )


class ArtifactCollector:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.expanduser().resolve(strict=True)
        if not is_allowed_workspace_path(self.workspace_root):
            raise PermissionError(f"Artifact workspace is outside allowed roots: {self.workspace_root}")

    def inspect(self, path: str | Path) -> dict[str, Any]:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.workspace_root / candidate
        resolved = candidate.resolve(strict=True)
        try:
            resolved.relative_to(self.workspace_root)
        except ValueError as exc:
            raise PermissionError(f"Artifact is outside workspace: {resolved}") from exc
        if not resolved.is_file():
            raise ValueError(f"Artifact is not a file: {resolved}")
        digest = hashlib.sha256()
        with resolved.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        stat = resolved.stat()
        return {
            "path": str(resolved),
            "sha256": digest.hexdigest(),
            "size_bytes": stat.st_size,
            "mime_type": mimetypes.guess_type(resolved.name)[0] or "application/octet-stream",
        }

    def record(
        self,
        path: str | Path,
        *,
        task_id: str | None = None,
        execution_id: str | None = None,
        kind: str = "file",
        db_path: str | Path | None = None,
    ) -> dict[str, Any]:
        evidence = self.inspect(path)
        return execution_store.add_artifact(
            task_id=task_id,
            execution_id=execution_id,
            kind=kind,
            db_path=db_path,
            **evidence,
        )
