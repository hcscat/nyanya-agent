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

const labels = {
  received: "접수",
  queued: "대기",
  running: "실행 중",
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
  $("wikiList").innerHTML = entries.length ? entries.map((entry) => `
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
  `).join("") : '<div class="empty">이 채널 범위에서 검색된 Wiki 기억이 없습니다.</div>';
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
  $("workRecordList").innerHTML = records.length ? records.map((record) => `
    <article class="memory-item">
      <div>
        <strong>${escapeHtml(record.request_summary || "본문 제외 기록")}</strong>
        <p>${escapeHtml(record.result_summary || "민감도·크기 검사로 본문을 보관하지 않았습니다.")}</p>
        <span class="meta">${escapeHtml(record.provenance_kind === "reviewed_apply" ? "검증된 적용 이력" : "모델 답변 이력")} · ${escapeHtml(record.current_task_status)} · <code>${escapeHtml(record.task_id)}</code></span>
      </div>
      <button class="button small secondary" data-action="work-record-forget" data-execution="${escapeHtml(record.execution_id)}" type="button">기억에서 제외</button>
    </article>
  `).join("") : '<div class="empty">이 범위에 보관 중인 작업 기억이 없습니다.</div>';
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
  $("runningList").innerHTML =
    items.length === 0
      ? `<div class="empty">진행 중 요청 없음</div>`
      : items
          .map(
            (item) => `
              <article class="list-item">
                <div>
                  ${badge(item.status)}
                  <strong>${escapeHtml(item.command || item.mode || "request")}</strong>
                  <p>${escapeHtml(item.result_summary || item.prompt || "처리 중")}</p>
                  <span class="meta">${escapeHtml(item.provider)} · ${escapeHtml(item.model)} · ${fmtDate(item.created_at)}</span>
                </div>
              </article>
            `,
          )
          .join("");
}

function renderFailures() {
  const items = state.summary?.recent_failures || [];
  $("failureList").innerHTML =
    items.length === 0
      ? `<div class="empty">최근 실패 없음</div>`
      : items
          .map(
            (item) => `
              <article class="list-item danger">
                <div>
                  ${badge(item.status)}
                  <strong>${escapeHtml(item.command || item.mode || "request")}</strong>
                  <p>${escapeHtml(item.error || item.result_summary || "오류 상세 없음")}</p>
                  <span class="meta">${fmtDate(item.ended_at || item.created_at)}</span>
                </div>
              </article>
            `,
          )
          .join("");
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

function avatarText(item) {
  const source = String(item.adapter_type || item.name || "NA");
  const parts = source.split(/[-_\s]+/).filter(Boolean);
  return parts
    .slice(0, 2)
    .map((part) => part.slice(0, 1).toUpperCase())
    .join("") || "NA";
}

function renderOffice() {
  if (!$("officeMetrics")) return;
  const activeTaskStatuses = new Set(["queued", "running", "awaiting_approval", "blocked"]);
  const activeExecutionStatuses = new Set(["pending", "starting", "running", "awaiting_approval", "cancelling", "stale"]);
  const onlineHosts = state.hosts.filter((host) => !["offline", "stale"].includes(host.observed_status)).length;
  const cards = [
    ["온라인 Host", onlineHosts, "info"],
    ["활성 Agent", state.agents.filter((agent) => agent.enabled).length, ""],
    ["대기·진행 Task", state.tasks.filter((task) => activeTaskStatuses.has(task.status)).length, "warn"],
    ["활성 Execution", state.executions.filter((execution) => activeExecutionStatuses.has(execution.status)).length, "warn"],
    ["승인 대기", state.approvals.filter((approval) => approval.status === "pending").length, "danger"],
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

  const zones = [
    ["queue", "대기", "Queue"],
    ["work", "작업", "Working"],
    ["review", "검토", "Review"],
    ["done", "완료", "Done"],
    ["offline", "예외", "Exception"],
  ];
  const grouped = Object.fromEntries(zones.map(([key]) => [key, []]));
  state.executions.slice(0, 60).forEach((execution) => grouped[officeZone(execution.status)].push(execution));
  $("agentOffice").innerHTML = zones
    .map(([key, title, english]) => {
      const items = grouped[key].slice(0, 8);
      return `
        <section class="office-zone" data-zone="${key}" aria-label="${escapeHtml(title)} 구역">
          <div class="zone-heading"><h3>${escapeHtml(title)}</h3><span>${escapeHtml(english)} · ${grouped[key].length}</span></div>
          <div class="zone-agents">
            ${
              items.length
                ? items
                    .map(
                      (execution) => `
                        <div class="office-agent">
                          <button class="office-avatar" type="button" data-action="execution-detail" data-execution="${escapeHtml(execution.id)}" aria-label="${escapeHtml(execution.adapter_type)} 실행 상세" title="${escapeHtml(label(execution.status))}">${escapeHtml(avatarText(execution))}</button>
                          <strong>${escapeHtml(execution.adapter_type)}</strong>
                          <span>${escapeHtml(shortId(execution.id))}</span>
                        </div>
                      `,
                    )
                    .join("")
                : `<div class="empty">-</div>`
            }
          </div>
        </section>
      `;
    })
    .join("");

  $("executionTable").innerHTML = `
    <table>
      <thead><tr><th>상태</th><th>Adapter</th><th>Task</th><th>Host</th><th>신뢰도</th><th>갱신</th></tr></thead>
      <tbody>
        ${state.executions
          .slice(0, 30)
          .map(
            (execution) => `
              <tr>
                <td>${badge(execution.status)}</td>
                <td><button class="link-button" type="button" data-action="execution-detail" data-execution="${escapeHtml(execution.id)}">${escapeHtml(execution.adapter_type)}</button><br><code>${escapeHtml(shortId(execution.id))}</code></td>
                <td><code>${escapeHtml(shortId(execution.task_id))}</code></td>
                <td>${escapeHtml(execution.host_id ? shortId(execution.host_id) : "-")}</td>
                <td>${Math.round((execution.status_confidence || 0) * 100)}%</td>
                <td>${fmtDate(execution.updated_at)}</td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;

  const pendingApprovals = state.approvals.filter((approval) => approval.status === "pending");
  $("approvalList").innerHTML = pendingApprovals.length
    ? pendingApprovals
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
        .join("")
    : `<div class="empty">승인 대기 없음</div>`;

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
  $("agentStatusTable").innerHTML = `
    <table>
      <thead><tr><th>종류</th><th>이름·ID</th><th>상태</th><th>역할·Adapter</th><th>마지막 확인</th></tr></thead>
      <tbody>${[...hostRows, ...agentRows].join("")}</tbody>
    </table>
  `;
}

async function openExecutionDetail(executionId) {
  const execution = await api(`/v1/executions/${encodeURIComponent(executionId)}`);
  $("executionDrawer").hidden = false;
  $("executionDetail").innerHTML = `
    <div class="detail-block"><strong>상태</strong><span>${badge(execution.status)}</span></div>
    <div class="detail-block"><strong>Execution ID</strong><code>${escapeHtml(execution.id)}</code></div>
    <div class="detail-block"><strong>Task ID</strong><code>${escapeHtml(execution.task_id)}</code></div>
    <div class="detail-block"><strong>Adapter</strong><span>${escapeHtml(execution.adapter_type)}</span></div>
    <div class="detail-block"><strong>작업 경로</strong><code>${escapeHtml(execution.workdir || "-")}</code></div>
    <div class="detail-block"><strong>시작·종료</strong><span>${fmtDate(execution.started_at)}<br>${fmtDate(execution.ended_at)}</span></div>
    <div class="detail-block"><strong>판정 신뢰도</strong><span>${Math.round((execution.status_confidence || 0) * 100)}%</span></div>
    <div class="detail-block"><strong>오류</strong><p>${escapeHtml(execution.error || "-")}</p></div>
    <div class="detail-block"><strong>최근 이벤트</strong>${(execution.events || [])
      .slice(-12)
      .reverse()
      .map((event) => `<p><code>${escapeHtml(event.event_type)}</code> ${escapeHtml(event.message || label(event.status))}<br><span class="meta">${fmtDate(event.created_at)}</span></p>`)
      .join("")}</div>
  `;
}

function renderRequests() {
  $("requestTable").innerHTML = `
    <table>
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
        ${state.requests
          .map(
            (item) => `
              <tr>
                <td>${badge(item.status)}</td>
                <td><strong>${escapeHtml(item.command || "message")}</strong><br><span class="meta">${escapeHtml(item.prompt).slice(0, 180)}</span></td>
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
  `;
}

function renderUsage() {
  const max = Math.max(1, ...state.usage.map((item) => item.requests || 0));
  $("usageChart").innerHTML =
    state.usage.length === 0
      ? `<div class="empty">사용량 데이터 없음</div>`
      : state.usage
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
          .join("");
}

function renderProjects() {
  $("projectList").innerHTML =
    state.projects.length === 0
      ? `<div class="empty">프로젝트 없음</div>`
      : state.projects
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
                          ${badge(phase.status)}
                          <strong>${escapeHtml(phase.title)}</strong>
                          <p>${escapeHtml(phase.summary || "요약 없음")}</p>
                          <span class="meta">${escapeHtml(phase.next_action || "다음 작업 없음")}</span>
                          <button class="button small secondary" data-action="check-phase" data-project="${escapeHtml(project.id)}" data-phase="${escapeHtml(phase.phase_key)}" type="button">체크</button>
                        </section>
                      `,
                    )
                    .join("")}
                </div>
              </article>
            `,
          )
          .join("");
}

function renderAudit() {
  $("auditLog").innerHTML =
    state.audit.length === 0
      ? `<div class="empty">감사 로그 없음</div>`
      : state.audit
          .map(
            (entry) => `
              <article class="audit-item">
                <span>${fmtDate(entry.created_at)}</span>
                <strong>${escapeHtml(entry.action)}</strong>
                <span>${escapeHtml(entry.actor)} · ${escapeHtml(entry.entity_type)}:${escapeHtml(entry.entity_id)}</span>
              </article>
            `,
          )
          .join("");
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

  $("memoryList").innerHTML = state.memories.length ? state.memories
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
          .join("") : '<div class="empty">기억 후보 없음. 필요한 경우 요청 이력에서 후보를 추출하세요.</div>';
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
  button.disabled = true;
  try {
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
  state.wikiScope = state.wikiScopes[$("wikiScope").value] || null;
  loadWikiEntries().catch((error) => alert(error.message));
});
$("wikiSearchBtn").addEventListener("click", () => {
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
    $("unlockControlBtn").textContent = "제어 활성";
    $("unlockControlBtn").disabled = true;
  } catch (error) {
    state.controlToken = previous;
    alert(error.message);
  }
});
$("usagePeriod").addEventListener("change", () => loadAll());
$("workRecordScope").addEventListener("change", async (event) => {
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
  $("executionDrawer").hidden = true;
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
  $("streamStatus").title = "조회에 인증이 필요하면 제어 활성 버튼에서 토큰을 입력하세요.";
  console.error("Dashboard load failed", error.name);
});

connectEventStream();
