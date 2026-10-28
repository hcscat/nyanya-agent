"""Fake subprocesses only; no authentication or provider invocation."""

import os
import sys
import time

import pytest

from nyanya_agent import process_runner as runner
# Capture before the global test fixture disables real model calls.
from nyanya_agent.model_routing import invoke as LOCAL_INVOKE
from nyanya_agent.task_outcomes import OutcomeSignal


def test_final_file_limit_stops_running_process_and_blocks_result(tmp_path):
    output = tmp_path / "final.txt"
    marker = tmp_path / "should-not-exist"
    code = (
        'from pathlib import Path; import sys,time; '
        'Path(sys.argv[1]).write_bytes(b"x" * 5000001); time.sleep(3); '
        'Path(sys.argv[2]).touch()'
    )
    started = time.monotonic()
    with pytest.raises(OutcomeSignal) as result:
        runner.run_command([sys.executable, "-c", code, str(output), str(marker)],
                           cwd=tmp_path, timeout=10, result_file=output)
    assert result.value.outcome.status == "blocked"
    assert time.monotonic() - started < 3
    assert not marker.exists()


def test_final_file_limit_checked_after_fast_exit(tmp_path):
    output = tmp_path / "final.txt"
    code = 'from pathlib import Path; import sys; Path(sys.argv[1]).write_bytes(b"x" * 5000001)'
    with pytest.raises(OutcomeSignal):
        runner.run_command([sys.executable, "-c", code, str(output)], cwd=tmp_path, timeout=3, result_file=output)


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "directory", "oversize"])
def test_final_reader_rejects_unsafe_entries_without_unbounded_read(tmp_path, kind):
    output = tmp_path / "final.txt"
    target = tmp_path / "target"
    target.write_text("synthetic-private-value")
    if kind == "symlink":
        output.symlink_to(target)
    elif kind == "hardlink":
        os.link(target, output)
    elif kind == "fifo":
        os.mkfifo(output)
    elif kind == "directory":
        output.mkdir()
    else:
        with output.open("wb") as stream:
            stream.truncate(runner.MAX_OUTPUT_BYTES + 1)
    with pytest.raises(OutcomeSignal):
        runner.read_result_file(output)


def test_final_reader_accepts_limit_and_missing_file(tmp_path):
    output = tmp_path / "final.txt"
    assert runner.read_result_file(output) == ""
    output.write_bytes(b"x" * runner.MAX_OUTPUT_BYTES)
    assert len(runner.read_result_file(output)) == runner.MAX_OUTPUT_BYTES


def test_reader_still_bounds_file_that_grew_after_stat(tmp_path, monkeypatch):
    from types import SimpleNamespace

    output = tmp_path / "final.txt"
    output.write_bytes(b"x" * (runner.MAX_OUTPUT_BYTES + 1))
    real_fstat = os.fstat

    def stale_size(fd):
        info = real_fstat(fd)
        return SimpleNamespace(st_mode=info.st_mode, st_nlink=info.st_nlink, st_size=0)

    monkeypatch.setattr(os, "fstat", stale_size)
    with pytest.raises(OutcomeSignal):
        runner.read_result_file(output)


def test_codex_invocation_uses_bounded_final_file(tmp_path, monkeypatch):
    from nyanya_agent import model_routing

    fake = tmp_path / "fake-codex"
    fake.write_text(
        "#!" + sys.executable + "\nimport sys\nfrom pathlib import Path\n"
        "Path(sys.argv[sys.argv.index('-o') + 1]).write_bytes(b'x' * 5000001)\n"
    )
    fake.chmod(0o700)
    monkeypatch.setattr(model_routing, "resolve_codex_cli", lambda: str(fake))
    with pytest.raises(OutcomeSignal) as result:
        LOCAL_INVOKE("astra", "Inspect this synthetic fixture", tmp_path, 3, None)
    assert result.value.outcome.status == "blocked"


@pytest.mark.parametrize(
    "profile,model,effort",
    [("luna", "gpt-6-luna", "xhigh"), ("sol", "gpt-6.1-sol", "high"), ("astra", "gpt-6.1-sol", "high")],
)
def test_codex_profile_uses_exact_model_and_effort_arguments(tmp_path, monkeypatch, profile, model, effort):
    from nyanya_agent import model_routing

    calls = []
    cancel = object()
    monkeypatch.setattr(model_routing, "resolve_codex_cli", lambda: "/synthetic/codex")

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        kwargs["result_file"].write_text("synthetic result")
        return 0, "", ""

    monkeypatch.setattr(runner, "run_command", fake_run)
    assert LOCAL_INVOKE(profile, "Inspect synthetic fixture", tmp_path, 23, cancel) == "synthetic result"
    assert len(calls) == 1
    command, kwargs = calls[0]
    output = kwargs["result_file"]
    assert command == [
        "/synthetic/codex", "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
        "-s", "read-only", "-m", model, "-c", f'model_reasoning_effort="{effort}"',
        "-o", str(output), "Inspect synthetic fixture",
    ]
    assert kwargs == dict(cwd=tmp_path, timeout=23, cancel_event=cancel, provider="codex", result_file=output)


def test_flash_profile_keeps_exact_assessment_arguments(tmp_path, monkeypatch):
    from nyanya_agent import model_routing

    calls = []
    monkeypatch.setattr(model_routing.shutil, "which", lambda _: "/synthetic/agy")

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return 0, "synthetic assessment", ""

    monkeypatch.setattr(runner, "run_command", fake_run)
    assert LOCAL_INVOKE("flash", "Inspect synthetic fixture", tmp_path, 23, None) == "synthetic assessment"
    assert calls == [([
        "/synthetic/agy", "--prompt", "Inspect synthetic fixture", "--model", "gemini-3.8-flash-medium",
        "--effort", "medium", "--mode", "plan", "--sandbox", "--disable-slash-commands", "--print-timeout", "23s",
    ], dict(cwd=tmp_path, timeout=23, cancel_event=None, provider="agy"))]


@pytest.mark.parametrize("profile", ["luna", "sol", "astra"])
def test_rejected_codex_model_is_blocked_without_fallback(tmp_path, monkeypatch, profile):
    from nyanya_agent import model_routing

    calls = []
    monkeypatch.setattr(model_routing, "resolve_codex_cli", lambda: "/synthetic/codex")

    def reject(command, **kwargs):
        calls.append(command)
        return 1, "", "model unavailable"

    monkeypatch.setattr(runner, "run_command", reject)
    with pytest.raises(OutcomeSignal) as result:
        LOCAL_INVOKE(profile, "Inspect synthetic fixture", tmp_path, 23, None)
    assert result.value.outcome.status == "blocked"
    assert model_routing.PROFILES[profile].model in result.value.outcome.text
    assert len(calls) == 1
    assert calls[0][calls[0].index("-m") + 1] == model_routing.PROFILES[profile].model


@pytest.mark.parametrize('platform', ['nt', 'posix-without-flags'])
def test_final_reader_unsupported_platform_is_explicitly_held(tmp_path, monkeypatch, platform):
    from types import SimpleNamespace

    unsupported_os = SimpleNamespace(name='nt' if platform == 'nt' else 'posix')
    monkeypatch.setattr(runner, 'os', unsupported_os)
    with pytest.raises(OutcomeSignal) as result:
        runner.read_result_file(tmp_path / 'final.txt')
    assert result.value.outcome.status == 'blocked'
    assert 'POSIX' in result.value.outcome.text


def test_unsupported_result_platform_fails_before_spawning(monkeypatch):
    from nyanya_agent import process_runner
    from nyanya_agent.task_outcomes import OutcomeSignal

    monkeypatch.setattr(process_runner.os, 'name', 'nt')
    monkeypatch.setattr(process_runner.subprocess, 'Popen', lambda *a, **k: pytest.fail('spawned unsupported runner'))
    with pytest.raises(OutcomeSignal, match='POSIX'):
        process_runner.run_command(['unused'], cwd='.', timeout=1, result_file='result.txt')
