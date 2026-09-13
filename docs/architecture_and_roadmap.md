# NyaNya Agent Architecture and Roadmap

supersede earlier callback-only execution, general-file write-hold and legacy mirroring
statements for normal terminal/Discord operations. Retain historical verification
and remaining delivery/session/platform limitations; source changes are not deployment.



## Product boundary

NyaNya Agent is a local-first Python **Local Control Plane**. It accepts
terminal or connector requests, applies workspace and approval policy, routes
approved work to configured runtimes, and records operational state in one
SQLite execution ledger.

It is not a replacement for Codex, Antigravity, tmux, Tailscale, or an LLM
runtime. Those systems remain independent behind explicit adapters. Orca is not
part of the current product direction.

## Component ownership

| Component | Responsibility |
|---|---|
| Python runtime | Provider calls, bridge policy, queues, execution adapters, memory, and dashboard API |
| TypeScript CLI | Setup, configuration, diagnostics, state backup, service management, and Python entrypoints |
| SQLite control plane | Tasks, executions, events, approvals, artifacts, leases, projects, Codex sessions, and host observations |
| Discord bridge | Current authenticated request intake, progress replies, commands, and controlled file delivery |
| Terminal CLI | Local synchronous facade over the same durable task service |
| Dashboard | Lower-priority local monitoring and authenticated management surface |
| External runtimes | Codex, Antigravity, tmux, and local model execution |

## Request lifecycle

1. A request enters through the terminal or an enabled connector.
2. The task service resolves or creates the workspace project and writes one
   durable `agent_tasks` row before calling an external provider or CLI.
3. Policy assigns risk, approval requirements, and an execution adapter.
4. The task service creates/adopts one current `executions` row and records
   append-only events, queue status, cancellation, and terminal evidence.
5. A Codex-routed task is linked to a project-scoped `codex_sessions` record.
6. The dashboard reads the ledger for monitoring and authenticated control.
7. Legacy request/project tables remain compatibility projections until a later
   migration removes the dual-store boundary.

## Current implemented baseline

- npm-distributed TypeScript CLI with a managed Python environment
- Discord bridge as the current supported connector; Telegram remains optional
- plan-first approval for side-effecting requests
- per-user queue and task-status commands
- SQLite dashboard, projects, phase tracking, and approved memory retrieval
- task, execution, event, approval, artifact, writer-lease, project, and
  Codex-session ledger
- common durable task service used by terminal and Discord execution paths
- subprocess, tmux, Codex, and Antigravity adapters; Orca is excluded from the
  default registry
- SSE dashboard updates, cancellation, retry, and recovery reconciliation
- backup, restore, LaunchAgent, release, and privacy validation tooling

## Near-term roadmap

1. Replace legacy request/project synchronization with ledger-backed projections.
2. Complete live backend and Discord acceptance tests after authentication.
3. Add local-model profiles that separate public aliases from private model paths
   and collect measured VRAM/GPU/CPU/resource evidence.
4. Add model-routing policy and persist complexity/importance decisions.
5. Add a private Tailscale transport and a second Mac mini worker only after
   host authorization, credential, and recovery design is reviewed.
6. Exercise backup, restore, restart, cancellation, and failed-adapter recovery
   as repeatable operational drills.

## Deferred remote work

Mac-to-Mac networking, remote worker operation, SSH hardening, public port
removal, and Wake-on-LAN relay remain deferred until the operator starts the
remote-host project. Tailscale is an acceptable future private transport; it is
not configured by this repository yet. The private remote-access plan is
intentionally excluded from Git.

## Non-goals

- unrestricted autonomous writes
- public unauthenticated dashboard exposure
- credential synchronization between hosts
- open-ended bot-to-bot conversation loops
- replacing mature terminal, worktree, VPN, or model runtimes
