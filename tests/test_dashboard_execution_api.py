from __future__ import annotations

from fastapi.testclient import TestClient

from nyanya_agent import dashboard_api
from nyanya_agent import execution_store as ledger
from nyanya_agent import database


def test_execution_context_is_authenticated_bounded_and_bound_to_each_attempt(tmp_path, monkeypatch):
    db_path = tmp_path / "dashboard.db"
    monkeypatch.setenv("NYANYA_DASHBOARD_CONTROL_TOKEN", "fixture-execution-token")
    client = TestClient(dashboard_api.create_app(db_path), base_url="http://127.0.0.1")
    headers = {"Authorization": "Bearer fixture-execution-token"}
    task = ledger.create_task(title="Fixture", prompt="Original request " * 100, db_path=db_path)
    attempts = [ledger.create_execution(task_id=task["id"], adapter_type="operation", db_path=db_path)
                for _ in range(2)]
    with database.connect(db_path) as conn:
        for index, attempt in enumerate(attempts):
            response = f"Attempt {index} response " * 100
            conn.execute("INSERT INTO task_results VALUES (?,?,?,?,?,?,?,?)",
                         (attempt["id"], task["id"], "succeeded", response, "unknown", "", "fixture", "fixture"))
    route = f"/v1/executions/{attempts[0]['id']}"
    assert client.get("/v1/executions").status_code == 401
    assert client.get(route).status_code == 401
    detail = client.get(route, headers=headers).json()
    assert detail["context"]["request_prompt"] == task["prompt"]
    assert detail["context"]["response"] == "Attempt 0 response " * 100
    assert detail["context"]["delivery_status"] == "unknown"
    listing = client.get("/v1/executions", headers=headers).json()
    for item in listing:
        assert len(item["context"]["request_prompt"]) <= 321
        assert len(item["context"]["response"]) <= 401
        index = next(i for i, attempt in enumerate(attempts) if attempt["id"] == item["id"])
        assert item["context"]["response"].startswith(f"Attempt {index} response")
    empty = ledger.create_task(title="No prompt fixture", db_path=db_path)
    attempt = ledger.create_execution(task_id=empty["id"], adapter_type="fixture", db_path=db_path)
    context = client.get(f"/v1/executions/{attempt['id']}", headers=headers).json()["context"]
    assert context["request_title"] == "No prompt fixture" and context["response"] is None
    assert client.get("/v1/executions/not-found", headers=headers).status_code == 404


def test_execution_read_api_and_authenticated_control_actions(tmp_path, monkeypatch):
    db_path = tmp_path / "dashboard.db"
    monkeypatch.setenv("NYANYA_DASHBOARD_CONTROL_TOKEN", "test-control-token")
    client = TestClient(dashboard_api.create_app(db_path), base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
    headers = {"Authorization": "Bearer test-control-token"}

    unauthenticated = client.post("/v1/tasks", json={"title": "Remote task"})
    assert unauthenticated.status_code == 401

    created = client.post(
        "/v1/tasks",
        headers=headers,
        json={"title": "Remote task", "prompt": "Inspect status", "requested_by": "operator"},
    )
    assert created.status_code == 201
    task = created.json()

    listed = client.get("/v1/tasks", headers={"Authorization": "Bearer test-control-token"})
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == task["id"]

    cancelled = client.post(
        f"/v1/tasks/{task['id']}/cancel",
        headers=headers,
        json={"actor": "operator", "reason": "test cancel"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    retried = client.post(
        f"/v1/tasks/{task['id']}/retry",
        headers={"X-Nyanya-Control-Token": "test-control-token"},
        json={"actor": "operator", "reason": "test retry"},
    )
    assert retried.status_code == 409
    assert client.get(f"/v1/tasks/{task['id']}", headers={"Authorization": "Bearer test-control-token"}).json()["status"] == "cancelled"

    health = client.get("/health", headers={"Authorization": "Bearer test-control-token"}).json()
    assert health["schema_version"] == ledger.MIGRATIONS[-1][0]
    assert health["control_auth_configured"] is True
    assert client.get("/v1/summary", headers={"Authorization": "Bearer test-control-token"}).json()["execution_ledger"]["schema_version"] == ledger.MIGRATIONS[-1][0]


def test_execution_project_codex_session_and_task_filters(tmp_path, monkeypatch):
    db_path = tmp_path / "dashboard.db"
    monkeypatch.setenv("NYANYA_DASHBOARD_CONTROL_TOKEN", "test-control-token")
    client = TestClient(dashboard_api.create_app(db_path), base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
    headers = {"X-Nyanya-Control-Token": "test-control-token"}

    project_response = client.post(
        "/v1/execution-projects",
        headers=headers,
        json={"name": "Control project", "workspace_root": str(tmp_path / "workspace")},
    )
    assert project_response.status_code == 201
    project = project_response.json()

    session_response = client.post(
        f"/v1/execution-projects/{project['id']}/codex-sessions",
        headers=headers,
        json={"session_key": "operator-codex", "name": "Operator Codex"},
    )
    assert session_response.status_code == 201
    session = session_response.json()

    task_response = client.post(
        "/v1/tasks",
        headers=headers,
        json={
            "title": "Project task",
            "project_id": project["id"],
            "codex_session_id": session["id"],
            "metadata": {"api_key": "redacted"},
        },
    )
    assert task_response.status_code == 201
    task = task_response.json()
    assert task["project_id"] == project["id"]
    assert task["codex_session_id"] == session["id"]
    assert task["metadata"]["api_key"] == "[REDACTED]"
    filtered = client.get(f"/v1/tasks?project_id={project['id']}", headers={"Authorization": "Bearer test-control-token"})
    assert filtered.status_code == 200
    assert filtered.json()[0]["id"] == task["id"]
    loaded_session = client.get(f"/v1/codex-sessions/{session['id']}", headers={"Authorization": "Bearer test-control-token"})
    assert loaded_session.status_code == 200


def test_approval_decision_and_cursor_event_read(tmp_path, monkeypatch):
    db_path = tmp_path / "dashboard.db"
    monkeypatch.setenv("NYANYA_DASHBOARD_CONTROL_TOKEN", "test-control-token")
    client = TestClient(dashboard_api.create_app(db_path), base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
    task = ledger.create_task(title="Approval", db_path=db_path)
    approval = ledger.request_approval(
        task_id=task["id"],
        action="workspace.write",
        requested_by="agent",
        db_path=db_path,
    )

    response = client.post(
        f"/v1/approvals/{approval['id']}/decision",
        headers={"Authorization": "Bearer test-control-token"},
        json={"decision": "approved", "decided_by": "operator"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"

    events = client.get("/v1/events", headers={"Authorization": "Bearer test-control-token"}).json()
    assert events
    cursor = events[-2]["seq"]
    resumed = client.get(f"/v1/events?after_seq={cursor}", headers={"Authorization": "Bearer test-control-token"}).json()
    assert resumed[0]["seq"] > cursor
