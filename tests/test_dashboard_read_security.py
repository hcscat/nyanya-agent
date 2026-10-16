"""Browser-origin boundaries apply even to connections from loopback."""

import pytest
from fastapi.testclient import TestClient

from nyanya_agent.dashboard_api import create_app
from nyanya_agent import execution_store as ledger


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('NYANYA_DASHBOARD_CONTROL_TOKEN', 'fixture-dashboard-access')
    monkeypatch.delenv('NYANYA_DASHBOARD_ALLOWED_HOSTS', raising=False)
    monkeypatch.delenv('NYANYA_DASHBOARD_CORS_ORIGINS', raising=False)
    path = tmp_path / 'dashboard.db'
    app = create_app(path)
    ledger.create_task(title='private fixture', prompt='private fixture request', db_path=path)
    with TestClient(app, base_url='http://127.0.0.1', client=('127.0.0.1', 12345)) as browser:
        yield browser


def test_local_api_requires_token_but_shell_and_health_remain_available(client):
    assert client.get('/').status_code == 200
    assert client.get('/health').status_code == 200
    for path in ['/v1/tasks', '/v1/summary', '/v1/events', '/v1/requests']:
        response = client.get(path)
        assert response.status_code == 401
        assert 'private fixture' not in response.text
    response = client.get('/v1/tasks', headers={'Authorization': 'Bearer fixture-dashboard-access'})
    assert response.status_code == 200
    assert response.json()[0]['title'] == 'private fixture'


@pytest.mark.parametrize('host', ['attacker.invalid', 'localhost.attacker.invalid', '127.0.0.1.attacker.invalid',
                                 'user@localhost', 'localhost/path', 'localhost:bad'])
def test_untrusted_host_rejected_even_with_token(client, host):
    response = client.get('/v1/tasks', headers={'Host': host, 'Authorization': 'Bearer fixture-dashboard-access'})
    assert response.status_code == 400
    assert 'private fixture' not in response.text


def test_cross_origin_and_forwarding_cannot_bypass_auth(client):
    headers = {'Origin': 'https://attacker.invalid', 'Authorization': 'Bearer fixture-dashboard-access'}
    assert client.get('/v1/tasks', headers=headers).status_code == 403
    assert client.get('/v1/tasks', headers={'X-Forwarded-For': '127.0.0.1'}).status_code == 401
    headers['Origin'] = 'http://127.0.0.1'
    assert client.get('/v1/tasks', headers=headers).status_code == 200


@pytest.mark.parametrize('host', ['localhost:8765', '127.0.0.1:8765', '[::1]:8765'])
def test_builtin_hosts_accept_authenticated_reads(client, host):
    assert client.get('/v1/tasks', headers={'Host': host, 'X-Nyanya-Control-Token': 'fixture-dashboard-access'}).status_code == 200


def test_missing_token_configuration_fails_closed(tmp_path, monkeypatch):
    monkeypatch.delenv('NYANYA_DASHBOARD_CONTROL_TOKEN', raising=False)
    monkeypatch.setenv('NYANYA_DASHBOARD_CONTROL_TOKEN_FILE', str(tmp_path / 'absent-token'))
    with TestClient(create_app(tmp_path / 'db'), base_url='http://localhost') as browser:
        assert browser.get('/v1/tasks').status_code == 503


def test_explicit_host_and_cors_origin_remain_authenticated(tmp_path, monkeypatch):
    monkeypatch.setenv('NYANYA_DASHBOARD_CONTROL_TOKEN', 'fixture-dashboard-access')
    monkeypatch.setenv('NYANYA_DASHBOARD_ALLOWED_HOSTS', 'dashboard.example.test')
    monkeypatch.setenv('NYANYA_DASHBOARD_CORS_ORIGINS', 'https://ui.example.test')
    with TestClient(create_app(tmp_path / 'db'), base_url='https://dashboard.example.test') as browser:
        assert browser.options('/v1/tasks', headers={'Origin': 'https://ui.example.test',
                               'Access-Control-Request-Method': 'GET',
                               'Access-Control-Request-Headers': 'Authorization'}).status_code == 200
        assert browser.get('/v1/tasks', headers={'Origin': 'https://ui.example.test'}).status_code == 401
        assert browser.get('/v1/tasks', headers={'Origin': 'https://ui.example.test',
                          'Authorization': 'Bearer fixture-dashboard-access'}).status_code == 200


def test_malformed_browser_headers_fail_without_server_error(client):
    token = ('Authorization', 'Bearer fixture-dashboard-access')
    assert client.get('/v1/tasks', headers=[token, ('Origin', 'http://127.0.0.1'),
                                          ('Origin', 'https://attacker.invalid')]).status_code == 403
    assert client.get('/v1/tasks', headers=[token, ('Host', 'local\thost')]).status_code == 400
    assert client.get('/v1/tasks', headers={b'Authorization': b'Bearer \xff'}).status_code == 401


def test_invalid_host_configuration_does_not_create_database(tmp_path, monkeypatch):
    monkeypatch.setenv('NYANYA_DASHBOARD_ALLOWED_HOSTS', '*.example.test')
    path = tmp_path / 'untouched.db'
    with pytest.raises(ValueError):
        create_app(path)
    assert not path.exists()


def test_module_import_and_help_do_not_create_state_or_start_server(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys

    root = Path(__file__).resolve().parents[1]
    state = tmp_path / 'untouched-state'
    env = os.environ.copy()
    env.update(NYANYA_HOME=str(state), NYANYA_ENV_FILE=str(state / 'absent.env'),
               NYANYA_DASHBOARD_DB_PATH=str(state / 'absent.db'),
               PYTHONPATH=str(root / 'src'), PYTHONDONTWRITEBYTECODE='1')
    for command in ([sys.executable, '-c', 'import nyanya_agent.dashboard_api'],
                    [sys.executable, '-m', 'nyanya_agent.dashboard_api', '--help']):
        result = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        assert not state.exists()
    assert 'usage:' in result.stdout.lower()


def test_legacy_asgi_attribute_is_lazy_and_cached(tmp_path, monkeypatch):
    from nyanya_agent import dashboard_api

    sentinel = object()
    called = []
    monkeypatch.delitem(dashboard_api.__dict__, 'app', raising=False)
    monkeypatch.setattr(dashboard_api, 'create_app', lambda: called.append(True) or sentinel)
    try:
        assert dashboard_api.app is sentinel
        assert dashboard_api.app is sentinel
        assert called == [True]
    finally:
        dashboard_api.__dict__.pop('app', None)
