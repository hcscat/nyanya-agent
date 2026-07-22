from __future__ import annotations

from pathlib import Path
import subprocess

from nyanya_agent import manager


def test_bootstrap_with_retry_recovers_launchd_transition(monkeypatch):
    results = iter(
        [
            subprocess.CompletedProcess(["launchctl"], 5, "", "transition"),
            subprocess.CompletedProcess(["launchctl"], 0, "", ""),
        ]
    )
    calls: list[Path] = []
    delays: list[float] = []

    def fake_bootstrap(path):
        calls.append(path)
        return next(results)

    monkeypatch.setattr(manager, "bootstrap", fake_bootstrap)
    monkeypatch.setattr(manager.time, "sleep", delays.append)

    result = manager.bootstrap_with_retry(Path("dashboard.plist"))

    assert result.returncode == 0
    assert len(calls) == 2
    assert delays == [0.25]


def test_bootstrap_with_retry_does_not_retry_other_errors(monkeypatch):
    monkeypatch.setattr(
        manager,
        "bootstrap",
        lambda path: subprocess.CompletedProcess(["launchctl"], 78, "", "invalid plist"),
    )
    delays: list[float] = []
    monkeypatch.setattr(manager.time, "sleep", delays.append)

    result = manager.bootstrap_with_retry(Path("dashboard.plist"))

    assert result.returncode == 78
    assert delays == []
