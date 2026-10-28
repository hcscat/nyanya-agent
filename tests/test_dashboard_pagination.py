"""Exercise the shipped UI renderers without a browser account or operating DB."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from nyanya_agent import dashboard_store as store, database
from nyanya_agent.dashboard_api import create_app


SCRIPT = Path(__file__).resolve().parents[1] / "src/nyanya_agent/dashboard_static/app.js"


def run_dashboard_js(assertions):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required to exercise the shipped dashboard script")
    source = SCRIPT.read_text().split('\ndocument.addEventListener("click", handleClick);')[0]
    harness = """
    const assert = require('node:assert/strict');
    const elements = new Map();
    const document = {
      body: {classList: {add() {}, remove() {}}},
      activeElement: null,
      getElementById(id) {
        if (!elements.has(id)) elements.set(id, {
          innerHTML: '', textContent: '', value: '',
          classList: {add() {}, toggle() {}},
          contains() {return false}, getAttribute() {return 'Fixture list'},
          querySelector() {return null},
          showModal() {this.open = true}, close() {this.open = false},
        });
        return elements.get(id);
      },
      querySelectorAll() {return []},
    };
    const row = id => ({id: String(id), title: 'Fixture ' + id, prompt: 'Fixture prompt ' + id,
      status: 'failed', command: 'Fixture ' + id, content: 'Fixture content',
      error: 'Fixture error', adapter_type: 'fixture', enabled: true, action: 'fixture',
      name: 'Fixture ' + id, phases: [], bucket: String(id), requests: 1});
    """
    result = subprocess.run([node, "-e", harness + source + assertions], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("count", [0, 1, 5, 6, 8, 10, 11])
def test_shared_pager_bounds_pages_and_keeps_loaded_items_reachable(count):
    run_dashboard_js(r"""
    const count = COUNT;
    const items = Array.from({length: count}, (_, i) => i);
    const renderItems = page => page.map(i => `<article data-row="${i}">${i}</article>`).join('');
    const visible = () => [...$('fixture').innerHTML.matchAll(/data-row="(\d+)"/g)].map(m => Number(m[1]));
    renderPagedList('fixture', items, renderItems, 'Empty fixture');
    const seen = new Set();
    for (let i = 0; i < Math.max(1, Math.ceil(count / 5)); i++) {
      assert.deepEqual(visible(), items.slice(i * 5, i * 5 + 5));
      visible().forEach(item => seen.add(item));
      moveListPage('fixture', 1);
    }
    assert.equal(seen.size, count);
    const before = visible();
    renderPagedList('fixture', items, renderItems, 'Empty fixture');
    assert.deepEqual(visible(), before, 'refresh must retain the selected page');
    moveListPage('fixture', 99);
    assert.deepEqual(visible(), before, 'unknown navigation must be inert');
    renderPagedList('fixture', items.slice(0, 1), renderItems, 'Empty fixture');
    assert.deepEqual(visible(), items.slice(0, 1), 'shrinking results must clamp the page');
    moveListPage('fixture', -1);
    assert.deepEqual(visible(), items.slice(0, 1));
    renderPagedList('fixture', [], renderItems, '<unsafe empty>');
    assert.equal(visible().length, 0);
    assert.ok(!$('fixture').innerHTML.includes('data-action="list-page"'));
    assert.ok($('fixture').innerHTML.includes('&lt;unsafe empty&gt;'));
    """.replace("COUNT", json.dumps(count)))


def test_all_menu_collections_share_paging_and_approval_tasks_are_not_hidden():
    run_dashboard_js("""
    const items = Array.from({length: 8}, (_, i) => row(i));
    state.summary = {running: items, recent_failures: items};
    for (const key of ['requests', 'usage', 'projects', 'audit', 'memories', 'hosts', 'agents', 'executions']) state[key] = items;
    state.tasks = items.map(item => ({...item, status: 'awaiting_approval'}));
    state.approvals = [{...row(0), status: 'pending', task_id: '0'}, {...row(9), status: 'pending', task_id: '9'}];
    assert.equal(pendingApprovalItems().length, 9, 'task approvals must appear once, alongside separate records');
    render();
    for (const id of ['runningList', 'failureList', 'executionTable', 'approvalList', 'agentStatusTable', 'requestTable', 'usageChart', 'projectList', 'auditLog', 'memoryList']) {
      assert.ok($(id).innerHTML.includes('1–5'), id);
      moveListPage(id, 1);
      assert.ok($(id).innerHTML.includes('6–'), id);
    }
    const project = {...row('project'), checks: [{phase_key: 'planning', status: 'needs_confirmation', finding: '<unsafe finding>', created_at: 'not a date'}],
      phases: [{phase_key: 'planning', status: 'running', title: 'Planning'}]};
    assert.ok(renderPhaseCheck(project, {phase_key: 'planning'}).includes('&lt;unsafe finding&gt;'));
    state.projects = [project]; renderProjects();
    const header = $('projectList').innerHTML.match(/<div class="phase-status-row">([\\s\\S]*?)<\\/div>/)[1];
    assert.equal((header.match(/status-badge/g) || []).length, 2, 'phase and check status share the header');
    assert.ok(header.indexOf('현재 단계') < header.indexOf('확인 필요'));
    project.checks[0].status = 'ok';
    assert.ok(!renderPhaseCheck(project, {phase_key: 'planning'}).includes('unsafe finding'));
    assert.ok(renderPhaseCheck(project, {phase_key: 'planning'}).includes('마지막 체크'));
    assert.equal(renderPhaseCheck(project, {phase_key: 'design'}), '');
    assert.equal(renderPhaseCheck(project, {phase_key: 'design'}, {badgeOnly: true}), '');
    """)


def test_status_counts_open_filtered_pages_and_refresh_retains_selection():
    run_dashboard_js("""
    state.executions = Array.from({length: 8}, (_, i) => ({...row(i), status: 'completed', error: '',
      context: {request_prompt: 'Original request ' + i, response: 'Attempt result ' + i}}));
    state.executions.push({...row(99), status: 'running'});
    renderOffice();
    assert.ok($('agentOffice').innerHTML.includes('완료 실행 8건 목록 보기'));
    assert.ok(!$('agentOffice').innerHTML.includes('office-avatar'));
    openExecutionList('done');
    assert.equal($('executionDrawer').open, true);
    assert.ok($('executionList').innerHTML.includes('1–5'));
    assert.ok($('executionList').innerHTML.includes('Original request 0'));
    assert.ok(!$('executionList').innerHTML.includes('Original request 5'));
    moveListPage('executionList', 1);
    renderOffice();
    assert.ok($('executionList').innerHTML.includes('6–8'));
    assert.ok($('executionList').innerHTML.includes('Attempt result 7'));
    openExecutionList('queue');
    assert.ok($('executionList').innerHTML.includes('이 상태의 실행 없음'));
    """)


def test_request_previews_use_the_original_once_bound_long_text_and_escape_markup():
    run_dashboard_js("""
    const prompt = '모델이 제미나이인것은 알겠다. 그럼 너는 누구인가?';
    const item = {...row(1), command: '모델이', prompt, mode: 'auto'};
    state.requests = [item]; renderRequests();
    assert.equal($('requestTable').innerHTML.split(prompt).length - 1, 1);
    assert.ok(!$('requestTable').innerHTML.includes('<strong>모델이</strong>'));
    state.summary = {recent_failures: [{...item, mode: 'control', command: 'cancel'}]};
    renderFailures();
    assert.ok($('failureList').innerHTML.includes(prompt));
    assert.ok($('failureList').innerHTML.includes('조회·제어 요청'));
    assert.ok(!$('failureList').innerHTML.includes('<strong>cancel</strong>'));
    assert.equal(preview('  First\\n  second  '), 'First second');
    assert.equal(preview('x'.repeat(1000)).length, 181);
    assert.ok(requestPreview('<img src=x onerror=alert(1)>').includes('&lt;img'));
    """)


def test_execution_detail_uses_attempt_context_and_ignores_late_detail_response():
    run_dashboard_js("""
    (async () => {
      api = async () => ({...row('attempt'), error: '', context: {request_prompt: '<original request>',
        response: '<this attempt result>', delivery_status: 'unknown'}, events: []});
      await openExecutionDetail('attempt');
      assert.ok($('executionDetail').innerHTML.includes('&lt;original request&gt;'));
      assert.ok($('executionDetail').innerHTML.includes('&lt;this attempt result&gt;'));
      assert.ok(!$('executionDetail').innerHTML.includes('<this attempt result>'));
      let resolve;
      api = () => new Promise(done => resolve = done);
      const pending = openExecutionDetail('late');
      executionDetailRevision++;
      const before = $('executionDetail').innerHTML;
      resolve({...row('late'), context: {request_prompt: 'late content'}});
      await pending;
      assert.equal($('executionDetail').innerHTML, before);
    })().catch(error => {console.error(error); process.exitCode = 1});
    """)


def test_project_create_and_check_record_status_without_starting_work(tmp_path, monkeypatch):
    path = tmp_path / "dashboard.db"
    monkeypatch.setenv("NYANYA_DASHBOARD_CONTROL_TOKEN", "fixture-phase-token")
    headers = {"Authorization": "Bearer fixture-phase-token"}
    with TestClient(create_app(path), base_url="http://127.0.0.1") as client:
        project = client.post("/v1/projects", headers=headers, json={"name": "Fixture project", "goal": "Track work"}).json()
        assert [phase["status"] for phase in project["phases"]] == ["running", "waiting", "waiting", "waiting"]
        route = f"/v1/projects/{project['id']}/phases/planning/check"
        assert client.post(route).status_code == 401
        first = client.post(route, headers=headers).json()
        assert first["status"] == "ok" and first["confirmation_required"] == 0
        store.update_phase(project["id"], "planning", next_action="Review fixture design", db_path=path)
        checked = client.post(route, headers=headers).json()
        assert checked["status"] == "needs_confirmation"
        updated = client.get(f"/v1/projects/{project['id']}", headers=headers).json()
        assert updated["checks"][0]["id"] == checked["id"]
        assert updated["phases"][0]["requires_confirmation"] == 1
        with database.connect(path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM agent_tasks").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM executions").fetchone()[0] == 0
