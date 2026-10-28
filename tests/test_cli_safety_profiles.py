from __future__ import annotations

from pathlib import Path
import urllib.request

import pytest

from nyanya_agent import model_routing, process_runner
from nyanya_agent import core


LOCAL_INVOKE = model_routing.invoke


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


@pytest.mark.parametrize("profile,model,effort", [
    ("luna", "gpt-6-luna", "xhigh"), ("sol", "gpt-6.1-sol", "high"),
])
def test_codex_read_only_invocation_uses_isolated_config(tmp_path, monkeypatch, profile, model, effort):
    captured = {}
    monkeypatch.setattr(model_routing, "resolve_codex_cli", lambda: "/synthetic/codex")

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        Path(command[command.index("-o") + 1]).write_text("ok", encoding="utf-8")
        return 0, "", ""

    monkeypatch.setattr(process_runner, "run_command", fake_run)
    assert LOCAL_INVOKE(profile, "Inspect a synthetic example", tmp_path, 30, None) == "ok"
    command = captured["command"]
    assert command[command.index("-s") + 1] == "read-only"
    assert "--ignore-user-config" in command and "--ephemeral" in command
    assert command[command.index("-m") + 1] == model
    assert command[command.index("-c") + 1] == f'model_reasoning_effort="{effort}"'
    assert captured["kwargs"]["cwd"] == tmp_path and captured["kwargs"]["provider"] == "codex"
