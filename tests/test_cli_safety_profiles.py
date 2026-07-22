from __future__ import annotations

from pathlib import Path
import urllib.request

import pytest

from nyanya_agent import bridge_runtime
from nyanya_agent import core


def test_backend_request_rejects_non_http_scheme():
    with pytest.raises(ValueError, match="http or https"):
        core.request_json("file:///etc/passwd", None, 1)


def test_backend_request_accepts_https(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"ok":true}'

    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: FakeResponse())

    assert core.request_json("https://example.com/health", None, 1) == {"ok": True}


def test_antigravity_uses_sandbox_by_default(monkeypatch):
    captured: dict[str, object] = {}

    monkeypatch.setattr(core, "resolve_gemini_like_cli", lambda value: "/opt/homebrew/bin/agy")
    monkeypatch.setattr(core, "format_cli_conversation", lambda config, messages: "hello")

    def fake_run(command, **kwargs):
        captured["command"] = command
        return 0, "ok", ""

    monkeypatch.setattr(core, "run_cancellable_command", fake_run)
    result = core.gemini_chat_once({"gemini_cli": "agy", "timeout_seconds": 30}, [])

    assert result == "ok"
    assert "--sandbox" in captured["command"]


def test_codex_read_only_invocation_uses_nyanya_profile(monkeypatch):
    captured: dict[str, object] = {}
    workdir = Path(__file__).resolve().parents[1]

    monkeypatch.setenv("NYANYA_CODEX_ENABLED", "true")
    monkeypatch.delenv("NYANYA_CODEX_PROFILE", raising=False)
    monkeypatch.setattr(bridge_runtime, "resolve_executable", lambda value: "/usr/local/bin/codex")
    monkeypatch.setattr(
        bridge_runtime,
        "classify_request_risk",
        lambda prompt, workdir=None: {
            "severity": "low",
            "requires_approval": False,
            "approval_granted": False,
            "reasons": [],
            "stop": False,
        },
    )

    def fake_run(command, **kwargs):
        captured["command"] = command
        output_path = Path(command[command.index("-o") + 1])
        output_path.write_text("ok", encoding="utf-8")
        return 0, "", ""

    monkeypatch.setattr(bridge_runtime, "run_subprocess_cancellable", fake_run)
    result = bridge_runtime.run_codex_task("inspect status", workdir=workdir)

    assert result == "ok"
    command = captured["command"]
    assert command[command.index("-s") + 1] == "read-only"
    assert command[command.index("--profile") + 1] == "nyanya-readonly"
