"""Candidate review and scoped memory use local assets without remote visualization."""

from html.parser import HTMLParser
from urllib.parse import urlsplit

from fastapi.testclient import TestClient

from nyanya_agent import dashboard_store as store
from nyanya_agent import execution_store as ledger
from nyanya_agent.dashboard_api import create_app


class ScriptSources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and "src" in attrs:
            self.sources.append(attrs["src"])
        if "id" in attrs:
            self.ids.add(attrs["id"])



def test_shell_uses_local_assets_and_keeps_review_and_work_views(tmp_path, monkeypatch):
    monkeypatch.setenv("NYANYA_DASHBOARD_CONTROL_TOKEN", "fixture-review-token")
    with TestClient(create_app(tmp_path / "dashboard.db"), base_url="http://127.0.0.1") as client:
        response = client.get("/")
        assert response.status_code == 200
        shell = ScriptSources()
        shell.feed(response.text)
        assert len(shell.sources) == 1
        asset = urlsplit(shell.sources[0])
        assert asset.path == "/static/app.js"
        assert {"memoryList", "extractMemoryBtn", "projectsView", "officeView", "statsView"} <= shell.ids
        assert "memoryGraph" not in shell.ids
        assert "techStackGraph" not in shell.ids
        script = client.get("/static/app.js").text
        assert "/v1/memories?limit=120" in script
        assert "memory-graph" not in script
        assert "tech-stack-graph" not in script
        assert "cytoscape" not in script.lower()



def test_candidate_review_preserves_history_and_removed_routes_stay_absent(tmp_path, monkeypatch):
    db = tmp_path / "dashboard.db"
    monkeypatch.setenv("NYANYA_DASHBOARD_CONTROL_TOKEN", "fixture-review-token")
    request_id = store.create_agent_request(prompt="앞으로 짧게 보고해줘.", db_path=db)
    store.mark_request_status(request_id, "completed", result_summary="알겠습니다.", db_path=db)
    project = store.create_project(name="Fixture project", goal="Keep work history", db_path=db)
    task = ledger.create_task(title="Fixture task", prompt="Inspect retained history", db_path=db)
    headers = {"Authorization": "Bearer fixture-review-token"}
    with TestClient(create_app(db), base_url="http://127.0.0.1") as client:
        for path in ["/v1/memories", "/v1/projects", "/v1/tasks", "/v1/requests"]:
            assert client.get(path).status_code == 401
        assert client.post("/v1/memories/extract").status_code == 401
        extracted = client.post("/v1/memories/extract", headers=headers)
        assert extracted.status_code == 200
        memory_id = extracted.json()["memory_ids"][0]
        review_path = f"/v1/memories/{memory_id}"
        assert client.patch(review_path, json={"status": "approved"}).status_code == 401
        assert client.patch(review_path, headers=headers, json={"status": "approved"}).json()["status"] == "approved"
        assert client.get("/v1/memories?status=approved", headers=headers).json()[0]["id"] == memory_id
        assert client.patch(review_path, headers=headers, json={"status": "rejected"}).json()["status"] == "rejected"
        for path in ["/v1/memory-graph", "/v1/tech-stack-graph"]:
            assert client.get(path, headers=headers).status_code == 404
        assert client.get(f"/v1/requests/{request_id}", headers=headers).json()["status"] == "completed"
        assert client.get(f"/v1/projects/{project['id']}", headers=headers).json()["goal"] == "Keep work history"
        assert client.get(f"/v1/tasks/{task['id']}", headers=headers).json()["prompt"] == "Inspect retained history"

