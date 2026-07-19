const state = {
  activeView: "main",
  summary: null,
  requests: [],
  usage: [],
  projects: [],
  audit: [],
  memories: [],
  memoryGraph: { nodes: [], edges: [], stats: {} },
  techStackGraph: { nodes: [], edges: [], stats: {} },
  hosts: [],
  agents: [],
  tasks: [],
  executions: [],
  approvals: [],
  controlToken: "",
  eventCursor: 0,
  eventSource: null,
  cy: null,
  techCy: null,
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
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("ko-KR", { hour12: false });
}

function fmtDuration(value) {
  if (value === null || value === undefined) return "-";
  if (value < 1000) return `${value}ms`;
  return `${(value / 1000).toFixed(1)}s`;
}

async function api(path, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const controlHeaders = method !== "GET" && state.controlToken ? { Authorization: `Bearer ${state.controlToken}` } : {};
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...controlHeaders, ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function loadAll() {
  const period = $("usagePeriod")?.value || "daily";
  const [
    summary,
    requests,
    usage,
    projects,
    audit,
    memories,
    memoryGraph,
    techStackGraph,
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
    api("/v1/memory-graph?limit=120"),
    api("/v1/tech-stack-graph?limit=120"),
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
  state.memoryGraph = memoryGraph;
  state.techStackGraph = techStackGraph;
  state.hosts = hosts;
  state.agents = agents;
  state.tasks = tasks;
  state.executions = executions;
  state.approvals = approvals;
  render();
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
  if (view === "memory") {
    window.setTimeout(() => {
      renderMemoryGraph();
      renderTechStackGraph();
      state.cy?.fit(undefined, 24);
      state.techCy?.fit(undefined, 24);
    }, 30);
  }
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
  const stats = state.memoryGraph?.stats || {};
  const cards = [
    ["전체 기억", stats.memories ?? state.memories.length, ""],
    ["검토 대기", stats.pending ?? 0, "warn"],
    ["승인", stats.approved ?? 0, "info"],
    ["타입", stats.types ?? 0, ""],
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

  $("memoryList").innerHTML =
    state.memories.length === 0
      ? `<div class="empty">기억 후보 없음. 요청 이력에서 후보를 추출하세요.</div>`
      : state.memories
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
                  <button class="button small secondary" data-action="memory-approve" data-memory="${escapeHtml(memory.id)}" type="button">승인</button>
                  <button class="button small secondary" data-action="memory-reject" data-memory="${escapeHtml(memory.id)}" type="button">거부</button>
                </div>
              </article>
            `,
          )
          .join("");

  renderMemoryGraph();
  renderTechStackGraph();
}

function graphElements(graph) {
  return [
    ...(graph.nodes || []).map((node) => ({
      data: {
        id: node.id,
        label: node.label,
        kind: node.kind,
        status: node.status,
        importance: node.importance || 1,
      },
    })),
    ...(graph.edges || []).map((edge, index) => ({
      data: {
        id: `edge-${index}`,
        source: edge.source,
        target: edge.target,
        label: edge.label,
        weight: edge.weight || 1,
      },
    })),
  ];
}

function graphStyle() {
  return [
    {
      selector: "node",
      style: {
        label: "data(label)",
        "background-color": "#1d63c7",
        color: "#1e2732",
        "font-size": 11,
        "text-valign": "bottom",
        "text-halign": "center",
        "text-wrap": "wrap",
        "text-max-width": 120,
        width: "mapData(importance, 1, 100, 24, 64)",
        height: "mapData(importance, 1, 100, 24, 64)",
      },
    },
    { selector: 'node[kind = "root"]', style: { "background-color": "#f0bd4a", width: 72, height: 72, "font-weight": 800 } },
    { selector: 'node[kind = "type"]', style: { "background-color": "#0d748a", color: "#0d3340", "font-weight": 700 } },
    { selector: 'node[kind = "technology"]', style: { "background-color": "#14764c", color: "#123524", "font-weight": 700 } },
    { selector: 'node[status = "pending"]', style: { "border-color": "#9a5a08", "border-width": 3 } },
    { selector: 'node[status = "approved"]', style: { "border-color": "#14764c", "border-width": 3 } },
    {
      selector: "edge",
      style: {
        width: "mapData(weight, 1, 10, 1, 5)",
        "line-color": "#a8b4c2",
        "target-arrow-color": "#a8b4c2",
        "target-arrow-shape": "triangle",
        "curve-style": "bezier",
      },
    },
  ];
}

function renderGraph({ containerId, graph, cyKey, emptyText }) {
  const container = $(containerId);
  if (!container) return;
  if (!window.cytoscape) {
    container.innerHTML = `<div class="empty">Cytoscape.js 로드 실패. 그래프 외 목록은 계속 사용할 수 있습니다.</div>`;
    return;
  }
  const elements = graphElements(graph || { nodes: [], edges: [] });
  if (elements.length <= 1) {
    container.innerHTML = `<div class="empty">${escapeHtml(emptyText)}</div>`;
    return;
  }
  if (!state[cyKey]) {
    state[cyKey] = cytoscape({
      container,
      style: graphStyle(),
      elements,
      layout: { name: "cose", animate: false, fit: true, padding: 24 },
    });
  } else {
    state[cyKey].elements().remove();
    state[cyKey].add(elements);
    state[cyKey].layout({ name: "cose", animate: false, fit: true, padding: 24 }).run();
  }
}

function renderMemoryGraph() {
  renderGraph({
    containerId: "memoryGraph",
    graph: state.memoryGraph,
    cyKey: "cy",
    emptyText: "표시할 기억 그래프 없음",
  });
}

function renderTechStackGraph() {
  renderGraph({
    containerId: "techStackGraph",
    graph: state.techStackGraph,
    cyKey: "techCy",
    emptyText: "표시할 기술스택 그래프 없음",
  });
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
  } catch (error) {
    alert(error.message);
  } finally {
    button.disabled = false;
  }
}

document.addEventListener("click", handleClick);
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
    await api("/v1/recovery/reconcile", { method: "POST" });
    $("unlockControlBtn").textContent = "제어 활성";
    $("unlockControlBtn").disabled = true;
  } catch (error) {
    state.controlToken = previous;
    alert(error.message);
  }
});
$("usagePeriod").addEventListener("change", () => loadAll());
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
  status.textContent = connected ? "실시간 연결" : "재연결 중";
}

function scheduleOperationReload() {
  window.clearTimeout(operationReloadTimer);
  operationReloadTimer = window.setTimeout(() => {
    loadOperations().catch(() => setStreamStatus(false));
  }, 180);
}

function connectEventStream() {
  state.eventSource?.close();
  const source = new EventSource(`/v1/events/stream?cursor=${state.eventCursor}`);
  state.eventSource = source;
  source.onopen = () => setStreamStatus(true);
  source.onerror = () => setStreamStatus(false);
  source.addEventListener("ledger", (event) => {
    const cursor = Number(event.lastEventId || 0);
    if (Number.isFinite(cursor)) state.eventCursor = Math.max(state.eventCursor, cursor);
    scheduleOperationReload();
  });
}

setView(location.hash.replace("#", ""), { updateHash: false });

loadAll().catch((error) => {
  document.body.innerHTML = `<main class="workspace"><section class="panel"><h1>Load failed</h1><pre>${escapeHtml(error.message)}</pre></section></main>`;
});

connectEventStream();
