# Local Control Plane Implementation

2026-09-12 follow-up: [P0 execution contracts and verification](p0_execution_20260912.md)
supersede earlier callback-only execution, general-file write-hold and legacy mirroring
statements for normal terminal/Discord operations. Retain historical verification
and remaining delivery/session/platform limitations; source changes are not deployment.


> Current implementation update (2026-09-10): [CORE-STAB-01](core_stabilization_20260910.md) records schema-v3 claims/results, manual recovery holds, typed outcomes and the remaining worker/approval/migration gaps. Older phase descriptions below are design/history where they conflict with that update. This is not a stable-release or live-acceptance declaration.

Status: first implementation slice completed; migration work remains

## Accepted product direction

NyaNya Agent is a **Local Control Plane**, not only a lightweight messenger
wrapper. The operator can request work remotely through a connector and inspect
or manage it later through durable local state.

The current supported slice is:

- terminal requests;
- Discord requests and controlled file delivery;
- one local provider or Codex CLI delegation;
- SQLite task/execution/event history;
- project and logical Codex-session grouping;
- local monitoring and authenticated dashboard control.

Telegram remains optional compatibility code. Slack, Kakao, Google Workspace,
additional local models, and the second Mac mini are later adapters. Orca is not
used in the current product direction. Tailscale is an acceptable future private
transport, but this repository does not configure it.

## Authoritative flow

```text
terminal / Discord / future connector
                 |
                 v
       DurableTaskService.submit()
                 |
       SQLite agent_tasks (queued)
                 |
       project + codex_session link
                 |
       SQLite executions + append-only events
                 |
       provider / Codex / subprocess adapter
                 |
       result + artifact + delivery projection
```

The invariant is: no provider, CLI, subprocess, or future remote-host work
starts before its durable task exists. The service owns per-owner queueing,
writer leases, cancellation signalling, execution status, and final response
delivery. Callback functions remain process-local; their task and execution
records remain durable.

## SQLite model

| Record | Role |
|---|---|
| `execution_projects` | Stable project/workspace identity and lifecycle |
| `codex_sessions` | Project-scoped logical session key, model, workspace, and optional external ID |
| `agent_tasks` | User intent, queue status, owner, priority, project/session links |
| `executions` | One concrete attempt and terminal evidence for a task |
| `execution_events` | Append-only status and progress history |
| `approvals` | Exact side-effect decision with expiry and audit trail |
| `artifacts` | Produced file metadata and task/execution relationship |
| `writer_leases` | Fenced single-writer coordination |

Schema version 2 adds projects and Codex-session links to the existing execution
ledger. `agent_requests` and the older dashboard project tables remain a
compatibility projection during migration; they are not the target ownership
model.

The current Codex CLI invocation remains ephemeral. Therefore a
`codex_sessions` row groups related NyaNya tasks but does not yet replay a
Codex conversation after restart. The `external_session_id` field is reserved
for a future verified persistent Codex integration.

## Interface responsibilities

### Terminal

`nyanya --prompt` and the interactive REPL use `DurableTaskService.run_sync()`.
They wait for the same worker result while persisting task and execution state.

### Discord

Discord remains the first remote connector. Normal provider/Codex requests,
queue/cancel commands, and file uploads use the durable service. Request rows
are mirrored for compatibility and can be inspected through the execution-ledger
task ID.

### Dashboard

The dashboard is monitoring-first. It exposes ledger-backed hosts, tasks,
executions, approvals, events, execution projects, and Codex sessions. Mutating
routes remain authenticated. A dashboard-created task is a durable management
record; automatic execution from a separate dashboard process is not yet a
worker-claim feature.

### Policy and governance

Human-maintained Markdown is the canonical policy surface:

- `prompts/policy.md`: universal mission, execution, approval, privacy, and connector rules;
- `prompts/policy_technical.md`: workspace, process, remote-host, and model-routing constraints;
- `prompts/policy_governance.md`: decision rights, change control, review gates, and data lifecycle.

Runtime code enforces hard boundaries. The Markdown documents define the
operator-visible policy contract and are injected into the bridge operating
protocol.

## Current limitations to resolve

1. Legacy request/project mirroring still creates a dual persistence boundary.
2. A process restart preserves records but cannot automatically resume a
   process-local provider callback.
3. Dashboard retry creates a queued record but needs a worker-claim protocol
   to execute when no bridge process owns the callback.
4. Project grouping currently derives from the assigned workspace; explicit
   project selection in connector commands is not yet implemented.
5. Codex session grouping is logical until a persistent external session
   contract is verified.
6. Automatic multi-model routing and measured VRAM/GPU/CPU scheduling are not
   implemented; model/profile choice remains configuration-driven.
7. Tailscale host registration, authorization, transport, heartbeat, and
   recovery are design work only.

## Recommended next phases

### Phase A — Stabilize the current slice

- complete live Discord and backend acceptance scenarios;
- exercise backup, restore, cancellation, retry, restart, and failed-adapter
  recovery;
- add explicit project/session selection and task query views;
- document the compatibility window for legacy tables.

### Phase B — Remove the dual write model

- create ledger-backed request and project read projections;
- migrate memory references from request IDs to durable task/event IDs;
- stop runtime writes from `dashboard_store` into the execution ledger;
- retain a read-only compatibility reader for one planned release window;
- remove circular store ownership after migration verification.

### Phase C — Remote worker over private transport

- define host identity and per-host authorization;
- use Tailscale only as private transport, never as authorization;
- add worker claim/lease/recovery semantics;
- test credential non-synchronization, stale hosts, cancellation, and rollback
  on both Mac minis.

### Phase D — Resource-aware model routing

- create stable public model profiles with private local paths outside source;
- collect reproducible CPU, GPU, VRAM, latency, context, and failure evidence;
- define complexity/importance/risk routing rules;
- persist the routing decision and reason in task metadata;
- measure cost/quality before selecting defaults.

## Verification baseline

The implementation slice is considered healthy when these pass together:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
.venv/bin/ruff check src/nyanya_agent tests
npm run typecheck --if-present
node --check src/nyanya_agent/dashboard_static/app.js
./packaging/release/verify_release.sh
```

Live service checks and user-visible acceptance tests are separate evidence and
must be rerun after credentials, host, or service state changes.
