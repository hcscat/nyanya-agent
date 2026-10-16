"""Synthetic transfer regression; no credentials, network or model calls."""
from types import SimpleNamespace
import pytest
from nyanya_agent import context_security as security, discord_bridge
from nyanya_agent.task_outcomes import SafeOperationError

@pytest.mark.parametrize('name', ['reports/note.txt', 'data/note.txt', 'docs/private/note.txt'])
def test_explicit_ordinary_document_folder_is_not_a_blanket_deny(tmp_path, name):
    p = tmp_path / name
    p.parent.mkdir(parents=True)
    p.write_text('Synthetic public document')
    with security.open_upload_file(tmp_path, name) as stream:
        assert stream.read() == b'Synthetic public document'
        assert stream.privacy_counts == {}

def test_transfer_over_old_two_million_bound_is_separate_from_model_budget(tmp_path):
    data = b'x' * 2000001
    (tmp_path / 'large.txt').write_bytes(data)
    with security.open_upload_file(tmp_path, 'large.txt', max_bytes=3000000) as stream:
        assert stream.read() == data
        assert stream.size == len(data)

@pytest.mark.parametrize('delta', [0, 1])
def test_actual_transfer_bound(tmp_path, delta):
    (tmp_path / 'note.txt').write_bytes(b'x' * (32 + delta))
    if delta:
        with pytest.raises(SafeOperationError):
            with security.open_upload_file(tmp_path, 'note.txt', max_bytes=32):
                pass
    else:
        with security.open_upload_file(tmp_path, 'note.txt', max_bytes=32) as stream:
            assert len(stream.read()) == 32

def test_pii_is_counted_without_exposing_values_in_metadata(tmp_path):
    (tmp_path / 'note.txt').write_text('Email: fixture.person@example.invalid')
    with security.open_upload_file(tmp_path, 'note.txt') as stream:
        assert stream.privacy_counts.get('email') == 1
        assert 'fixture.person' not in repr(stream.privacy_counts)
        assert len(stream.sha256) == 64
        assert stream.identity['size'] == stream.size

def test_non_utf8_document_keeps_original_bytes_after_full_inspection(tmp_path):
    data = '합성 문서 안내입니다'.encode('cp949')
    (tmp_path / 'note.txt').write_bytes(data)
    with security.open_upload_file(tmp_path, 'note.txt') as stream:
        assert stream.read() == data
        assert stream.privacy_counts == {}

@pytest.mark.parametrize('sdk,expected', [(4000000, 4000000), (50000000, 8 * 1024 * 1024)])
def test_limit_is_minimum_of_sdk_and_app(sdk, expected):
    assert discord_bridge.upload_byte_limit(SimpleNamespace(guild=SimpleNamespace(filesize_limit=sdk))) == expected

@pytest.mark.parametrize('sdk', [None, 0, -1, True, '8000000'])
def test_unknown_destination_limit_fails_closed(sdk):
    with pytest.raises(SafeOperationError):
        discord_bridge.upload_byte_limit(SimpleNamespace(guild=SimpleNamespace(filesize_limit=sdk)))

def test_long_document_inspection_has_a_bounded_execution_time():
    import subprocess, sys
    code = "from nyanya_agent.upload_document_privacy import inspect_document; assert inspect_document(b'x'*2_000_001,'note.txt').counts=={}"
    run = subprocess.run([sys.executable, '-c', code], capture_output=True, timeout=10)
    assert run.returncode == 0, run.stderr.decode()

@pytest.mark.parametrize('data', [b'/Users/' + b'fixture-owner/private/file.txt', b'/home/fixture-owner/private/file.txt', b'C:\\Users\\fixture-owner\\file.txt', b'~/private/file.txt'])
def test_local_path_personal_information_requires_confirmation_metadata(tmp_path, data):
    (tmp_path / 'note.txt').write_bytes(data)
    with security.open_upload_file(tmp_path, 'note.txt') as stream:
        assert stream.privacy_counts.get('local_path') == 1
