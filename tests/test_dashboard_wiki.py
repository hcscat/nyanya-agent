"""Private topic review is authenticated, revision-bound and not a task approval."""

import json
from pathlib import Path
import shutil
import subprocess

from fastapi.testclient import TestClient
import pytest

from nyanya_agent import database as db, execution_store as ledger, operation_store as store
from nyanya_agent import wiki_store as wiki
from nyanya_agent.dashboard_api import create_app
from nyanya_agent.operation_spec import OperationSpec
from nyanya_agent.operation_worker import ASSESSMENT, Worker


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", str(root))
    monkeypatch.setenv("NYANYA_WORK_MEMORY_ENABLED", "true")
    monkeypatch.setenv("NYANYA_DASHBOARD_CONTROL_TOKEN", "synthetic-wiki-control")
    path = tmp_path / "dashboard.db"
    def model(profile, prompt, *args):
        if prompt.startswith(ASSESSMENT):
            return json.dumps({"importance": 1, "impact": 1, "complexity": 1, "reason": "fixture"})
        return json.dumps({"summary": "The synthetic cache retries three times.", "changes": [],
                           "wiki": [{"topic": "Synthetic cache retry", "summary": "The historical choice was three retries."}]})
    worker = Worker(path, invoke=model)
    task = store.submit(path, OperationSpec(prompt="Describe the synthetic cache retry decision", workspace=str(root)),
                        "operator", worker.generation, conversation_key="synthetic-channel")
    assert worker.run_once()
    scope = wiki.list_scopes(path)[0]
    item = wiki.list_entries(path, scope["owner"], scope["workspace"], scope["session_id"])[0]
    scope = {key: value for key, value in scope.items() if value is not None}
    headers = {"Authorization": "Bearer synthetic-wiki-control"}
    with TestClient(create_app(path), base_url="http://127.0.0.1") as client:
        yield client, headers, path, root, task, scope, item
    worker.close()


def test_wiki_read_and_control_require_token_origin_and_explicit_channel_scope(setup):
    client, headers, _, _, _, scope, item = setup
    assert client.get("/v1/wiki/scopes").status_code == 401
    assert client.get("/v1/wiki", params=scope).status_code == 401
    assert client.get("/v1/wiki", headers=headers).status_code == 422
    assert client.get("/v1/wiki/scopes", headers={**headers, "Origin": "https://other.invalid"}).status_code == 403
    assert client.get("/v1/wiki", headers=headers, params=scope).json()[0]["id"] == item["id"]
    wrong = {**scope, "owner": "other-owner"}
    assert client.get("/v1/wiki", headers=headers, params=wrong).status_code == 400
    route = f"/v1/wiki/{item['id']}/review"
    payload = {**scope, "status": "approved", "review_version": item["review_version"]}
    assert client.post(route, json=payload).status_code == 401
    assert client.post(route, headers=headers, json={**payload, "session_id": "unknown-channel"}).status_code == 400
    assert client.post(route, headers=headers, json={**payload, "review_version": 999}).status_code == 409
    assert client.post(route, headers=headers, json=payload).json()["status"] == "approved"
    assert client.post(route, headers=headers, json=payload).status_code == 409


def test_wiki_forget_preserves_task_plan_and_raw_result_and_clears_derived_memory(setup):
    client, headers, path, _, task, scope, item = setup
    before_task = ledger.get_task(task["id"], db_path=path)
    with db.connect(path) as conn:
        before_result = dict(conn.execute("SELECT * FROM task_results WHERE task_id=?", (task["id"],)).fetchone())
    payload = {**scope, "status": "forgotten", "review_version": item["review_version"]}
    assert client.post(f"/v1/wiki/{item['id']}/review", headers=headers, json=payload).json()["status"] == "forgotten"
    assert client.get("/v1/wiki", headers=headers, params=scope).json() == []
    assert ledger.get_task(task["id"], db_path=path) == before_task
    with db.connect(path) as conn:
        assert dict(conn.execute("SELECT * FROM task_results WHERE task_id=?", (task["id"],)).fetchone()) == before_result
        assert conn.execute("SELECT count(*) FROM approvals").fetchone()[0] == 0
        assert tuple(conn.execute("SELECT status,content FROM wiki_entries").fetchone()) == ("forgotten", "")


@pytest.mark.parametrize("status", ["rejected", "superseded"])
def test_authenticated_work_forget_clears_inactive_wiki_and_preserves_ledger(setup, status):
    client, headers, path, _, task, scope, item = setup
    execution = item["source_execution_id"]
    before_task = ledger.get_task(task["id"], db_path=path)
    with db.connect(path) as conn:
        before_result = dict(conn.execute("SELECT * FROM task_results WHERE execution_id=?", (execution,)).fetchone())
        conn.execute("UPDATE wiki_entries SET status=? WHERE id=?", (status, item["id"]))
    route = f"/v1/work-records/{execution}/forget"
    assert client.post(route, json=scope).status_code == 401
    assert client.post(route, headers=headers, json={**scope, "owner": "other-owner"}).status_code == 404
    assert client.post(route, headers=headers, json=scope).json() == {"forgotten": True}
    assert client.get("/v1/wiki", headers=headers, params={**scope, "include_inactive": True}).json() == []
    assert ledger.get_task(task["id"], db_path=path) == before_task
    with db.connect(path) as conn:
        assert dict(conn.execute("SELECT * FROM task_results WHERE execution_id=?", (execution,)).fetchone()) == before_result
        assert tuple(conn.execute("SELECT status,title,content FROM wiki_entries").fetchone()) == (
            "forgotten", "Forgotten topic", "")


def test_dashboard_wiki_controls_escape_content_and_keep_explicit_scope(setup):
    client, _, _, _, _, _, _ = setup
    html = client.get("/").text
    script = client.get("/static/app.js").text
    assert all(f'id="{name}"' in html for name in ["wikiScope", "wikiQuery", "wikiSearchBtn", "wikiList"])
    assert "escapeHtml(entry.title)" in script and "escapeHtml(entry.content)" in script
    assert "review_version: entry.review_version" in script
    assert "state.wikiScope !== scope || state.wikiRevision !== revision" in script
    assert 'session_id: scope.session_id' in script


def test_malformed_date_is_inert_when_inserted_in_dashboard_html():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for the actual dashboard formatter")
    source = (Path(__file__).resolve().parents[1] / "src/nyanya_agent/dashboard_static/app.js").read_text()
    start = source.index("function escapeHtml(")
    escape = source[start:source.index("\nfunction label(", start)]
    start = source.index("function fmtDate(")
    formatter = source[start:source.index("\nfunction fmtDuration(", start)]
    payload = "<img src=x onerror=alert('fixture')>"
    code = escape + formatter + "\nprocess.stdout.write(fmtDate(" + json.dumps(payload) + "));"
    result = subprocess.run([node, "-e", code], capture_output=True, text=True, check=True)
    assert "<img" not in result.stdout and "&lt;img" in result.stdout
