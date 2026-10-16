"""Bounded subprocess ownership; terminate the owned group and reap the parent."""

import os
import signal
import subprocess
import time
import tempfile
import stat
from pathlib import Path
from nyanya_agent.context_security import child_environment
from nyanya_agent.task_outcomes import OutcomeSignal


MAX_OUTPUT_BYTES = 4_000_000


def _check_result_file(path):
    if path is None:
        return
    try:
        info = Path(path).lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise OutcomeSignal("blocked", "모델 최종 응답 파일을 안전하게 확인하지 못했습니다.") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_OUTPUT_BYTES:
        raise OutcomeSignal("blocked", "모델 최종 응답 파일이 안전한 형식 또는 크기 제한을 벗어났습니다.")


def _require_result_file_support():
    if os.name != "posix" or not all(hasattr(os, flag) for flag in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK")):
        raise OutcomeSignal("blocked", "안전한 모델 최종 응답 읽기는 POSIX 파일 검증이 필요합니다.")


def read_result_file(path):
    """Read a bounded no-follow inode on POSIX; unsupported platforms stay held."""
    _require_result_file_support()
    path = Path(path)
    try:
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise OutcomeSignal("blocked", "모델 최종 응답 디렉터리를 안전하게 열지 못했습니다.") from exc
    try:
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            return ""
        except OSError as exc:
            raise OutcomeSignal("blocked", "모델 최종 응답 파일을 안전하게 열지 못했습니다.") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_OUTPUT_BYTES:
                raise OutcomeSignal("blocked", "모델 최종 응답 파일이 안전한 형식 또는 크기 제한을 벗어났습니다.")
            with os.fdopen(os.dup(fd), "rb") as stream:
                value = stream.read(MAX_OUTPUT_BYTES + 1)
            if len(value) > MAX_OUTPUT_BYTES:
                raise OutcomeSignal("blocked", "모델 최종 응답이 크기 제한을 초과했습니다.")
            return value.decode("utf-8", errors="replace")
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def run_command(command, *, cwd, timeout, cancel_event=None, provider=None, result_file=None):
    if result_file is not None:
        _require_result_file_support()
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        # Prompts are arguments; never inherit the worker's open parent-liveness pipe.
        proc = subprocess.Popen(
            command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=output, stderr=errors,
            start_new_session=(os.name == "posix"), env=child_environment(provider),
        )
        deadline = time.monotonic() + timeout
        try:
            while True:
                _check_result_file(result_file)
                reason = (
                    "cancelled"
                    if cancel_event and cancel_event.is_set()
                    else "timed_out"
                    if time.monotonic() >= deadline
                    else ""
                )
                oversized = max(os.fstat(output.fileno()).st_size, os.fstat(errors.fileno()).st_size) > MAX_OUTPUT_BYTES
                if reason or oversized:
                    terminate(proc)
                    if oversized:
                        raise OutcomeSignal("blocked", "모델 출력이 제한을 초과했습니다. 요청 범위를 줄여주세요.")
                    raise OutcomeSignal(
                        reason, "실행을 취소했습니다." if reason == "cancelled" else "실행 제한시간을 초과했습니다."
                    )
                try:
                    proc.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    continue
                _check_result_file(result_file)
                output.seek(0)
                errors.seek(0)
                if max(os.fstat(output.fileno()).st_size, os.fstat(errors.fileno()).st_size) > MAX_OUTPUT_BYTES:
                    raise OutcomeSignal("blocked", "모델 출력이 제한을 초과했습니다.")
                return (
                    proc.returncode,
                    output.read(MAX_OUTPUT_BYTES).decode("utf-8", errors="replace"),
                    errors.read(MAX_OUTPUT_BYTES).decode("utf-8", errors="replace"),
                )
        finally:
            if proc.poll() is None:
                terminate(proc)


def terminate(proc):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            if os.name == "posix":
                os.killpg(proc.pid, sig)
            elif sig == signal.SIGTERM:
                proc.terminate()
            else:
                proc.kill()
        except ProcessLookupError:
            pass
        except PermissionError as exc:
            raise OutcomeSignal("blocked", "프로세스 종료 권한이 없어 종료 확인이 필요합니다.") from exc
        try:
            proc.wait(timeout=2)
            if os.name == "posix":
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            return
        except subprocess.TimeoutExpired:
            continue
    raise OutcomeSignal("blocked", "프로세스 종료를 확인하지 못했습니다. 재실행하지 마세요.")
