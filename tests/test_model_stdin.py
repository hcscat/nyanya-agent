"""Model commands must not inherit the worker's open controller-liveness pipe."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from nyanya_agent import process_runner


@pytest.mark.skipif(os.name != "posix", reason="POSIX liveness pipe and bounded signal cleanup")
@pytest.mark.parametrize("payload", [b"", b"controller-liveness"])
def test_model_stdin_eof_preserves_open_controller_pipe(tmp_path, payload):
    # The alarm is a last-resort bound if the caller itself fails during cleanup.
    child = """
import signal, sys
signal.alarm(8)
data = sys.stdin.buffer.read()
print(repr(data))
print(sys.argv[1], file=sys.stderr)
"""
    caller = """
import json, signal, sys
from nyanya_agent.process_runner import run_command
from nyanya_agent.task_outcomes import OutcomeSignal

def stop(*_):
    raise SystemExit(1)  # Unwind run_command's owned-process cleanup.

signal.signal(signal.SIGTERM, stop)
try:
    result = run_command([sys.executable, "-c", sys.argv[1], "argument-prompt"],
                         cwd=sys.argv[2], timeout=2)
except OutcomeSignal as exc:
    result = {"status": exc.outcome.status}
print(json.dumps(result), flush=True)
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(process_runner.__file__).resolve().parents[1])
    read_fd, write_fd = os.pipe()
    process = None
    try:
        if payload:
            assert os.write(write_fd, payload) == len(payload)
        process = subprocess.Popen(
            [sys.executable, "-c", caller, child, str(tmp_path)],
            stdin=read_fd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, text=True,
        )
        # Passing an fd rather than PIPE keeps communicate() from closing the
        # controller's write end. It stays open through every assertion below.
        output, errors = process.communicate(timeout=12)
        assert process.returncode == 0, errors
        assert errors == ""
        assert json.loads(output) == [0, "b''\n", "argument-prompt\n"]
        # No model read may steal bytes from the controller's pipe. With the
        # writer still alive, an exhausted pipe must block rather than return EOF.
        os.set_blocking(read_fd, False)
        if payload:
            assert os.read(read_fd, len(payload)) == payload
        with pytest.raises(BlockingIOError):
            os.read(read_fd, 1)
    finally:
        try:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate(timeout=3)
        finally:
            os.close(read_fd)
            os.close(write_fd)
