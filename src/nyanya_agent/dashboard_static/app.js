const state = {
  activeView: "main",
  summary: null,
  requests: [],
  usage: [],
  projects: [],
  audit: [],
  memories: [],
  workRecordScopes: [],
  workRecords: [],
  workRecordScope: null,
  workRecordRevision: 0,
  wikiScopes: [],
  wikiScope: null,
  wikiEntries: [],
  wikiRevision: 0,
  hosts: [],
  agents: [],
  tasks: [],
  executions: [],
  approvals: [],
  controlToken: "",
  eventCursor: 0,
  eventSource: null,
};

const LIST_PAGE_SIZE = 5;
const listPages = new Map();
const executionZones = { queue: "대기", work: "작업 중", review: "검토 필요", done: "완료", offline: "실패·중단" };
let executionListZone = null;
let executionDialogMode = null;
let executionDetailRevision = 0;

function preview(value, limit = 180) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > limit ? `${text.slice(0, limit).trimEnd()}…` : text;
}

function requestText(item) {
  return item.prompt || item.command || "요청 내용 미기록";
}

function requestKind(item) {
  return item.mode === "control" ? "조회·제어 요청" : "모델 처리 요청";
}

function requestPreview(text) {
  return `<span class="request-preview">${escapeHtml(preview(text))}</span>`;
}

function executionPrompt(execution) {
  const context = execution.context || {};
  return context.request_prompt || context.request_title || "원요청 내용 미기록";
}

function executionProcessing(execution) {
  const context = execution.context || {};
  return execution.error || context.response || (context.model_selection
    ? `${context.model_selection} · ${label(execution.status)}` : `처리 결과 미기록 · ${label(execution.status)}`);
}

const labels = {
  received: "접수",
  queued: "대기",
  running: "실행 중",
  phase_active: "현재 단계",
  sending: "전달 중",
  delivered: "전달 완료",
  acknowledged: "확인됨",
  unknown: "확인 필요",
  completed: "완료",
  failed: "실패",
  cancelled: "취소",
  ignored: "무시",
  active: "진행",
  paused: "일시중지",
  archived: "보관",
  planning: "기획",
  design: "설계",
  implementation: "구현",
  test: "테스트",
  waiting: "대기",
  blocked: "차단",
  green: "정상",
  amber: "주의",
  red: "위험",
  needs_confirmation: "확인 필요",
  ok: "정상",
  pending: "검토 대기",
  starting: "시작 중",
  awaiting_approval: "승인 대기",
  cancelling: "취소 중",
  succeeded: "완료",
  timed_out: "시간 초과",
  stale: "응답 지연",
  lost: "연결 유실",
  offline: "오프라인",
  online: "온라인",
  approved: "승인",
  rejected: "거부",
  superseded: "이전 버전",
  forgotten: "기억 제외",
  preference: "사용자 선호",
  workflow: "작업 방식",
  report_style: "결과 보고",
  project_fact: "프로젝트 사실",
  decision: "결정 사항",
  correction: "정정/피드백",
  failure_pattern: "실패 패턴",
  safety_rule: "안전 규칙",
  artifact: "산출물",
};

function $(id) {
  return document.getElementById(id);
}

function qs(selector) {
  return document.querySelector(selector);
}

function $$(selector) {
  return Array.from(document.querySelectorAll(selector));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function label(value) {
  return labels[value] || value || "-";
}

function badge(value) {
  return `<span class="status-badge ${escapeHtml(value)}">${escapeHtml(label(value))}</span>`;
}

function fmtDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return escapeHtml(value);
  return date.toLocaleString("ko-KR", { hour12: false });
}

function fmtDuration(value) {
  if (value === null || value === undefined) return "-";
  if (value < 1000) return `${value}ms`;
  return `${(value / 1000).toFixed(1)}s`;
}

function renderPagedList(id, items, renderItems, emptyText, { compact = false } = {}) {
  const container = $(id);
  const pages = Math.max(1, Math.ceil(items.length / LIST_PAGE_SIZE));
  const page = Math.min(listPages.get(id)?.page || 0, pages - 1);
  const start = page * LIST_PAGE_SIZE;
  const title = container.getAttribute("aria-label") || "목록";
  const focused = container.contains(document.activeElement) ? document.activeElement?.dataset.pageStep : null;
  listPages.set(id, { page, items, renderItems, emptyText, compact });
  container.classList.add("paged-list");
  container.classList.toggle("compact-list", compact);
  container.innerHTML = `
    <div id="${escapeHtml(id)}Page" class="page-viewport${items.length ? "" : " is-empty"}" role="region" aria-label="${escapeHtml(title)} 내용" tabindex="-1">
      <div class="page-items">${items.length ? renderItems(items.slice(start, start + LIST_PAGE_SIZE)) : `<div class="empty">${escapeHtml(emptyText)}</div>`}</div>
    </div>
    ${items.length ? `<nav class="list-pagination" aria-label="${escapeHtml(title)} 페이지 이동">
      <span class="page-status" role="status">조회한 ${items.length}건 중 ${start + 1}–${Math.min(start + LIST_PAGE_SIZE, items.length)} · ${page + 1}/${pages} 페이지</span>
      <button class="button small secondary" type="button" data-action="list-page" data-list="${escapeHtml(id)}" data-page-step="-1" aria-controls="${escapeHtml(id)}Page" ${page === 0 ? "disabled" : ""}>이전</button>
      <button class="button small secondary" type="button" data-action="list-page" data-list="${escapeHtml(id)}" data-page-step="1" aria-controls="${escapeHtml(id)}Page" ${page === pages - 1 ? "disabled" : ""}>다음</button>
    </nav>` : ""}
  `;
  if (focused) {
    const preferred = container.querySelector(`[data-page-step="${focused}"]`);
    (preferred?.disabled ? container.querySelector(".list-pagination button:not(:disabled)") || container.querySelector(".page-viewport") : preferred)?.focus({ preventScroll: true });
  }
}

function moveListPage(id, step) {
  const list = listPages.get(id);
  if (!list || ![-1, 1].includes(step)) return;
  const pages = Math.max(1, Math.ceil(list.items.length / LIST_PAGE_SIZE));
  list.page = Math.max(0, Math.min(list.page + step, pages - 1));
  renderPagedList(id, list.items, list.renderItems, list.emptyText, { compact: list.compact });
}

async function api(path, options = {}) {
  const controlHeaders = state.controlToken ? { Authorization: `Bearer ${state.controlToken}` } : {};
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...controlHeaders, ...(options.headers || {}) },
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function loadAll() {
  if (!state.controlToken) {
    setStreamStatus(false);
    $("streamStatus").title = "대시보드 잠금 해제 버튼에서 토큰을 입력하세요.";
    return;
  }
  const period = $("usagePeriod")?.value || "daily";
  const [
    summary,
    requests,
    usage,
    projects,
    audit,
    memories,
    hosts,
    agents,
    tasks,
    executions,
    approvals,
  ] = await Promise.all([
    api("/v1/summary"),
    api("/v1/requests?limit=50"),
    api(`/v1/usage?period=${encodeURIComponent(period)}&limit=30`),
    api("/v1/projects"),
    api("/v1/audit-log?limit=40"),
    api("/v1/memories?limit=120"),
    api("/v1/hosts"),
    api("/v1/agents"),
    api("/v1/tasks?limit=100"),
    api("/v1/executions?limit=100"),
    api("/v1/approvals?limit=100"),
  ]);
  state.summary = summary;
  state.requests = requests;
  state.usage = usage;
  state.projects = await Promise.all(projects.map((project) => api(`/v1/projects/${project.id}`)));
  state.audit = audit;
  state.memories = memories;
  state.hosts = hosts;
  state.agents = agents;
  state.tasks = tasks;
  state.executions = executions;
  state.approvals = approvals;
  render();
  await loadWorkRecordScopes();
  await loadWikiScopes();
}

async function loadWikiScopes() {
  const scopes = await api("/v1/wiki/scopes");
  const selected = state.wikiScope && JSON.stringify(state.wikiScope);
  state.wikiScopes = scopes;
  state.wikiScope = scopes.find((scope) => JSON.stringify(scope) === selected) || null;
  $("wikiScope").innerHTML = '<option value="">채널 기억 범위를 선택하세요</option>' + scopes.map((scope, index) =>
    `<option value="${index}">${escapeHtml(scope.owner)} · ${escapeHtml(scope.workspace)} · ${escapeHtml(scope.project_id || "프로젝트 없음")} · 채널 ${escapeHtml(scope.session_id.slice(-8))}</option>`,
  ).join("");
  $("wikiScope").value = state.wikiScope ? String(scopes.indexOf(state.wikiScope)) : "";
  await loadWikiEntries();
}

async function loadWikiEntries() {
  const revision = ++state.wikiRevision;
  const scope = state.wikiScope;
  state.wikiEntries = [];
  if (!scope) {
    listPages.delete("wikiList");
    $("wikiList").innerHTML = '<p class="empty">채널 기억 범위를 선택하세요.</p>';
    return;
  }
  const query = new URLSearchParams({ owner: scope.owner, workspace: scope.workspace, session_id: scope.session_id, include_inactive: "true" });
  if (scope.project_id) query.set("project_id", scope.project_id);
  if ($("wikiQuery").value.trim()) query.set("query", $("wikiQuery").value.trim());
  $("wikiList").textContent = "주제별 기억을 조회 중입니다.";
  const entries = await api(`/v1/wiki?${query}`);
  if (state.wikiScope !== scope || state.wikiRevision !== revision) return;
  state.wikiEntries = entries;
  renderPagedList("wikiList", entries, (page) => page.map((entry) => `
    <article class="memory-item">
      <div>
        ${badge(entry.status)} ${entry.conflict ? '<span class="status-badge amber">내용 충돌</span>' : ""}
        <strong>${escapeHtml(entry.title)} · 버전 ${escapeHtml(entry.revision)}</strong>
        <p>${escapeHtml(entry.content)}</p>
        <span class="meta">${escapeHtml(entry.provenance_kind === "reviewed_apply" ? "과거 검토 적용 근거" : "과거 모델 요약")} · ${escapeHtml(entry.status === "approved" ? "검토한 기억" : "현재 사실로 확인되지 않음")}</span>
        <p class="meta">근거 작업 <code>${escapeHtml(entry.source_task_id)}</code> · 실행 <code>${escapeHtml(entry.source_execution_id)}</code> · ${fmtDate(entry.created_at)}</p>
      </div>
      ${["pending", "approved"].includes(entry.status) ? `<div class="memory-actions">
        <button class="button small secondary" data-action="wiki-approved" data-wiki="${escapeHtml(entry.id)}" type="button">기억 버전 선택</button>
        <button class="button small secondary" data-action="wiki-rejected" data-wiki="${escapeHtml(entry.id)}" type="button">요약 거부</button>
        <button class="button small secondary" data-action="wiki-forgotten" data-wiki="${escapeHtml(entry.id)}" type="button">이 근거 기억 제외</button>
      </div>` : ""}
    </article>
  `).join(""), "이 채널 범위에서 검색된 Wiki 기억이 없습니다.");
}

async function loadWorkRecordScopes() {
  const scopes = await api("/v1/work-records/scopes");
  const selected = state.workRecordScope && JSON.stringify(state.workRecordScope);
  state.workRecordScopes = scopes;
  state.workRecordScope = scopes.find((scope) => JSON.stringify(scope) === selected) || null;
  const selector = $("workRecordScope");
  selector.innerHTML = '<option value="">조회 범위를 선택하세요</option>' + scopes.map((scope, index) =>
    `<option value="${index}">${escapeHtml(scope.owner)} · ${escapeHtml(scope.workspace)} · ${escapeHtml(scope.project_id || "프로젝트 없음")}</option>`,
  ).join("");
  selector.value = state.workRecordScope ? String(scopes.indexOf(state.workRecordScope)) : "";
  await loadWorkRecords();
}

async function loadWorkRecords() {
  const revision = ++state.workRecordRevision;
  const scope = state.workRecordScope;
  if (!scope) {
    listPages.delete("workRecordList");
    state.workRecords = [];
    $("workRecordList").innerHTML = '<p class="empty">조회 범위를 선택하세요.</p>';
    return;
  }
  const query = new URLSearchParams({ owner: scope.owner, workspace: scope.workspace });
  if (scope.project_id) query.set("project_id", scope.project_id);
  state.workRecords = [];
  $("workRecordList").textContent = "작업 기억을 조회 중입니다.";
  const records = await api(`/v1/work-records?${query}`);
  if (state.workRecordScope !== scope || state.workRecordRevision !== revision) return;
  state.workRecords = records;
  renderPagedList("workRecordList", records, (page) => page.map((record) => `
    <article class="memory-item">
      <div>
        <strong>${escapeHtml(record.request_summary || "본문 제외 기록")}</strong>
        <p>${escapeHtml(record.result_summary || "민감도·크기 검사로 본문을 보관하지 않았습니다.")}</p>
        <span class="meta">${escapeHtml(record.provenance_kind === "reviewed_apply" ? "검증된 적용 이력" : "모델 답변 이력")} · ${escapeHtml(record.current_task_status)} · <code>${escapeHtml(record.task_id)}</code></span>
      </div>
      <button class="button small secondary" data-action="work-record-forget" data-execution="${escapeHtml(record.execution_id)}" type="button">기억에서 제외</button>
    </article>
  `).join(""), "이 범위에 보관 중인 작업 기억이 없습니다.");
}

async function loadOperations() {
  const [hosts, agents, tasks, executions, approvals] = await Promise.all([
    api("/v1/hosts"),
    api("/v1/agents"),
    api("/v1/tasks?limit=100"),
    api("/v1/executions?limit=100"),
    api("/v1/approvals?limit=100"),
  ]);
  state.hosts = hosts;
  state.agents = agents;
  state.tasks = tasks;
  state.executions = executions;
  state.approvals = approvals;
  renderOffice();
}

function render() {
  renderActiveView();
  renderMetrics();
  renderRunning();
  renderFailures();
  renderRequests();
  renderUsage();
  renderProjects();
  renderOffice();
  renderMemories();
  renderAudit();
}

function renderActiveView() {
  $$("[data-view-panel]").forEach((panel) => {
    const active = panel.dataset.viewPanel === state.activeView;
    panel.hidden = !active;
    panel.classList.toggle("active", active);
  });
  $$("[data-view]").forEach((button) => {
    const active = button.dataset.view === state.activeView;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "page" : "false");
  });
}

function setView(view, { updateHash = true } = {}) {
  if (!["main", "office", "projects", "memory", "stats"].includes(view)) {
    view = "main";
  }
  state.activeView = view;
  if (updateHash) {
    history.replaceState(null, "", `#${view}`);
  }
  renderActiveView();
}

function memoryTone(memory) {
  if (memory.status === "approved") return "green";
  if (memory.status === "rejected") return "red";
  if ((memory.importance || 0) >= 70) return "amber";
  return "";
}

function renderMetrics() {
  const counts = state.summary?.status_counts || {};
  const cards = [
    ["전체 요청", state.summary?.requests ?? 0, ""],
    ["오늘 요청", state.summary?.today_requests ?? 0, ""],
    ["실행 중", (counts.running ?? 0) + (counts.queued ?? 0), "warn"],
    ["실패", counts.failed ?? 0, "danger"],
    ["단계 확인", state.summary?.phase_confirmations ?? 0, "info"],
  ];
  $("overview").innerHTML = cards
    .map(
      ([title, value, tone]) => `
        <article class="metric-card ${tone}">
          <div><span>${escapeHtml(title)}</span><strong>${escapeHtml(value)}</strong></div>
          <div class="metric-tone" aria-hidden="true"></div>
        </article>
      `,
    )
    .join("");
}

function renderRunning() {
  const items = state.summary?.running || [];
  renderPagedList("runningList", items, (page) => page
          .map(
            (item) => `
              <article class="list-item">
                <div class="item-heading">${badge(item.status)}<span class="meta">${requestKind(item)} · ${fmtDate(item.created_at)}</span></div>
                <strong>${requestPreview(requestText(item))}</strong>
                <p class="result-preview">${escapeHtml(preview(item.result_summary || "요청을 처리하고 있습니다.", 240))}</p>
                <span class="meta">${escapeHtml(item.provider || "-")} · ${escapeHtml(item.model || "-")}</span>
              </article>
            `,
          )
          .join(""), "진행 중 요청 없음");
}

function renderFailures() {
  const items = state.summary?.recent_failures || [];
  renderPagedList("failureList", items, (page) => page
          .map(
            (item) => `
              <article class="list-item danger">
                <div class="item-heading">${badge(item.status)}<span class="meta">${requestKind(item)} · ${fmtDate(item.ended_at || item.created_at)}</span></div>
                <strong>${requestPreview(requestText(item))}</strong>
                <p class="result-preview">${escapeHtml(preview(item.error || item.result_summary || "오류 상세 미기록", 240))}</p>
              </article>
            `,
          )
          .join(""), "최근 실패 없음");
}

function shortId(value) {
  const text = String(value || "-");
  return text.length > 18 ? `${text.slice(0, 9)}…${text.slice(-6)}` : text;
}

function officeZone(status) {
  if (["pending", "queued", "starting", "received"].includes(status)) return "queue";
  if (["running", "cancelling"].includes(status)) return "work";
  if (["awaiting_approval", "blocked"].includes(status)) return "review";
  if (["succeeded", "completed"].includes(status)) return "done";
  return "offline";
}

function pendingApprovalItems() {
  const waitingTasks = state.tasks.filter((task) => task.status === "awaiting_approval");
  const waitingIds = new Set(waitingTasks.map((task) => task.id));
  return [
    ...waitingTasks.map((task) => ({
      status: "awaiting_approval", action: "파일 변경안 검토", task_id: task.id,
      reason: `${task.title || task.prompt || "파일 변경 요청"} · 요청 대화에서 변경안과 해시를 확인하고 승인하세요.`,
      requested_at: task.updated_at,
    })),
    ...state.approvals.filter((approval) => approval.status === "pending" && !waitingIds.has(approval.task_id))
      .map((approval) => ({ ...approval, action: `실행 승인 기록 · ${approval.action}` })),
  ];
}

function renderOffice() {
  if (!$("officeMetrics")) return;
  const activeTaskStatuses = new Set(["queued", "running", "awaiting_approval", "blocked"]);
  const activeExecutionStatuses = new Set(["pending", "starting", "running", "awaiting_approval", "cancelling", "stale"]);
  const onlineHosts = state.hosts.filter((host) => !["offline", "stale"].includes(host.observed_status)).length;
  const pendingApprovals = pendingApprovalItems();
  const cards = [
    ["온라인 Host", onlineHosts, "info"],
    ["설정된 에이전트", state.agents.filter((agent) => agent.enabled).length, ""],
    ["미완료 작업", state.tasks.filter((task) => activeTaskStatuses.has(task.status)).length, "warn"],
    ["진행 중 실행", state.executions.filter((execution) => activeExecutionStatuses.has(execution.status)).length, "warn"],
    ["승인 대기", pendingApprovals.length, "danger"],
  ];
  $("officeMetrics").innerHTML = cards
    .map(
      ([title, value, tone]) => `
        <article class="metric-card ${tone}">
          <div><span>${escapeHtml(title)}</span><strong>${escapeHtml(value)}</strong></div>
          <div class="metric-tone" aria-hidden="true"></div>
        </article>
      `,
    )
    .join("");

  $("agentOffice").innerHTML = Object.entries(executionZones).map(([key, title]) => {
    const count = state.executions.filter((execution) => officeZone(execution.status) === key).length;
    return `<button class="execution-count" type="button" data-action="execution-list" data-zone="${key}" aria-label="${title} 실행 ${count}건 목록 보기">
      <span>${title}</span><strong>${count}</strong><span class="meta">목록 보기</span>
    </button>`;
  }).join("");
  $("executionWindow").textContent = `최근 조회한 ${state.executions.length}건의 실행 시도입니다. 숫자를 눌러 원요청과 결과를 확인하세요. 조회·제어를 포함한 전체 요청은 통계에서 확인할 수 있습니다.`;
  renderPagedList("executionTable", state.executions, renderExecutionRows, "실행 이력 없음");
  if (executionDialogMode === "list") renderExecutionDialogList();

  renderPagedList("approvalList", pendingApprovals, (page) => page
        .map(
          (approval) => `
            <article class="list-item">
              ${badge(approval.status)}
              <strong>${escapeHtml(approval.action)}</strong>
              <p>${escapeHtml(approval.reason || "사유 미기록")}</p>
              <span class="meta">${escapeHtml(shortId(approval.task_id || approval.execution_id))} · ${fmtDate(approval.requested_at)}</span>
            </article>
          `,
        )
        .join(""), "승인 대기 없음");

  const hostRows = state.hosts.map(
    (host) => `
      <tr>
        <td>Host</td><td><strong>${escapeHtml(host.name)}</strong><br><code>${escapeHtml(shortId(host.id))}</code></td>
        <td>${badge(host.observed_status || host.status)}</td><td>${escapeHtml(host.role)}</td><td>${fmtDate(host.last_heartbeat_at)}</td>
      </tr>
    `,
  );
  const agentRows = state.agents.map(
    (agent) => `
      <tr>
        <td>Agent</td><td><strong>${escapeHtml(agent.name)}</strong><br><code>${escapeHtml(shortId(agent.id))}</code></td>
        <td>${badge(agent.enabled ? "green" : "offline")}</td><td>${escapeHtml(agent.adapter_type)}</td><td>${fmtDate(agent.updated_at)}</td>
      </tr>
    `,
  );
  renderPagedList("agentStatusTable", [...hostRows, ...agentRows], (page) => `
    <table>
      <thead><tr><th>종류</th><th>이름·ID</th><th>상태</th><th>역할·Adapter</th><th>마지막 확인</th></tr></thead>
      <tbody>${page.join("")}</tbody>
    </table>
  `, "등록된 Host·Agent 없음");
}

function renderExecutionRows(page) {
  return page.map((execution) => `
    <article class="list-item execution-item">
      <div class="item-heading">${badge(execution.status)}<span class="meta">${fmtDate(execution.started_at || execution.created_at)}</span></div>
      <strong>${requestPreview(executionPrompt(execution))}</strong>
      <p class="result-preview"><span class="field-label">처리</span> ${escapeHtml(preview(executionProcessing(execution), 240))}</p>
      <div class="item-footer"><span class="meta">${escapeHtml(execution.adapter_type)} · ${escapeHtml(shortId(execution.task_id))}</span>
        <button class="button small secondary" type="button" data-action="execution-detail" data-execution="${escapeHtml(execution.id)}">요청·결과 상세</button>
      </div>
    </article>`).join("");
}

function showExecutionDialog(title) {
  $("executionDrawerTitle").textContent = title;
  $("executionDrawer").scrollTop = 0;
  if (!$("executionDrawer").open) {
    document.body.classList.add("dialog-open");
    $("executionDrawer").showModal();
  }
}

function renderExecutionDialogList() {
  const executions = state.executions.filter((execution) => officeZone(execution.status) === executionListZone);
  if (!$("executionDetail").querySelector("#executionList")) {
    $("executionDetail").innerHTML = '<div id="executionList" class="stack" aria-label="상태별 실행 목록"></div>';
  }
  $("backToExecutionList").hidden = true;
  renderPagedList("executionList", executions, renderExecutionRows, "이 상태의 실행 없음");
}

function openExecutionList(zone) {
  if (!Object.hasOwn(executionZones, zone)) return;
  executionDetailRevision++;
  executionListZone = zone;
  executionDialogMode = "list";
  listPages.delete("executionList");
  renderExecutionDialogList();
  showExecutionDialog(`${executionZones[zone]} 실행 목록`);
}

async function openExecutionDetail(executionId) {
  const revision = ++executionDetailRevision;
  const execution = await api(`/v1/executions/${encodeURIComponent(executionId)}`);
  if (revision !== executionDetailRevision) return;
  if (executionDialogMode !== "list") executionListZone = null;
  executionDialogMode = "detail";
  const context = execution.context || {};
  $("backToExecutionList").hidden = !executionListZone;
  $("executionDetail").innerHTML = `
    <div class="detail-block"><div class="item-heading">${badge(execution.status)}<span class="meta">${fmtDate(execution.started_at)} → ${fmtDate(execution.ended_at)}</span></div></div>
    <div class="detail-block"><h3>원래 요청</h3><p class="original-text">${escapeHtml(executionPrompt(execution))}</p></div>
    <div class="detail-block"><h3>이 실행의 처리 결과</h3><p class="original-text">${escapeHtml(context.response || executionProcessing(execution))}</p></div>
    ${execution.error && execution.error !== context.response ? `<div class="detail-block"><h3>오류</h3><p>${escapeHtml(execution.error)}</p></div>` : ""}
    <div class="detail-block"><h3>처리 정보</h3><p>${escapeHtml(context.model_selection || "모델 선택 기록 없음")}<br>전달 상태: ${escapeHtml(context.delivery_status === "pending" ? "전달 대기" : label(context.delivery_status || "미기록"))}</p><span class="meta">저장된 실행 시도의 기록이며 현재 파일 상태나 전달 성공을 대신 보장하지 않습니다.</span></div>
    <details class="detail-block"><summary>실행 식별 정보</summary><dl class="execution-identifiers">
      <dt>Execution ID</dt><dd><code>${escapeHtml(execution.id)}</code></dd>
      <dt>Task ID</dt><dd><code>${escapeHtml(execution.task_id)}</code></dd>
      <dt>실행 방식</dt><dd>${escapeHtml(execution.adapter_type)}</dd>
      <dt>작업 경로</dt><dd><code>${escapeHtml(execution.workdir || "-")}</code></dd>
    </dl></details>
    <details class="detail-block"><summary>실행 이벤트</summary><div id="executionEvents" class="stack" aria-label="실행 이벤트"></div></details>
  `;
  listPages.delete("executionEvents");
  renderPagedList("executionEvents", (execution.events || []).slice().reverse(), (page) => page
    .map((event) => `<p><code>${escapeHtml(event.event_type)}</code> ${escapeHtml(event.message || label(event.status))}<br><span class="meta">${fmtDate(event.created_at)}</span></p>`)
    .join(""), "실행 이벤트 없음", { compact: true });
  showExecutionDialog("실행 상세");
}

function renderRequests() {
  renderPagedList("requestTable", state.requests, (page) => `
    <table class="request-table">
      <thead>
        <tr>
          <th>상태</th>
          <th>요청</th>
          <th>모드</th>
          <th>모델</th>
          <th>소요</th>
          <th>토큰</th>
          <th>시작</th>
        </tr>
      </thead>
      <tbody>
        ${page
          .map(
            (item) => `
              <tr>
                <td>${badge(item.status)}</td>
                <td class="request-cell">${requestPreview(requestText(item))}</td>
                <td>${escapeHtml(item.mode)}</td>
                <td>${escapeHtml(item.provider)}<br><span class="meta">${escapeHtml(item.model || "-")}</span></td>
                <td>${fmtDuration(item.duration_ms)}</td>
                <td>${item.total_tokens ?? "-"}</td>
                <td>${fmtDate(item.started_at || item.created_at)}</td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `, "요청 이력 없음");
}

function renderUsage() {
  const max = Math.max(1, ...state.usage.map((item) => item.requests || 0));
  renderPagedList("usageChart", state.usage, (page) => page
          .map((item) => {
            const width = Math.max(2, Math.round(((item.requests || 0) / max) * 100));
            return `
              <article class="usage-row">
                <span>${escapeHtml(item.bucket)}</span>
                <div class="bar"><i style="width:${width}%"></i></div>
                <strong>${escapeHtml(item.requests || 0)}</strong>
                <small>완료 ${escapeHtml(item.completed || 0)} · 실패 ${escapeHtml(item.failed || 0)} · 평균 ${fmtDuration(Math.round(item.avg_duration_ms || 0))}</small>
              </article>
            `;
          })
          .join(""), "사용량 데이터 없음");
}

function renderProjects() {
  renderPagedList("projectList", state.projects, (page) => page
          .map(
            (project) => `
              <article class="project-card">
                <div class="project-head">
                  <div>
                    ${badge(project.health)}
                    <h3>${escapeHtml(project.name)}</h3>
                    <p>${escapeHtml(project.goal || "목표 미기록")}</p>
                  </div>
                  <span class="meta">현재 단계: ${escapeHtml(label(project.current_phase))}</span>
                </div>
                <div class="phase-grid">
                  ${(project.phases || [])
                    .map(
                      (phase) => `
                        <section class="phase-card">
                          <div class="phase-status-row">
                            ${badge(phase.status === "running" ? "phase_active" : phase.status)}
                            ${renderPhaseCheck(project, phase, { badgeOnly: true })}
                          </div>
                          <strong>${escapeHtml(phase.title)}</strong>
                          <p>${escapeHtml(phase.summary || "단계 요약을 아직 기록하지 않았습니다.")}</p>
                          <span class="meta">${escapeHtml(phase.next_action || "다음 작업: 아직 지정하지 않음")}</span>
                          ${renderPhaseCheck(project, phase)}
                          <button class="button small secondary" data-action="check-phase" data-project="${escapeHtml(project.id)}" data-phase="${escapeHtml(phase.phase_key)}" type="button" title="저장된 단계 상태와 다음 작업을 확인합니다. 개발이나 테스트를 실행하지 않습니다.">상태 체크</button>
                        </section>
                      `,
                    )
                    .join("")}
                </div>
              </article>
            `,
          )
          .join(""), "프로젝트 없음");
}

function renderPhaseCheck(project, phase, { badgeOnly = false } = {}) {
  const check = (project.checks || []).find((item) => item.phase_key === phase.phase_key);
  if (!check) return "";
  if (badgeOnly) return badge(check.status);
  const finding = check.status !== "ok" && check.finding ? `<p>${escapeHtml(check.finding)}</p>` : "";
  return `<div class="phase-check" role="status">${finding}<span class="meta">마지막 체크: ${fmtDate(check.created_at)}</span></div>`;
}

function renderAudit() {
  renderPagedList("auditLog", state.audit, (page) => page
          .map(
            (entry) => `
              <article class="audit-item">
                <span>${fmtDate(entry.created_at)}</span>
                <strong>${escapeHtml(entry.action)}</strong>
                <span>${escapeHtml(entry.actor)} · ${escapeHtml(entry.entity_type)}:${escapeHtml(entry.entity_id)}</span>
              </article>
            `,
          )
          .join(""), "감사 로그 없음");
}

function renderMemories() {
  if (!$("memorySummary")) return;
  const cards = [
    ["조회한 기억", state.memories.length, ""],
    ["검토 대기", state.memories.filter((memory) => memory.status === "pending").length, "warn"],
    ["승인", state.memories.filter((memory) => memory.status === "approved").length, "info"],
    ["타입", new Set(state.memories.map((memory) => memory.memory_type)).size, ""],
  ];
  $("memorySummary").innerHTML = cards
    .map(
      ([title, value, tone]) => `
        <article class="metric-card memory ${tone}">
          <div><span>${escapeHtml(title)}</span><strong>${escapeHtml(value)}</strong></div>
          <div class="metric-tone" aria-hidden="true"></div>
        </article>
      `,
    )
    .join("");

  renderPagedList("memoryList", state.memories, (page) => page
          .map(
            (memory) => `
              <article class="memory-item ${memoryTone(memory)}">
                <div>
                  ${badge(memory.status)}
                  <strong>${escapeHtml(memory.title)}</strong>
                  <p>${escapeHtml(memory.content)}</p>
                  <span class="meta">${escapeHtml(label(memory.memory_type))} · 중요도 ${Math.round(memory.importance || 0)} · 신뢰도 ${Math.round((memory.confidence || 0) * 100)}%</span>
                </div>
                <div class="memory-actions">
                  <button class="button small secondary" data-action="memory-approve" data-memory="${escapeHtml(memory.id)}" type="button" ${memory.status === "approved" ? "disabled" : ""}>승인</button>
                  <button class="button small secondary" data-action="memory-reject" data-memory="${escapeHtml(memory.id)}" type="button" ${memory.status === "rejected" ? "disabled" : ""}>거부</button>
                </div>
              </article>
            `,
          )
          .join(""), "기억 후보 없음. 필요한 경우 요청 이력에서 후보를 추출하세요.");
}

async function createProject(event) {
  event.preventDefault();
  const name = $("projectNameInput").value.trim();
  const goal = $("projectGoalInput").value.trim();
  if (!name) return;
  await api("/v1/projects", {
    method: "POST",
    body: JSON.stringify({ name, goal, owner: "operator" }),
  });
  $("projectNameInput").value = "";
  $("projectGoalInput").value = "";
  await loadAll();
}

async function handleClick(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  if (button.dataset.action === "list-page") {
    moveListPage(button.dataset.list, Number(button.dataset.pageStep));
    return;
  }
  button.disabled = true;
  try {
    if (button.dataset.action === "execution-list") openExecutionList(button.dataset.zone);
    if (button.dataset.action === "check-phase") {
      await api(`/v1/projects/${button.dataset.project}/phases/${button.dataset.phase}/check`, { method: "POST" });
      await loadAll();
    }
    if (button.dataset.action === "memory-approve" || button.dataset.action === "memory-reject") {
      await api(`/v1/memories/${button.dataset.memory}`, {
        method: "PATCH",
        body: JSON.stringify({ status: button.dataset.action === "memory-approve" ? "approved" : "rejected" }),
      });
      await loadAll();
    }
    if (button.dataset.action === "execution-detail") {
      await openExecutionDetail(button.dataset.execution);
    }
    if (button.dataset.action === "work-record-forget") {
      const scope = state.workRecordScope;
      if (!scope) return;
      await api(`/v1/work-records/${encodeURIComponent(button.dataset.execution)}/forget`, {
        method: "POST", body: JSON.stringify(scope),
      });
      await loadWorkRecords();
      await loadWikiEntries();
    }
    if (["wiki-approved", "wiki-rejected", "wiki-forgotten"].includes(button.dataset.action)) {
      const scope = state.wikiScope;
      const entry = state.wikiEntries.find((item) => item.id === button.dataset.wiki);
      if (!scope || !entry) return;
      await api(`/v1/wiki/${encodeURIComponent(entry.id)}/review`, {
        method: "POST",
        body: JSON.stringify({ ...scope, status: button.dataset.action.slice(5), review_version: entry.review_version }),
      });
      await loadWikiEntries();
      await loadWorkRecords();
    }
  } catch (error) {
    alert(error.message);
  } finally {
    button.disabled = false;
  }
}

document.addEventListener("click", handleClick);
$("wikiScope").addEventListener("change", () => {
  listPages.delete("wikiList");
  state.wikiScope = state.wikiScopes[$("wikiScope").value] || null;
  loadWikiEntries().catch((error) => alert(error.message));
});
$("wikiSearchBtn").addEventListener("click", () => {
  listPages.delete("wikiList");
  loadWikiEntries().catch((error) => alert(error.message));
});
qs('[data-view="main"]').addEventListener("click", () => setView("main"));
qs('[data-view="office"]').addEventListener("click", () => setView("office"));
qs('[data-view="projects"]').addEventListener("click", () => setView("projects"));
qs('[data-view="memory"]').addEventListener("click", () => setView("memory"));
qs('[data-view="stats"]').addEventListener("click", () => setView("stats"));
$("projectForm").addEventListener("submit", createProject);
$("refreshBtn").addEventListener("click", () => loadAll());
$("unlockControlBtn").addEventListener("click", async () => {
  const token = window.prompt("Dashboard control token");
  if (!token) return;
  const previous = state.controlToken;
  state.controlToken = token.trim();
  try {
    await api("/v1/operations/incomplete");
    await loadAll();
    $("unlockControlBtn").textContent = "대시보드 연결됨";
    connectEventStream();
    $("unlockControlBtn").disabled = true;
  } catch (error) {
    state.controlToken = previous;
    alert(error.message);
  }
});
$("usagePeriod").addEventListener("change", () => {
  listPages.delete("usageChart");
  loadAll();
});
$("workRecordScope").addEventListener("change", async (event) => {
  listPages.delete("workRecordList");
  const value = event.target.value;
  state.workRecordScope = value === "" ? null : state.workRecordScopes[Number(value)] || null;
  try {
    await loadWorkRecords();
  } catch (error) {
    $("workRecordList").textContent = "작업 기억을 조회하지 못했습니다.";
    alert(error.message);
  }
});
$("extractMemoryBtn").addEventListener("click", async () => {
  $("extractMemoryBtn").disabled = true;
  try {
    await api("/v1/memories/extract?limit=80", { method: "POST" });
    await loadAll();
  } catch (error) {
    alert(error.message);
  } finally {
    $("extractMemoryBtn").disabled = false;
  }
});

$("closeExecutionDrawer").addEventListener("click", () => {
  executionDetailRevision++;
  $("executionDrawer").close();
});

$("executionDrawer").addEventListener("cancel", () => { executionDetailRevision++; });
$("executionDrawer").addEventListener("close", () => {
  executionDetailRevision++;
  executionDialogMode = null;
  document.body.classList.remove("dialog-open");
});
$("backToExecutionList").addEventListener("click", () => {
  executionDetailRevision++;
  executionDialogMode = "list";
  renderExecutionDialogList();
  $("executionDrawerTitle").textContent = `${executionZones[executionListZone]} 실행 목록`;
  $("executionDrawer").scrollTop = 0;
});

let operationReloadTimer = null;

function setStreamStatus(connected) {
  const status = $("streamStatus");
  status.classList.toggle("offline", !connected);
  status.textContent = connected ? "5초 주기 갱신" : "연결·인증 확인";
}

function scheduleOperationReload() {
  window.clearTimeout(operationReloadTimer);
  operationReloadTimer = window.setTimeout(() => {
    loadOperations().catch(() => setStreamStatus(false));
  }, 180);
}

function connectEventStream() {
  // Authenticated polling also works through private proxies; no token in URLs.
  window.clearInterval(state.eventPollTimer);
  if (!state.controlToken) return;
  state.eventPollTimer = window.setInterval(async () => {
    try {
      const events = await api(`/v1/events?after_seq=${state.eventCursor}&limit=1000`);
      for (const event of events) state.eventCursor = Math.max(state.eventCursor, Number(event.seq) || 0);
      if (events.length) scheduleOperationReload();
      setStreamStatus(true);
    } catch {
      setStreamStatus(false);
    }
  }, 5000);
}

setView(location.hash.replace("#", ""), { updateHash: false });

loadAll().catch((error) => {
  setStreamStatus(false);
  $("streamStatus").title = "대시보드 잠금 해제 버튼에서 토큰을 입력하세요.";
  console.error("Dashboard load failed", error.name);
});

connectEventStream();
