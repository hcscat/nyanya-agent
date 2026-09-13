# NyaNya Agent Architecture Diagnostic

Status: baseline diagnosis with 2026-09-01 implementation follow-up

Review date: 2026-08-26

Implementation follow-up: 2026-09-01

The accepted product decision is **Option B: Local Control Plane**. The first
migration slice is now implemented: SQLite schema version 2 adds
`execution_projects` and `codex_sessions`, `task_service.py` provides the common
durable submission/queue/execution path, terminal and Discord work use it, and
the dashboard exposes ledger-backed project/session/task queries. Legacy request
and project tables remain compatibility projections; their removal is a later
phase.

## Executive conclusion

NyaNya Agent is no longer merely a lightweight messenger wrapper. The current
repository contains four product surfaces in one deployable unit:

1. a local request gateway for terminal, Discord, and Telegram;
2. policy, planning, routing, and provider invocation;
3. a durable execution-control plane with approvals, leases, events, recovery,
   projects, and memory;
4. an npm installer/service manager plus a local dashboard.

The repository has valuable safety and operations foundations, but its current
shape is transitional. The highest architectural risk is not raw size. It is
that the original messenger execution path and the newer execution ledger both
exist, while legacy dashboard records are mirrored into the newer tables. This
creates two concepts of a task, two status lifecycles, and synchronization code
between them.

The recommended direction is **not a rewrite**. The operator accepted the local
control-plane direction: one durable execution ledger, one application service,
and optional interfaces/adapters around it. Dashboard remains monitoring-first;
Discord is the current connector; Tailscale is a future private transport;
Orca is excluded from the default product.

## Review method and evidence

This diagnosis inspected the repository history, current documentation,
Python/TypeScript implementation, database schemas, dashboard routes, release
tooling, and tests. It also performed read-only live checks of the installed
services and public npm version.

Verified snapshot:

- Branch `main` matched `origin/main` at commit `2182510` during review.
- `package.json` and public npm both reported version `0.3.0`.
- Discord bridge, dashboard, and memory worker were running.
- Dashboard health returned `status=ok` on its local endpoint.
- The repository had one untracked user-owned `AGENTS.md`; it was preserved.
- No npm publish workflow existed; CI only performed build, tests, audits, and
  release-content verification.

The review did not restart services, send messenger test requests, mutate live
data, publish a package, or run the five operator acceptance scenarios.

## How the system evolved

Repository history shows a rapid additive evolution:

| Period | Main addition | Architectural effect |
|---|---|---|
| 2026-06-07 | Core agent, Discord/Telegram bridges, policy, runtime | Original direct local-agent path |
| 2026-06-07 | Python service manager and backend auth commands | Runtime lifecycle enters product code |
| 2026-06-14 | Dashboard and dashboard store | First durable request/project record model |
| 2026-06-20 | Memory worker and safety policy | Memory and policy become independent subsystems |
| 2026-06-22 | Queue and progress updates | In-process bridge scheduling grows |
| 2026-07-07 | TypeScript npm CLI and packaging | A second management surface is added |
| 2026-07-13 | State/config/backup and CI | Distribution becomes a major concern |
| 2026-07-20 | Execution ledger, adapters, recovery, Orca | A second, durable execution model is added |
| 2026-07-30 | Planning protocol and docs consolidation | Safety contract spans prompts and runtime |

This history explains the current seams: most subsystems were sensible
increments, but their integration contracts were not fully consolidated after
the execution control plane arrived.

## Current logical architecture

```text
Ingress
  terminal CLI       Discord bridge       Telegram bridge       dashboard API
       |                    |                    |                    |
       +--------------------+--------------------+--------------------+
                            |
               policy / planning / routing
             bridge_policy + bridge_runtime + prompts
                            |
             +--------------+----------------+
             |                               |
   original bridge path              execution control plane
   in-memory owner queue              task/execution/event ledger
   direct provider/Codex call         approval + lease + recovery
             |                               |
             +---------------+---------------+
                             |
         providers and runtime adapters
   configured backend / subprocess / tmux / Orca / Codex / Antigravity
                             |
                     local artifacts/results

Persistence and operations
  legacy request/project/memory tables <-> execution-ledger mirror
  dashboard + memory worker + launchd manager + npm CLI
```

### Ownership by implementation language

- Python owns product behavior: providers, bridges, policy, queueing, dashboard,
  memory, persistence, execution adapters, service control, and recovery.
- TypeScript is primarily the npm-facing setup/config/doctor/state/service CLI
  and launches Python entry points.
- JavaScript/CSS provide the dashboard frontend.
- SQLite is intended to be the operational source of truth, but the bridge
  scheduler still has material in-memory state.

## Component inventory

| Area | Main modules | Current responsibility | Observation |
|---|---|---|---|
| Agent/provider core | `core.py` | Config loading, provider calls, CLI loop | Broad base module; provider and UI concerns coexist |
| Bridge policy | `bridge_constants.py`, `bridge_policy.py` | Commands, risk, workspace, planning, help | Safety-critical rules are distributed across code and prompts |
| Bridge runtime | `bridge_runtime.py`, `bridge_store.py` | Routing, direct execution, owner queue, progress | Queue/current-task state is process memory |
| Messenger ingress | `discord_bridge.py`, `telegram_bridge.py` | Authorization, files, delivery | Shared store, but feature depth and implementation are asymmetric |
| Legacy operations store | `dashboard_store.py` | Requests, projects, phase checks, audit, memory | 1,400+ lines and still central to bridge telemetry |
| Execution ledger | `execution_store.py` | Tasks, executions, sessions, events, approvals, artifacts, leases | Strong model, but mirrors legacy records rather than replacing them |
| Runtime coordination | `execution_runtime.py`, `execution_adapters.py` | Start/observe/cancel/recover adapters | Useful contract; not the universal bridge execution path |
| Dashboard | `dashboard_api.py`, static assets | Read/control APIs and operator UI | Exposes both legacy and new models in one API |
| Memory | `memory_worker.py`, dashboard-store memory functions | Candidate extraction, approval, search, graph | Coupled to legacy request records |
| Lifecycle | `manager.py`, shell scripts, TypeScript CLI | launchd, health, setup, state backup | Python and TypeScript management responsibilities overlap |
| Distribution | package metadata, packaging scripts, CI | npm/Python package and privacy gate | Good release guardrails; publish authentication remains manual |

## Quantitative shape

The largest implementation files at review time were approximately:

| File | Lines | Signal |
|---|---:|---|
| `dashboard_store.py` | 1,439 | request/project/audit/memory responsibilities combined |
| `execution_store.py` | 1,427 | schema plus every ledger repository operation |
| `execution_adapters.py` | 917 | five adapter implementations and artifact collection |
| `dashboard_static/styles.css` | 888 | large single dashboard stylesheet |
| `manager.py` | 866 | all service/config/health operations |
| `dashboard_static/app.js` | 836 | single-file dashboard client |
| `discord_bridge.py` | 608 | authorization, command handling, files, telemetry, delivery |
| `bridge_store.py` | 606 | conversation, queue, execution, cancellation, recording |
| `core.py` | 590 | provider and terminal-agent foundation |
| `bridge_policy.py` | 575 | safety and planning policy |

There were 55 statically counted Python test functions across 14 test modules.
This is useful contract coverage, but file count and line count are indicators,
not quality scores.

## What is already strong

### Explicit safety boundary

The project consistently treats workspace allowlists, risk classification,
approval, local-only dashboard defaults, and public/private source separation as
first-class concerns. Mutating dashboard routes require a control credential,
and write-capable coordinated executions require persisted approval and a writer
lease.

### Durable execution concepts

The new ledger has the right operational concepts for serious local automation:
separate task and execution states, append-only events, runtime sessions,
confidence, approvals, artifacts, host/profile inventory, leases with fencing,
and stale/lost recovery.

### Adapter isolation

Subprocess, tmux, Orca, Codex, and Antigravity share a protocol and capability
description. That is a sound seam for optional runtimes and future host support.

### Release and privacy discipline

The npm package has an allowlist/denylist release verifier, CI audits, clean
packaging rules, and documented secret boundaries. Generated/private documents
and runtime state are ignored.

### Local-first operational posture

The dashboard binds locally by default, bridge credentials remain local, and
remote access is deferred behind explicit authenticated/private-network design.

## Primary architectural findings

### P0 — Two task/execution models coexist (partially resolved)

The original diagnosis found that `NyaNyaConversationStore` scheduled owner
tasks in process memory and executed providers directly. The bridge now submits
through `DurableTaskService`, which persists task queue state, one current
execution, cancellation, leases, and terminal events before the provider/Codex
call. The runtime adapter coordinator remains a separate lower-level entrypoint
for command-oriented adapter tests and dashboard operations.

Consequences:

- A “task” means different things depending on ingress and route.
- A running process still owns callback functions and conversation memory, so a
  restart cannot resume an in-flight Python callback automatically. Persisted
  task/execution state remains available for reconciliation and future worker
  claim/resume logic.
- Approval, writer lease, cancellation, retry, heartbeat, and recovery are not
  guaranteed to apply uniformly to messenger work.
- Dashboard status can represent a mirrored observation rather than the
  authoritative execution that drove the work.

Implementation decision: all currently executed terminal and Discord ingress
creates the same durable task before execution. Remaining work is to make
progress delivery event-driven and to add a persistent worker claim protocol
for post-restart queued work.

### P0 — Legacy and new persistence models are mutually coupled (migration remains)

`dashboard_store` lazily imports `execution_store` to mirror requests, while
`execution_store` imports `dashboard_store` as its legacy database helper. The
dashboard initializes and exposes both.

Consequences:

- Schema ownership and migration direction are ambiguous.
- Circular dependency makes change and testing harder.
- Dual writes/reconciliation can drift or duplicate state semantics.
- Memory and project features remain anchored to legacy request IDs.

Decision: create one persistence boundary. The new execution ledger is the
authoritative write model; legacy request/project tables are retained only for
compatibility projections during a defined migration window. Later work must
remove bidirectional runtime mirroring and circular store ownership.

### P1 — Product identity and default scope are broader than “lightweight”

The default repository includes bridges, provider execution, dashboard,
projects, memory graphing, execution control, five runtime adapters, service
management, state backup, installers, and release tooling.

Consequences:

- Users cannot easily tell the minimum product from optional operations tooling.
- Every release has a large verification surface.
- Documentation and support must explain features that may be irrelevant to a
  simple local bridge user.

Decision: define feature tiers and packaging boundaries before adding features.

### P1 — Safety and planning policy has several sources of truth

Rules appear in constants, bridge policy/runtime code, system and memory prompts,
messenger help, dashboard behavior, and documentation. The project correctly
requires these to stay aligned, but alignment currently depends on discipline.

Consequences:

- A new command or risk class can behave differently across ingress surfaces.
- Prompt text can promise controls not enforced by the execution path.
- Tests cover components more than an executable end-to-end policy contract.

Decision: represent command/risk/approval/planning policy as typed domain data,
generate help/prompt fragments where possible, and test the policy matrix once.

### P1 — Management responsibilities overlap across languages

The TypeScript CLI configures, diagnoses, backs up, and invokes services, while
Python `manager.py` also owns launchd generation, lifecycle, health, auth, and
Discord account operations. Shell wrappers add a third entry surface.

Consequences:

- Platform behavior can drift between npm CLI, Python manager, and scripts.
- Cross-platform distribution claims are constrained by macOS-specific service
  management.
- Maintenance cost grows for command aliases and compatibility wrappers.

Decision: keep TypeScript as a thin public installer/launcher and define one
Python service-control API, or move lifecycle entirely to TypeScript. Do not
continue duplicating behavior.

### P1 — Large modules hide subsystem boundaries

The largest Python stores mix schema, repository methods, redaction, analytics,
memory extraction, graph construction, and compatibility. The dashboard client
and CSS are also single large files.

Consequences:

- Changes have broad regression surfaces.
- It is difficult to assign ownership or remove optional features.
- Domain logic is harder to test without SQLite/API/UI setup.

Decision: split only after the target boundaries are accepted. Mechanical file
splitting before resolving the two execution models would preserve the wrong
architecture in more files.

### P2 — Live acceptance and failure drills lag implementation breadth

Unit/integration tests cover stores, adapters, runtime paths, CLI safety, and
dashboard APIs. The documented live messenger, file delivery, cancellation,
backup/restore, restart, and failed-adapter drills remain important.

Decision: establish a repeatable acceptance matrix before resizing so removed or
moved functionality has observable compatibility criteria.

### P2 — Documentation has minor signs of drift

The documentation is substantially consolidated, but some operational text is
duplicated and current implementation detail is spread across multiple guides.
This is a maintenance signal rather than a runtime defect.

## Recommended target architecture

Define NyaNya as:

> A local operator gateway that converts authorized requests into durable tasks,
> applies one safety policy, delegates execution through explicit adapters, and
> reports auditable results to optional interfaces.

```text
                    Optional ingress adapters
          CLI       Discord       Telegram       Dashboard
            \          |             |              /
             +---------+-------------+-------------+
                               |
                    Application service layer
             submit / approve / cancel / retry / observe
                               |
                Domain policy and task state machine
          planning / risk / authorization / lease / events
                               |
                    Single execution ledger port
                               |
                SQLite repository + schema migrations
                               |
                    Execution adapter registry
          provider / subprocess / tmux / Orca / Codex / other
                               |
                 Artifact and delivery adapter ports

Optional supporting workers: memory extraction, dashboard projection,
notifications, backup. These consume ledger events; they do not create a second
task model.
```

### Proposed module boundaries

```text
domain/
  task.py               states and transition rules
  policy.py             risk, authorization, planning contract
  events.py             event types and redacted payload contract

application/
  task_service.py       submit, approve, start, cancel, retry, observe
  query_service.py      operator-facing read models

ports/
  execution.py          adapter protocol
  repository.py         ledger protocol
  delivery.py           messenger/result delivery protocol

adapters/
  ingress/              CLI, Discord, Telegram, dashboard
  execution/            provider, subprocess, tmux, Orca, Codex, Antigravity
  persistence/          SQLite and migrations
  delivery/             Discord, Telegram, terminal

workers/
  memory.py             optional event consumer
  recovery.py           stale-session reconciliation
```

These names are a design aid, not an instruction to perform a bulk move. The
first implementation step should establish interfaces around existing code.

## Product resizing choices for later review

### Option A — Lean gateway

Default: terminal + one configured provider + policy + SQLite task history.
Discord, Telegram, dashboard, memory, and external runtime adapters become
optional extras.

Best when install simplicity and small maintenance surface are the priority.

### Option B — Local control plane (recommended baseline)

Default: durable task ledger, CLI, dashboard, approval/recovery, and one provider.
Messenger bridges, memory, and advanced runtime adapters are optional feature
groups.

Best match for the valuable work already implemented while still allowing a
clear minimum product.

### Option C — Multi-agent operations platform

Keep all current surfaces and expand remote hosts, model profiles, scheduling,
and integrations.

This requires a larger security model, explicit plugin lifecycle, compatibility
policy, multi-host identity, observability, and a materially larger test/support
budget. It should not be the implicit result of incremental feature additions.

## Proposed phased follow-up

These are planning inputs, not committed dates.

### Phase 0 — Product decision and acceptance baseline

- Select Option A, B, or C and write explicit non-goals.
- Run and record the five operator-visible acceptance tests.
- Exercise backup/restore, restart, cancellation, and adapter-loss recovery.
- Build a capability matrix by ingress and runtime.
- Freeze new feature work until the task model decision is accepted.

Exit: one product statement, one supported capability matrix, one observed
baseline.

### Phase 1 — One authoritative task path

- Add an application task service in front of the current execution ledger.
- Make terminal, Discord, Telegram, and dashboard submit through it.
- Persist queue position and owner concurrency rules.
- Deliver progress from ledger events.
- Preserve compatibility IDs and define migration/rollback tooling.

Exit: every real request has one task, one current execution, and one event
stream before provider execution starts.

### Phase 2 — Remove runtime mirroring

- Migrate legacy requests/events to ledger records.
- Move project and memory references to stable task/event identifiers.
- Replace dashboard dual-store queries with projections from the ledger.
- Retain a read-only compatibility path for one defined release window.
- Remove circular store imports and reconciliation writes.

Exit: one schema owner and no bidirectional legacy synchronization.

### Phase 3 — Clarify packaging and service ownership

- Define core and optional dependency groups/features.
- Choose the single owner for service lifecycle and platform abstraction.
- Consolidate public CLI names and compatibility period.
- Separate macOS launchd support from portable runtime behavior.
- Keep npm release migration as an independent, controlled work item.

Exit: documented minimal install, optional features, and one management path.

### Phase 4 — Decompose and harden

- Split stores, API, dashboard client, and adapters along accepted boundaries.
- Centralize policy declarations and generate/test ingress-specific presentation.
- Add migration, fault-injection, privacy, and end-to-end acceptance tests.
- Add metrics for task latency, failure, recovery, queue age, and approvals.
- Re-evaluate remote-host work only after local invariants are proven.

Exit: smaller modules, enforced dependency direction, and repeatable release and
operational gates.

## Decisions the owner should make before detailed scheduling

1. Which product identity is correct: lean gateway, local control plane, or
   multi-agent operations platform?
2. Must projects and memory be core product features or optional dashboard
   modules?
3. Which execution adapters are officially supported versus experimental?
4. Is macOS the supported service platform, or must unattended service control
   be portable in the next release line?
5. Should messenger requests always use the durable coordinator, including
   low-risk conversational requests?
6. What compatibility window is required for existing SQLite state and CLI
   aliases?
7. Which operator-visible acceptance scenarios define “no regression” during
   resizing?

## Immediate recommendation

Do not begin with file moves, UI redesign, remote-host features, or a rewrite.
Approve the product option and durable-task invariant first. Then implement a
thin application service that can route one existing ingress through the ledger
end to end. Use that slice to measure complexity and migration risk before
committing to the full schedule.

## Scope exclusions

This review did not:

- change runtime architecture or database schemas;
- modify or restart local services;
- configure npm publishing or GitHub Actions releases;
- run live Discord/Telegram acceptance messages;
- inspect or expose credentials, private identifiers, or live data contents;
- estimate calendar duration without the owner's product-scope decisions.
