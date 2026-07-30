# NyaNya Agent Architecture and Roadmap

## Product boundary

NyaNya Agent is a local-first Python agent wrapper and operations control plane.
It accepts terminal, Discord, or Telegram requests, applies workspace and approval
policy, delegates suitable work to configured runtimes, and records operational
state in SQLite.

It is not a replacement for Codex, Antigravity, Orca, tmux, a private network, or
an LLM runtime. Those systems remain behind explicit adapters.

## Component ownership

| Component | Responsibility |
|---|---|
| Python runtime | Provider calls, bridge policy, queues, execution adapters, memory, and dashboard API |
| TypeScript CLI | Setup, configuration, diagnostics, state backup, service management, and Python entrypoints |
| SQLite control plane | Tasks, executions, events, approvals, artifacts, leases, and host observations |
| Discord and Telegram bridges | Authenticated request intake, progress replies, commands, and controlled file delivery |
| Dashboard | Local operational visibility and authenticated control actions |
| External runtimes | Codex, Antigravity, Orca, tmux, and local model execution |

## Request lifecycle

1. A request enters through CLI or an enabled messenger bridge.
2. NyaNya records the request and resolves its workspace.
3. Policy assigns risk, approval requirements, and an execution adapter.
4. The agent states the objective, scope, schedule, detailed procedure, and
   verification criteria before substantial work.
5. Higher-risk work waits for explicit approval.
6. The adapter runs the task while events and progress are recorded.
7. The result, artifacts, and termination evidence are stored and reported.
8. A material objective or scope change pauses execution for a revised plan.

## Current implemented baseline

- npm-distributed TypeScript CLI with a managed Python environment
- Discord and Telegram bridges
- plan-first approval for side-effecting requests
- per-user queue and task-status commands
- SQLite dashboard, projects, phase tracking, and approved memory retrieval
- task, execution, event, approval, artifact, and writer-lease ledger
- subprocess, tmux, Orca, Codex, and Antigravity adapters
- SSE dashboard updates, cancellation, retry, and recovery reconciliation
- backup, restore, LaunchAgent, release, and privacy validation tooling

## Near-term roadmap

1. Apply objective, scope, schedule, procedure, and drift-control rules to every
   substantial task, not only high-risk side effects.
2. Complete live backend and messenger acceptance tests after authentication.
3. Add local-model profiles that separate public aliases from private model paths.
4. Reconcile the public CLI around `nyanya` and retain compatibility commands
   only when they provide an explicit migration benefit.
5. Exercise backup, restore, restart, and failed-adapter recovery as repeatable
   operational drills.

## Deferred remote work

Mac-to-Mac networking, remote Orca operation, SSH hardening, public port removal,
and Wake-on-LAN relay remain deferred until the operator starts the remote-host
project. The private remote-access plan is intentionally excluded from Git.

## Non-goals

- unrestricted autonomous writes
- public unauthenticated dashboard exposure
- credential synchronization between hosts
- open-ended bot-to-bot conversation loops
- replacing mature terminal, worktree, VPN, or model runtimes
