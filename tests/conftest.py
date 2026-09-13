"""Never let tests load operator credentials or migrate the live operational DB."""

import os
import pytest
from pathlib import Path
import tempfile


def pytest_configure(config):
    config._nyanya_test_state = tempfile.TemporaryDirectory(prefix="nyanya-tests-")
    config._nyanya_original_env = {key: value for key, value in os.environ.items() if key.startswith("NYANYA_")}
    for key in config._nyanya_original_env:
        os.environ.pop(key)
    root = Path(config._nyanya_test_state.name)
    os.environ.update(
        {
            "NYANYA_HOME": str(root),
            "NYANYA_ENV_FILE": str(root / "absent.env"),
            "NYANYA_DASHBOARD_DB_PATH": str(root / "test.db"),
            "NYANYA_WORKSPACE_ROOTS": str(Path(__file__).resolve().parents[1]) + "," + str(root),
            "NYANYA_MEMORY_RETRIEVAL_ENABLED": "false",
        }
    )


def pytest_unconfigure(config):
    for key in list(os.environ):
        if key.startswith("NYANYA_"):
            os.environ.pop(key)
    os.environ.update(config._nyanya_original_env)
    config._nyanya_test_state.cleanup()


@pytest.fixture(autouse=True)
def prevent_live_model_calls(monkeypatch):
    from nyanya_agent import model_routing
    from nyanya_agent.operation_service import OperationService

    def denied(*args, **kwargs):
        raise AssertionError("Test must explicitly supply a fake model/worker; live invocation prohibited")

    monkeypatch.setattr(model_routing, "invoke", denied)
    monkeypatch.setattr(OperationService, "ensure_worker", denied)


@pytest.fixture
def fixture_worker(monkeypatch):
    """Real worker threads/DB, deterministic model, no external process or account."""
    import json
    import threading
    from nyanya_agent.operation_service import OperationService
    from nyanya_agent.operation_worker import Worker

    workers = []

    def model(profile, prompt, *args):
        if prompt.startswith("Return only JSON"):
            return json.dumps(dict(importance=2, impact=1, complexity=2, reason="fixture"))
        return json.dumps(dict(summary="done", changes=[]))

    def start(service):
        if service.generation:
            return service.generation
        worker = Worker(service.path, invoke=model)
        service.generation = worker.generation
        thread = threading.Thread(target=worker.run)
        workers.append((worker, thread))
        thread.start()
        return worker.generation

    monkeypatch.setattr(OperationService, "ensure_worker", start)
    yield workers
    for worker, thread in workers:
        worker.stop.set()
        thread.join(timeout=5)
        assert not thread.is_alive()
