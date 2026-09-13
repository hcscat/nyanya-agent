"""Bounded subprocess ownership; terminate the owned group and reap the parent."""

import os
import signal
import subprocess
import time
import tempfile
from nyanya_agent.task_outcomes import OutcomeSignal


def run_command(command, *, cwd, timeout, cancel_event=None):
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        # Prompts are arguments; never inherit the worker's open parent-liveness pipe.
        proc = subprocess.Popen(
            command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=output, stderr=errors,
            start_new_session=(os.name == "posix"),
        )
        deadline = time.monotonic() + timeout
        try:
            while True:
                reason = (
                    "cancelled"
                    if cancel_event and cancel_event.is_set()
                    else "timed_out"
                    if time.monotonic() >= deadline
                    else ""
                )
                oversized = max(os.fstat(output.fileno()).st_size, os.fstat(errors.fileno()).st_size) > 4_000_000
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
                output.seek(0)
                errors.seek(0)
                if max(os.fstat(output.fileno()).st_size, os.fstat(errors.fileno()).st_size) > 4_000_000:
                    raise OutcomeSignal("blocked", "모델 출력이 제한을 초과했습니다.")
                return (
                    proc.returncode,
                    output.read(4_000_000).decode("utf-8", errors="replace"),
                    errors.read(4_000_000).decode("utf-8", errors="replace"),
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
