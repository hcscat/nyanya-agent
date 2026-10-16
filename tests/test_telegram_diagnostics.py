"""Polling diagnostics never persist credential-bearing upstream errors."""

from types import SimpleNamespace

from nyanya_agent.telegram_bridge import TelegramBridge


def test_polling_error_omits_provider_url_and_credential(monkeypatch, capsys):
    from nyanya_agent import telegram_bridge

    credential = "synthetic-" + "credential-for-polling"
    bridge = TelegramBridge(credential, SimpleNamespace())
    calls = 0

    def failed_poll(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError(f"upstream failed at {bridge.api_base}/getUpdates")
        raise KeyboardInterrupt()

    monkeypatch.setattr(bridge, "api", failed_poll)
    monkeypatch.setattr(telegram_bridge.time, "sleep", lambda _: None)

    assert bridge.run() == 0
    captured = capsys.readouterr()
    assert "Telegram bridge error: OSError" in captured.err
    assert credential not in captured.err
    assert bridge.api_base not in captured.err
