"""OPS-DEPLOY-01 lifecycle evidence using isolated state and deterministic runtimes."""

import asyncio
from io import BytesIO
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from nyanya_agent import database as db, execution_store as ledger, operation_store as store, work_queue
from nyanya_agent import discord_bridge, operation_service, operation_worker, reviewed_changes as files
from nyanya_agent import telegram_bridge
from nyanya_agent.operation_service import OperationService
from nyanya_agent.operation_spec import OperationSpec
from nyanya_agent.operation_worker import Worker
from nyanya_agent.task_outcomes import OutcomeSignal, TaskOutcome


REAL_ENSURE_WORKER = OperationService.ensure_worker


@pytest.fixture
def state(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(root))
    worker = Worker(tmp_path / "state.db", slots=1)
    yield worker, root
    worker.close()


def submit(worker, root, prompt="interrupted request", **kwargs):
    return store.submit(
        worker.path, OperationSpec(prompt=prompt, workspace=str(root), **kwargs), "operator", worker.generation
    )


def status(worker, task):
    return ledger.get_task(task["id"], db_path=worker.path)["status"]


def assert_closed(worker):
    with db.connect(worker.path) as conn:
        assert conn.execute("SELECT closed FROM operation_workers WHERE id=?", (worker.generation,)).fetchone()[0]
        assert conn.execute("SELECT count(*) FROM task_claims WHERE released=0").fetchone()[0] == 0
    assert worker.events == {}


@pytest.mark.parametrize("once", [False, True])
@pytest.mark.parametrize("explicit_cancel", [False, True])
def test_shutdown_holds_work_but_preserves_explicit_cancel_and_completion(state, once, explicit_cancel):
    worker, root = state
    completed = submit(worker, root, "already complete")
    record = store.claim(worker.path, worker.generation)
    store.finish(worker.path, record, TaskOutcome("succeeded", "saved result"))
    active = submit(worker, root)
    queued = submit(worker, root, "never started")
    cancelled_queue = submit(worker, root, "explicit queued cancellation")
    store.cancel(worker.path, cancelled_queue["id"], "operator")
    started = threading.Event()

    def invoke(*args):
        started.set()
        assert args[-1].wait(4)
        raise OutcomeSignal("cancelled", "fixture runtime confirmed termination")

    worker.invoke = invoke
    thread = threading.Thread(target=worker.run_once if once else worker.run)
    thread.start()
    try:
        assert started.wait(3)
        if explicit_cancel:
            store.cancel(worker.path, active["id"], "operator")
        worker.stop.set()
    finally:
        worker.stop.set()
        thread.join(5)
    assert not thread.is_alive()
    assert status(worker, active) == ("cancelled" if explicit_cancel else "blocked")
    assert status(worker, queued) == "blocked"
    assert status(worker, cancelled_queue) == "cancelled"
    assert status(worker, completed) == "completed"
    assert work_queue.result(worker.path, completed["id"], "operator")["response"] == "saved result"
    assert "never started" in store.explain(worker.path, queued["id"], "operator")
    if not explicit_cancel:
        explanation = store.explain(worker.path, active["id"], "operator")
        assert "interrupted request" in explanation and "flash_assessment" in explanation
        assert "사용자 취소가 아닙니다" in explanation
    assert_closed(worker)
    fresh = Worker(worker.path)
    try:
        assert store.claim(worker.path, fresh.generation) is None
    finally:
        fresh.close()


def test_explicit_cancel_without_worker_shutdown(state):
    worker, root = state
    task = submit(worker, root)

    def invoke(*args):
        store.cancel(worker.path, task["id"], "operator")
        assert args[-1].wait(3)
        raise OutcomeSignal("cancelled", "confirmed stopped")

    worker.invoke = invoke
    worker.run_once()
    assert not worker.stop.is_set()
    assert status(worker, task) == "cancelled"


def test_completed_result_during_shutdown_is_not_relabelled(state, monkeypatch):
    worker, root = state
    task = submit(worker, root)

    def perform(*_):
        worker.stop.set()
        return TaskOutcome("succeeded", "completed before shutdown")

    monkeypatch.setattr(worker, "perform", perform)
    worker.run_once()
    assert status(worker, task) == "completed"
    assert_closed(worker)


def test_run_once_already_stopped_does_not_claim(state):
    worker, root = state
    task = submit(worker, root)
    worker.stop.set()
    assert not worker.run_once()
    assert status(worker, task) == "blocked"
    with db.connect(worker.path) as conn:
        assert conn.execute("SELECT attempts FROM task_operations WHERE task_id=?", (task["id"],)).fetchone()[0] == 0
    assert_closed(worker)


def test_run_once_base_exception_stops_monitor_and_recovers(state, monkeypatch):
    worker, root = state
    task = submit(worker, root)

    def interrupt(*_):
        raise KeyboardInterrupt

    monkeypatch.setattr(worker, "perform", interrupt)
    with pytest.raises(KeyboardInterrupt):
        worker.run_once()
    assert status(worker, task) == "blocked"
    assert_closed(worker)


@pytest.mark.skipif(os.name != "posix", reason="POSIX reviewed file apply")
def test_shutdown_during_partial_apply_keeps_reconciliation_gate(state, monkeypatch):
    worker, root = state
    for name in ("first.txt", "second.txt"):
        (root / name).write_text("before")
    parent = submit(worker, root)
    record = store.claim(worker.path, worker.generation)
    plan = files.propose(
        worker.path, parent["id"], "operator", root,
        [{"path": name, "action": "modify", "content": "after", "reason": "fixture"}
         for name in ("first.txt", "second.txt")],
        files.snapshot(root),
    )
    store.finish(worker.path, record, TaskOutcome("awaiting_approval", "review files"))
    files.decide(worker.path, plan["id"], "operator", plan["plan_hash"])
    task = submit(worker, root, kind="apply", plan_id=plan["id"])
    original_replace = files.os.replace

    def replace(*args, **kwargs):
        original_replace(*args, **kwargs)
        worker.stop.set()
        assert worker.events[task["id"]].wait(3)

    monkeypatch.setattr(files.os, "replace", replace)
    worker.run_once()
    assert status(worker, task) == "blocked"
    assert files.get_plan(worker.path, plan["id"], "operator")["status"] == "uncertain"
    assert (root / "first.txt").read_text() == "after"
    assert (root / "second.txt").read_text() == "before"
    fresh = Worker(worker.path)
    try:
        with pytest.raises(ValueError, match="reconciliation"):
            store.resume(worker.path, task["id"], "operator", fresh.generation)
        with pytest.raises(ValueError, match="reconciliation"):
            store.resume(worker.path, parent["id"], "operator", fresh.generation)
        assert store.claim(worker.path, fresh.generation) is None
    finally:
        fresh.close()
    assert_closed(worker)


class UnreadyProcess:
    def __init__(self, *, cannot_reap=False):
        self.stdin = BytesIO()
        self.calls = []
        self.returncode = None
        self.cannot_reap = cannot_reap

    def poll(self):
        return self.returncode

    def terminate(self):
        self.calls.append("terminate")

    def kill(self):
        self.calls.append("kill")

    def wait(self, timeout):
        self.calls.append(("wait", timeout))
        if "kill" not in self.calls or self.cannot_reap:
            raise subprocess.TimeoutExpired("fixture worker", timeout)
        self.returncode = -9
        return self.returncode


@pytest.mark.parametrize("cannot_reap", [False, True])
def test_startup_timeout_bounds_terminate_kill_reap_and_retains_request(tmp_path, monkeypatch, cannot_reap):
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(tmp_path))
    service = OperationService(tmp_path / "state.db")
    service.ensure_worker = lambda: REAL_ENSURE_WORKER(service)
    process = UnreadyProcess(cannot_reap=cannot_reap)
    launches = []

    def launch(argv, **kwargs):
        launches.append((argv, kwargs))
        return process

    monkeypatch.setattr(operation_service.subprocess, "Popen", launch)
    ticks = iter((0, 11))
    monkeypatch.setattr(operation_service.time, "monotonic", lambda: next(ticks))
    task = service.submit("retain startup failure", tmp_path, "operator")
    assert task["status"] == "blocked"
    assert "Worker 시작 실패" in store.explain(service.path, task["id"], "operator")
    assert process.calls == ["terminate", ("wait", 5), "kill", ("wait", 3)]
    assert process.stdin.closed
    assert service.generation is None
    assert launches[0][0][-2:] == ["--parent-pid", str(os.getpid())]
    assert launches[0][1]["stdin"] == subprocess.PIPE


def test_failed_spawn_is_not_cached_as_ready(tmp_path, monkeypatch):
    service = OperationService(tmp_path / "state.db")
    launches = []

    def fail(*_args, **_kwargs):
        launches.append(1)
        raise OSError("fixture failure")

    monkeypatch.setattr(operation_service.subprocess, "Popen", fail)
    for _ in range(2):
        with pytest.raises(OSError):
            REAL_ENSURE_WORKER(service)
        assert service.generation is None
    assert len(launches) == 2


def test_parent_pipe_loss_stops_worker_and_wrong_parent_fails_closed(state):
    worker, _ = state
    read_fd, write_fd = os.pipe()
    try:
        operation_worker.watch_parent(worker, os.getppid(), read_fd)
        assert not worker.stop.wait(0.1)
        os.close(write_fd)
        write_fd = None
        assert worker.stop.wait(2)
    finally:
        if write_fd is not None:
            os.close(write_fd)
        os.close(read_fd)
    worker.stop.clear()
    operation_worker.watch_parent(worker, -1, -1)
    assert worker.stop.is_set()


@pytest.mark.skipif(os.name != "posix", reason="POSIX worker signal fixture")
@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT])
@pytest.mark.parametrize("once", [False, True])
def test_standalone_worker_main_signals_close_and_hold(tmp_path, monkeypatch, sig, once):
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(tmp_path))
    script = '''
import sys
from nyanya_agent import operation_worker as module, operation_store as store, database as db
from nyanya_agent.operation_spec import OperationSpec
from nyanya_agent.task_outcomes import OutcomeSignal
root = sys.argv.pop()
def model(*args):
    print("RUNNING", flush=True)
    assert args[-1].wait(8)
    raise OutcomeSignal("cancelled", "fixture stopped")
class FixtureWorker(module.Worker):
    def __init__(self, *args):
        super().__init__(*args, invoke=model)
        for i in range(2):
            store.submit(self.path, OperationSpec(prompt=str(i), workspace=root),
                         "operator", self.generation)
module.Worker = FixtureWorker
module.main()
with db.connect(sys.argv[sys.argv.index("--db") + 1]) as conn:
    assert conn.execute("SELECT count(*) FROM operation_workers WHERE closed=1").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM agent_tasks WHERE status='blocked'").fetchone()[0] == 2
print("CLOSED_AND_HELD", flush=True)
'''
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(operation_worker.__file__).resolve().parents[1])
    argv = [sys.executable, "-c", script, "--db", str(tmp_path / "signal.db"), "--slots", "1"]
    if once:
        argv.append("--once")
    process = subprocess.Popen(argv + [str(tmp_path)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        started = []
        reader = threading.Thread(target=lambda: started.append(process.stdout.readline()), daemon=True)
        reader.start()
        reader.join(5)
        assert not reader.is_alive() and started == ["RUNNING\n"]
        process.send_signal(sig)
        output, errors = process.communicate(timeout=10)
        assert process.returncode == 0 and "CLOSED_AND_HELD" in output
        assert not errors
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)


@pytest.mark.skipif(os.name != "posix", reason="POSIX controller death and inherited pipe fixture")
def test_real_controller_death_closes_orphan_worker_without_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(tmp_path))
    child = '''
import os, sys
from nyanya_agent.operation_worker import Worker, watch_parent
from nyanya_agent.operation_spec import OperationSpec
from nyanya_agent import operation_store as store, execution_store as ledger
from nyanya_agent.task_outcomes import OutcomeSignal
def model(*args):
    print("RUNNING", flush=True)
    assert args[-1].wait(8)
    raise OutcomeSignal("cancelled", "fixture stopped")
worker = Worker(sys.argv[1], slots=1, invoke=model)
tasks = [store.submit(worker.path, OperationSpec(prompt=str(i), workspace=sys.argv[2]),
                      "operator", worker.generation) for i in range(2)]
watch_parent(worker, int(sys.argv[3]), 0)
worker.run()
assert all(ledger.get_task(t["id"], db_path=worker.path)["status"] == "blocked" for t in tasks)
print("CLOSED_AND_HELD", flush=True)
'''
    controller = '''
import os, subprocess, sys
process = subprocess.Popen([sys.executable, "-c", sys.argv[1], sys.argv[2], sys.argv[3], str(os.getpid())],
                           stdin=subprocess.PIPE)
process.wait(timeout=12)
'''
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(operation_worker.__file__).resolve().parents[1])
    process = subprocess.Popen(
        [sys.executable, "-c", controller, child, str(tmp_path / "orphan.db"), str(tmp_path)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        # A reader thread bounds startup even if the fixture fails before printing.
        started = []
        reader = threading.Thread(target=lambda: started.append(process.stdout.readline()), daemon=True)
        reader.start()
        reader.join(5)
        assert not reader.is_alive() and started == ["RUNNING\n"]
        process.kill()  # Only the test's own Popen controller, never a discovered PID.
        output, errors = process.communicate(timeout=10)
        assert "CLOSED_AND_HELD" in output
        assert not errors
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=15)


class FakeClient:
    def __init__(self, start):
        self.action = start
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        self.closed = True

    async def start(self, _token):
        await self.action()


@pytest.mark.parametrize("termination", ["sigterm", "cancel", "failure"])
def test_discord_orderly_close_is_off_loop_and_restores_signal(monkeypatch, termination):
    registered = []
    previous = object()
    original_signal = signal.signal

    def register(sig, handler):
        if sig != signal.SIGTERM:
            return original_signal(sig, handler)
        registered.append((sig, handler))
        return previous

    monkeypatch.setattr(discord_bridge.signal, "signal", register)
    loop_thread = threading.get_ident()
    ticks = threading.Event()
    closed = []

    async def start():
        if termination == "failure":
            raise RuntimeError("fixture start failure")
        if termination == "sigterm":
            registered[0][1]()
            registered[0][1]()  # Repeated stop must not interrupt cleanup.
        else:
            asyncio.current_task().cancel()
        await asyncio.sleep(0)

    client = FakeClient(start)

    def close():
        assert client.closed
        assert threading.get_ident() != loop_thread
        assert ticks.wait(2), "store cleanup blocked the event loop"
        closed.append(True)

    async def run():
        asyncio.get_running_loop().call_later(0.03, ticks.set)
        await discord_bridge.run_client(client, "fixture", SimpleNamespace(close=close))

    if termination == "failure":
        with pytest.raises(RuntimeError, match="fixture"):
            asyncio.run(run())
    elif termination == "cancel":
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(run())
    else:
        asyncio.run(run())
    assert closed == [True]
    assert registered[-1] == (signal.SIGTERM, previous)
    assert all(sig == signal.SIGTERM for sig, _ in registered)  # SIGINT stays asyncio-owned.


def test_discord_does_not_register_signals_off_main_thread(monkeypatch):
    calls = []
    monkeypatch.setattr(discord_bridge.signal, "signal", lambda *_: calls.append("signal"))

    async def start():
        return

    thread = threading.Thread(
        target=lambda: asyncio.run(discord_bridge.run_client(
            FakeClient(start), "fixture", SimpleNamespace(close=lambda: calls.append("closed"))
        ))
    )
    thread.start()
    thread.join(3)
    assert not thread.is_alive()
    assert calls == ["closed"]


@pytest.mark.parametrize("main_thread", [False, True])
def test_telegram_sigterm_cleanup_and_thread_guard(monkeypatch, main_thread):
    registered = []
    closed = []
    previous = object()
    monkeypatch.setattr(telegram_bridge, "parse_args", lambda: SimpleNamespace(config=None, check_config=False))
    monkeypatch.setattr(telegram_bridge, "load_runtime_config", lambda _: {})
    monkeypatch.setattr(telegram_bridge, "env_first", lambda *_: "fixture")
    monkeypatch.setattr(telegram_bridge, "NyaNyaConversationStore", lambda _: SimpleNamespace(close=lambda: closed.append(1)))

    def register(sig, handler):
        registered.append((sig, handler))
        return previous

    def run(_):
        if main_thread:
            registered[0][1]()
        return 0

    monkeypatch.setattr(telegram_bridge.signal, "signal", register)
    monkeypatch.setattr(telegram_bridge.TelegramBridge, "run", run)
    if main_thread:
        assert telegram_bridge.main() == 0
        assert registered[-1] == (signal.SIGTERM, previous)
    else:
        thread = threading.Thread(target=telegram_bridge.main)
        thread.start()
        thread.join(3)
        assert not thread.is_alive()
        assert not registered
    assert closed == [1]
