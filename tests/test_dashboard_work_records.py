"""Authenticated work-record controls do not mutate task or effect history."""

import json

import pytest
from fastapi.testclient import TestClient

from nyanya_agent import database as db, execution_store as ledger, operation_store as store
from nyanya_agent.dashboard_api import create_app
from nyanya_agent.operation_spec import OperationSpec
from nyanya_agent.operation_worker import Worker


@pytest.fixture
def setup(tmp_path, monkeypatch):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    monkeypatch.setenv("NYANYA_WORKSPACE_ROOTS", f"{first},{second}")
    monkeypatch.setenv("NYANYA_WORK_MEMORY_ENABLED", "true")
    monkeypatch.setenv("NYANYA_DASHBOARD_CONTROL_TOKEN", "fixture-work-record-control")
    path = tmp_path / "records.db"

    def model(profile, prompt, *args):
        if prompt.startswith("Return only JSON"):
            return json.dumps(dict(importance=1, impact=1, complexity=1, reason="fixture"))
        return json.dumps(dict(summary="합성 예제의 재시도는 세 번입니다.", changes=[]))

    worker = Worker(path, invoke=model)
    tasks = []
    for workspace in (first, second):
        task = store.submit(path, OperationSpec(prompt="합성 예제 재시도 횟수를 설명해줘", workspace=str(workspace)),
                            "operator", worker.generation)
        assert worker.run_once()
        tasks.append(ledger.get_task(task["id"], db_path=path))
    headers = {"Authorization": "Bearer fixture-work-record-control"}
    with TestClient(create_app(path), base_url="http://127.0.0.1") as client:
        yield client, headers, path, (first, second), tasks
    worker.close()


def test_work_record_api_requires_auth_and_explicit_scope(setup):
    client, headers, _, roots, tasks = setup
    assert client.get("/v1/work-records/scopes").status_code == 401
    assert client.get("/v1/work-records", params={"owner": "operator", "workspace": str(roots[0])}).status_code == 401
    assert client.get("/v1/work-records", headers=headers).status_code == 422
    scopes = client.get("/v1/work-records/scopes", headers=headers).json()
    assert {s["workspace"] for s in scopes} == {str(root) for root in roots}
    assert all(s["owner"] == "operator" and s["project_id"] is None for s in scopes)
    for root, task in zip(roots, tasks):
        records = client.get("/v1/work-records", headers=headers,
                             params={"owner": "operator", "workspace": str(root)}).json()
        assert len(records) == 1
        assert records[0]["task_id"] == task["id"]
    assert client.get("/v1/work-records", headers=headers,
                      params={"owner": "other-owner", "workspace": str(roots[0])}).json() == []
    assert client.get("/v1/work-records", headers=headers,
                      params={"owner": "operator", "workspace": str(roots[0]), "limit": 21}).status_code == 422


def test_forget_requires_matching_scope_and_preserves_workflow(setup):
    client, headers, path, roots, tasks = setup
    task = tasks[0]
    execution = task["current_execution_id"]
    route = f"/v1/work-records/{execution}/forget"
    payload = {"owner": "operator", "workspace": str(roots[0])}
    assert client.post(route, json=payload).status_code == 401
    assert client.post(route, headers=headers,
                       json={"owner": "operator", "workspace": str(roots[1])}).status_code == 404
    with db.connect(path) as conn:
        before = dict(conn.execute("SELECT * FROM task_results WHERE execution_id=?", (execution,)).fetchone())
    assert client.post(route, headers=headers, json=payload).json() == {"forgotten": True}
    assert client.get("/v1/work-records", headers=headers, params=payload).json() == []
    assert ledger.get_task(task["id"], db_path=path) == task
    with db.connect(path) as conn:
        assert dict(conn.execute("SELECT * FROM task_results WHERE execution_id=?", (execution,)).fetchone()) == before
        record = conn.execute("SELECT * FROM task_work_records WHERE execution_id=?", (execution,)).fetchone()
        assert record["status"] == "forgotten"
        assert record["request_summary"] == record["result_summary"] == ""


def test_work_record_routes_reject_wrong_origin_and_ui_keeps_scope_selection(setup):
    client, headers, _, _, _ = setup
    response = client.get("/v1/work-records/scopes", headers={**headers, "Origin": "https://other.invalid"})
    assert response.status_code == 403
    html = client.get("/").text
    script = client.get("/static/app.js").text
    assert 'id="workRecordScope"' in html and 'id="workRecordList"' in html
    assert "if (!scope)" in script and "encodeURIComponent(button.dataset.execution)" in script


def test_removed_workspace_returns_controlled_scope_error(setup):
    client, headers, _, roots, tasks = setup
    roots[0].rmdir()
    params = {"owner": "operator", "workspace": str(roots[0])}
    assert client.get("/v1/work-records", headers=headers, params=params).status_code == 400
    route = f"/v1/work-records/{tasks[0]['current_execution_id']}/forget"
    assert client.post(route, headers=headers, json=params).status_code == 400
