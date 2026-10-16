"""Execute scoped memory rendering and controls against a synthetic browser boundary."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest


NODE_SMOKE = r"""
'use strict';
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[1], 'utf8');
function block(name) {
  const escapedName = name.replaceAll('$', '\\$');
  const start = new RegExp('^(?:async )?function ' + escapedName + '\\(', 'm').exec(source);
  assert(start, name);
  const end = /^}\n/m.exec(source.slice(start.index));
  assert(end, name);
  return source.slice(start.index, start.index + end.index + end[0].length);
}
const elements = new Map();
const document = { getElementById(id) {
  if (!elements.has(id)) elements.set(id, { innerHTML: '', textContent: '', value: '' });
  return elements.get(id);
}};
const state = { memories: [], wikiEntries: [], wikiScope: null, wikiRevision: 0,
  workRecords: [], workRecordScope: null, workRecordRevision: 0 };
let calls = [];
let wikiRows = [];
let workRows = [];
let beforeResponse = null;
const context = vm.createContext({ document, state, URLSearchParams,
  // Paging has a separate contract; keep these memory controls valid on both UI stages.
  listPages: new Map(),
  renderPagedList: (id, items, renderItems, emptyText) => {
    document.getElementById(id).innerHTML = items.length ? renderItems(items) : '<div class="empty">' + emptyText + '</div>';
  },
  label: value => value,
  api: async (url, options = {}) => {
    calls.push({ url, options });
    if (beforeResponse) { const action = beforeResponse; beforeResponse = null; action(); }
    if (url.startsWith('/v1/wiki?')) return wikiRows;
    if (url.startsWith('/v1/work-records?')) return workRows;
    return {};
  },
  alert: () => { throw new Error('Unexpected UI error alert'); },
});
for (const name of ['$', 'escapeHtml', 'badge', 'fmtDate', 'memoryTone', 'loadWikiEntries',
                    'loadWorkRecords', 'renderMemories', 'handleClick']) {
  vm.runInContext(block(name), context, { filename: 'staged-dashboard-' + name });
}
const el = id => document.getElementById(id);
const scope = { owner: 'synthetic-owner', workspace: '/synthetic/workspace', project_id: 'project', session_id: 'synthetic-session' };
const workScope = { owner: scope.owner, workspace: scope.workspace, project_id: scope.project_id };
const attack = '<img src=x onerror=alert(1)>';
const entry = { id: 'wiki-synthetic', title: attack, content: attack, status: 'pending', conflict: true,
  revision: 2, review_version: 4, provenance_kind: 'model_reply', source_task_id: 'task-synthetic',
  source_execution_id: 'exec-synthetic', created_at: attack };
const record = { execution_id: 'exec/synthetic', task_id: 'task-synthetic', request_summary: attack,
  result_summary: attack, provenance_kind: 'model_reply', current_task_status: 'completed' };
(async () => {
  let checks = 0;
  state.wikiScope = scope; state.workRecordScope = workScope;
  el('wikiQuery').value = 'synthetic topic';
  wikiRows = [entry]; workRows = [record];
  await context.loadWikiEntries(); await context.loadWorkRecords();
  assert(el('wikiList').innerHTML.includes('&lt;img'));
  assert(el('workRecordList').innerHTML.includes('&lt;img'));
  assert(!el('wikiList').innerHTML.includes('<img'));
  assert(!el('workRecordList').innerHTML.includes('<img'));
  const query = new URLSearchParams(calls.find(c => c.url.startsWith('/v1/wiki?')).url.split('?')[1]);
  assert.equal(query.get('owner'), scope.owner);
  assert.equal(query.get('workspace'), scope.workspace);
  assert.equal(query.get('session_id'), scope.session_id);
  assert.equal(query.get('project_id'), scope.project_id);
  assert.equal(query.get('query'), 'synthetic topic');
  checks++;

  state.memories = [{ id: 'memory-synthetic', title: attack, content: attack, status: 'approved', memory_type: 'preference', importance: 50, confidence: 0.8 }];
  context.renderMemories();
  assert(el('memoryList').innerHTML.includes('&lt;img'));
  assert(!el('memoryList').innerHTML.includes('<img'));
  assert(el('memoryList').innerHTML.includes('disabled'));
  checks++;

  wikiRows = []; workRows = []; state.memories = [];
  await context.loadWikiEntries(); await context.loadWorkRecords(); context.renderMemories();
  for (const id of ['wikiList', 'workRecordList', 'memoryList']) assert(el(id).innerHTML.includes('class="empty"'));
  checks++;

  const count = calls.length;
  state.wikiScope = null; state.workRecordScope = null;
  await context.loadWikiEntries(); await context.loadWorkRecords();
  assert.equal(calls.length, count);
  assert.equal(state.wikiEntries.length, 0); assert.equal(state.workRecords.length, 0);
  checks++;

  state.wikiScope = scope; state.workRecordScope = workScope;
  wikiRows = [entry]; workRows = [record];
  beforeResponse = () => { state.wikiRevision++; };
  await context.loadWikiEntries();
  assert.equal(state.wikiEntries.length, 0);
  beforeResponse = () => { state.workRecordRevision++; };
  await context.loadWorkRecords();
  assert.equal(state.workRecords.length, 0);
  checks++;

  await context.loadWikiEntries();
  calls = [];
  const review = { dataset: { action: 'wiki-approved', wiki: entry.id }, disabled: false };
  await context.handleClick({ target: { closest: () => review } });
  const reviewed = calls.filter(c => c.options.method === 'POST');
  assert.equal(reviewed.length, 1);
  assert.equal(reviewed[0].url, '/v1/wiki/wiki-synthetic/review');
  assert.deepEqual(JSON.parse(reviewed[0].options.body), { ...scope, status: 'approved', review_version: 4 });
  assert.equal(review.disabled, false);
  checks++;

  calls = [];
  const forget = { dataset: { action: 'work-record-forget', execution: record.execution_id }, disabled: false };
  await context.handleClick({ target: { closest: () => forget } });
  const forgotten = calls.filter(c => c.options.method === 'POST');
  assert.equal(forgotten.length, 1);
  assert.equal(forgotten[0].url, '/v1/work-records/exec%2Fsynthetic/forget');
  assert.deepEqual(JSON.parse(forgotten[0].options.body), workScope);
  assert.equal(forget.disabled, false);
  checks++;

  calls = []; state.wikiScope = null; state.workRecordScope = null;
  await context.handleClick({ target: { closest: () => review } });
  await context.handleClick({ target: { closest: () => forget } });
  assert.equal(calls.length, 0);
  checks++;

  // Bootstrap the complete script against IDs and views from the checked-in shell.
  const html = fs.readFileSync(require('node:path').join(require('node:path').dirname(process.argv[1]), 'index.html'), 'utf8');
  const actualIds = new Set(Array.from(html.matchAll(/\bid="([^"]+)"/g), match => match[1]));
  const missing = [];
  const bootstrapErrors = [];
  let fetches = 0;
  function domElement(dataset = {}) {
    return { dataset, value: '', innerHTML: '', textContent: '', hidden: false,
      classList: { add() {}, remove() {}, toggle() {} },
      addEventListener() {}, setAttribute() {}, getAttribute() { return null; },
    };
  }
  const ids = new Map(Array.from(actualIds, id => [id, domElement()]));
  const panels = Array.from(html.matchAll(/\bdata-view-panel="([^"]+)"/g), match => domElement({ viewPanel: match[1] }));
  const views = Array.from(html.matchAll(/\bdata-view="([^"]+)"/g), match => domElement({ view: match[1] }));
  const bootDocument = {
    body: domElement(), addEventListener() {},
    getElementById(id) { if (!ids.has(id)) missing.push(id); return ids.get(id) || null; },
    querySelector(selector) {
      const match = /^\[data-view="([^"]+)"\]$/.exec(selector);
      return match ? views.find(view => view.dataset.view === match[1]) || null : null;
    },
    querySelectorAll(selector) {
      if (selector === '[data-view-panel]') return panels;
      if (selector === '[data-view]') return views;
      throw new Error('Unexpected bootstrap selector: ' + selector);
    },
  };
  const bootstrap = vm.createContext({ document: bootDocument, URLSearchParams,
    location: { hash: '' }, history: { replaceState() {} },
    window: { clearTimeout() {}, clearInterval() {}, setTimeout() { return 1; }, setInterval() { return 1; } },
    console: { error: (...args) => bootstrapErrors.push(args.map(String).join(' ')) },
    fetch: () => { fetches++; return Promise.reject(new Error('Locked bootstrap must not fetch')); },
    alert: () => { throw new Error('Unexpected bootstrap alert'); },
  });
  vm.runInContext(source, bootstrap, { filename: 'complete-dashboard-bootstrap', timeout: 1000 });
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(missing, []);
  assert.deepEqual(bootstrapErrors, []);
  assert.equal(fetches, 0);
  checks++;

  process.stdout.write(JSON.stringify({ checks, status: 'passed', network: 'stubbed', source: 'staged dashboard functions' }) + '\n');
})().catch(error => { process.stderr.write(error.stack + '\n'); process.exitCode = 1; });
"""


def test_memory_rendering_and_controls_keep_escaped_content_and_explicit_scope():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for the actual dashboard functions")
    source = Path(__file__).resolve().parents[1] / "src/nyanya_agent/dashboard_static/app.js"
    result = subprocess.run(
        [node, "-e", NODE_SMOKE, str(source)], capture_output=True, text=True, check=True, timeout=15,
    )
    assert json.loads(result.stdout) == {
        "checks": 9, "status": "passed", "network": "stubbed", "source": "staged dashboard functions",
    }
