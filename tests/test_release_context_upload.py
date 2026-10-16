"""Synthetic release regressions; no provider, Discord or operator files are used."""

import json

import pytest

from nyanya_agent import context_security as security, reviewed_changes as files
from nyanya_agent.operation_worker import RESPONSE, _bounded_snapshot, _current_prompt
from nyanya_agent.task_outcomes import SafeOperationError


PUBLIC_ENV_EXAMPLE = (
    "# Synthetic project\n"
    "NYANYA_DISCORD_BOT_TOKEN" + "=\n"
    "NYANYA_DISCORD_PREFIX=!nyanya\n"
    "NYANYA_DASHBOARD_CONTROL_TOKEN_FILE=data/dashboard_control.token\n"
)


@pytest.mark.parametrize("content", [
    PUBLIC_ENV_EXAMPLE,
    'api_key:\n  "<YOUR_API_KEY>"\n',
    'password:\n  "${PASSWORD}"\n',
    "TOKEN=\r\nPREFIX=!fixture\r\n",
    'TOKEN=""\nPREFIX=!fixture\n',
    'TOKEN_FILE="data/example.token"',
    '{"api_key_file": "config/example.key", "token": "<YOUR_TOKEN>"}',
    'api_key = os.getenv("OPENAI_API_KEY")',
])
def test_public_empty_env_and_file_reference_examples_are_not_secrets(content):
    assert not security.sensitive_content(content, environ={})


@pytest.mark.parametrize("content", [
    'TOKEN_FILE=synthetic-embedded-credential',
    'TOKEN=synthetic-embedded-credential\nPREFIX=!fixture',
    '{"api_key": "synthetic-embedded-credential"}',
    'TOKEN_FILE=sk-' + 'SYNTHETIC1234567890' * 2,
    'Authorization: Bearer synthetic-embedded-credential',
    '-----BEGIN PRIVATE KEY-----\nsynthetic\n-----END PRIVATE KEY-----',
])
def test_safe_file_references_never_exempt_embedded_credentials(content):
    assert security.sensitive_content(content, environ={})


def test_known_secret_still_blocks_even_when_disguised_as_file_reference():
    value = "synthetic-known-value.data"
    assert security.sensitive_content(f"TOKEN_FILE=data/{value}", {"API_KEY": value})
    assert not security.sensitive_content(PUBLIC_ENV_EXAMPLE, {
        "NYANYA_DASHBOARD_CONTROL_TOKEN_FILE": "data/dashboard_control.token",
    })


@pytest.mark.parametrize("request_text", [
    "Read only nyanya-agent/README.md",
    "[SYNTHETIC-READ-ONLY] 읽기 전용 기능 테스트입니다. 파일과 설정을 변경하지 마세요. 명령도 실행하지 마세요. 등록된 작업공간 안의 nyanya-agent/README.md 한 파일만 읽고 첫 제목과 주요 기능 세 가지를 알려 주세요. 해당 상대 경로가 없다면 다른 파일을 찾지 말고 없다고 알려 주세요.",
])
def test_readme_regression_c_uses_public_content_instead_of_empty_snapshot(tmp_path, request_text):
    project = tmp_path / "nyanya-agent"
    project.mkdir()
    (project / "README.md").write_text(PUBLIC_ENV_EXAMPLE)
    diagnostics = {}
    captured = files.snapshot(tmp_path, request_text, diagnostics)
    assert captured["nyanya-agent/README.md"]["content"] == PUBLIC_ENV_EXAMPLE
    assert diagnostics["nyanya-agent/README.md"] == "included"


def test_snapshot_preserves_missing_filtered_encoding_and_size_reasons(tmp_path):
    (tmp_path / "secret.txt").write_text("API_KEY=synthetic-private-value")
    (tmp_path / "binary.txt").write_bytes(b"not\0text")
    (tmp_path / "invalid.txt").write_bytes(b"invalid\xff")
    (tmp_path / "large.txt").write_bytes(b"x" * 50_001)
    diagnostics = {}
    captured = files.snapshot(
        tmp_path, "Read missing.txt secret.txt binary.txt invalid.txt large.txt .env", diagnostics,
    )
    assert captured == {}
    assert diagnostics == {
        "missing.txt": "missing", "secret.txt": "filtered_sensitive",
        "binary.txt": "unsupported_type", "invalid.txt": "unsupported_encoding",
        "large.txt": "oversized", ".env": "filtered_private",
    }
    serialized = json.dumps(diagnostics)
    assert "synthetic-private-value" not in serialized and str(tmp_path) not in serialized


def test_snapshot_io_errors_are_not_reported_as_missing(tmp_path, monkeypatch):
    def unreadable(*args):
        raise PermissionError("synthetic diagnostic that must not be forwarded")

    monkeypatch.setattr(files, "read_file", unreadable)
    diagnostics = {}
    assert files.snapshot(tmp_path, "Read exact/note.txt", diagnostics) == {}
    assert diagnostics == {"exact/note.txt": "unreadable"}
    assert "synthetic diagnostic" not in json.dumps(diagnostics)


def test_model_prompt_distinguishes_exclusion_from_verified_missing():
    diagnostics = {"secret.txt": "filtered_sensitive", "absent.txt": "missing"}
    prompt = _current_prompt(RESPONSE, "Read the named files", {}, diagnostics=diagnostics)
    assert '"path": "secret.txt", "status": "filtered_sensitive"' in prompt
    assert '"path": "absent.txt", "status": "missing"' in prompt
    security.validate_provider_prompt(prompt)
    assert "Never infer that a file does not exist merely because it is absent from the snapshot" in prompt
    assert "not proof of absence" in prompt


def test_diagnostics_and_snapshot_share_the_prompt_budget(monkeypatch):
    import nyanya_agent.operation_worker as worker

    monkeypatch.setattr(worker, "MAX_PROMPT_BYTES", 6000)
    diagnostics = {f"path-{index}/" + "z" * 300 + ".txt": "unreadable" for index in range(80)}
    baseline = {"note.txt": {"sha256": "fixture", "content": "x" * 1800}}
    bounded = _bounded_snapshot("Read note.txt", baseline, diagnostics)
    prompt = _current_prompt(RESPONSE, "Read note.txt", bounded, diagnostics=diagnostics)
    assert len((prompt + worker.HISTORY_LABEL + "{}").encode()) <= worker.MAX_PROMPT_BYTES
    assert "truncated" in prompt


@pytest.mark.parametrize("name", [
    ".env", ".codex/auth.json", "sessions/entry.txt", "config/auth.json",
    "AGENTS.md", "config/user_workspaces.json", "key.pem", "database.sqlite",
])
def test_upload_rejects_private_paths_before_open(tmp_path, monkeypatch, name):
    def denied(*args, **kwargs):
        pytest.fail("Private upload path was opened")

    monkeypatch.setattr(security.os, "open", denied)
    with pytest.raises(SafeOperationError, match="private"):
        with security.open_upload_file(tmp_path, name):
            pytest.fail("Private file reached the sender")


@pytest.mark.parametrize("content", [
    b"TOKEN=synthetic-private-value", b"binary\0data", b"invalid\xff",
])
def test_upload_rejects_sensitive_or_uninspectable_content(tmp_path, content):
    (tmp_path / "ordinary.txt").write_bytes(content)
    with pytest.raises(SafeOperationError):
        with security.open_upload_file(tmp_path, "ordinary.txt"):
            pytest.fail("Unsafe content reached the sender")


@pytest.mark.parametrize("name", ["document.pdf", "archive.zip", "image.png", "payload.exe"])
def test_upload_rejects_uninspectable_types_even_if_bytes_look_textual(tmp_path, name):
    (tmp_path / name).write_text("synthetic placeholder")
    with pytest.raises(SafeOperationError, match="inspection held"):
        with security.open_upload_file(tmp_path, name):
            pytest.fail("Uninspectable type reached the sender")


def test_upload_bounds_content_and_keeps_stream_at_start(tmp_path, monkeypatch):
    monkeypatch.setattr(security, "MAX_UPLOAD_BYTES", 32)
    target = tmp_path / "note.txt"
    target.write_text("x" * 33)
    with pytest.raises(SafeOperationError, match="bound"):
        with security.open_upload_file(tmp_path, "note.txt"):
            pytest.fail("Oversized content reached the sender")
    target.write_text(PUBLIC_ENV_EXAMPLE.splitlines()[0])
    with security.open_upload_file(tmp_path, "note.txt") as stream:
        assert stream.tell() == 0
        assert stream.read() == b"# Synthetic project"
    assert stream.closed


def test_upload_sends_exact_screened_bytes_if_the_inode_is_modified(tmp_path):
    target = tmp_path / "note.txt"
    target.write_text("safe original")
    with security.open_upload_file(tmp_path, "note.txt") as stream:
        target.write_text("TOKEN=synthetic-private-value")
        assert stream.read() == b"safe original"


def test_upload_scans_known_secret_values_without_reporting_them(tmp_path, monkeypatch):
    value = "synthetic-known-upload-value"
    monkeypatch.setenv("API_KEY", value)
    (tmp_path / "note.txt").write_text(value)
    with pytest.raises(SafeOperationError) as error:
        with security.open_upload_file(tmp_path, "note.txt"):
            pytest.fail("Known secret reached the sender")
    assert value not in str(error.value)


def test_public_readme_file_is_not_filtered_as_a_secret(tmp_path):
    from pathlib import Path

    public_readme = Path(__file__).resolve().parents[1] / "README.md"
    content = public_readme.read_text(encoding="utf-8")
    project = tmp_path / "nyanya-agent"
    project.mkdir()
    (project / "README.md").write_text(content, encoding="utf-8")
    diagnostics = {}
    captured = files.snapshot(tmp_path, "Read only nyanya-agent/README.md", diagnostics)
    assert captured["nyanya-agent/README.md"]["content"] == content
    assert diagnostics == {"nyanya-agent/README.md": "included"}


@pytest.mark.parametrize("content", [
    "api_key:\n  synthetic-credential-value\n",
    "service:\n  api_key:\n    synthetic-credential-value\n",
    "password:\n  synthetic-pass-value\n",
    "client_secret:\r\n    synthetic-client-value\r\n",
])
def test_indented_yaml_credentials_remain_blocked_in_context_and_upload(tmp_path, content):
    assert security.sensitive_content(content, environ={})
    (tmp_path / "note.txt").write_text(content)
    diagnostics = {}
    assert files.snapshot(tmp_path, "Read note.txt", diagnostics) == {}
    assert diagnostics == {"note.txt": "filtered_sensitive"}
    with pytest.raises(SafeOperationError):
        with security.open_upload_file(tmp_path, "note.txt"):
            pytest.fail("Indented credential reached sender")
