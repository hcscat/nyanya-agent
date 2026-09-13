# NyaNya Execution Control Plane

2026-09-12 follow-up: [P0 execution contracts and verification](p0_execution_20260912.md)
supersede earlier callback-only execution, general-file write-hold and legacy mirroring
statements for normal terminal/Discord operations. Retain historical verification
and remaining delivery/session/platform limitations; source changes are not deployment.


> Current implementation update (2026-09-10): [CORE-STAB-01](core_stabilization_20260910.md) records schema-v3 claims/results, manual recovery holds, typed outcomes and the remaining worker/approval/migration gaps. Older phase descriptions below are design/history where they conflict with that update. This is not a stable-release or live-acceptance declaration.

## Scope

The control plane records and observes work executed by local or remote NyaNya
workers. It is the product's Local Control Plane: every provider, CLI,
subprocess, or future remote-host request must enter the durable task path
before execution. It does not expose the dashboard to the public internet, copy
OAuth credentials between hosts, or grant unattended writes by default.

## Data model

| Entity | Responsibility |
|---|---|
| `hosts` | Mac A/B identity, role, capability inventory, heartbeat, stale/offline projection |
| `agent_profiles` | Adapter, model, workspace root, and execution policy |
| `execution_projects` | Stable workspace/project identity and lifecycle |
| `codex_sessions` | Project-scoped logical Codex session identity and model/workspace metadata |
| `agent_tasks` | User intent, project/session linkage, and queue state |
| `executions` | One concrete attempt for a task, including status confidence and termination evidence |
| `runtime_sessions` | PID, tmux session, external handle, heartbeat, and persisted adapter handle |
| `execution_events` | Append-only ordered event stream with reconnect cursor |
| `approvals` | Expiring, auditable write or side-effect decisions |
| `artifacts` | File path, SHA-256, size, MIME type, and task/execution relationship |
| `writer_leases` | Single-writer lock with a monotonically increasing fence token |

`schema_migrations` and SQLite `user_version` are applied before the execution API starts. A changed checksum for an already-applied migration fails startup instead of silently mutating history.

`codex_sessions` currently provides a stable project/conversation grouping key
for NyaNya task management. The bridge still invokes the Codex CLI in ephemeral
mode, so this registry does not yet promise conversational context replay inside
Codex. A future persistent Codex session integration may populate
`external_session_id` after its CLI and recovery contract are verified.

## State model

Task states:

```text
queued -> running -> completed
   |         |  -> failed
   |         |  -> cancelled
   |         -> awaiting_approval -> running
   -> blocked -> queued
```

Execution states:

```text
pending -> starting -> running -> succeeded
                    |    |     -> failed
                    |    |     -> timed_out
                    |    |     -> cancelling -> cancelled
                    |    -> awaiting_approval -> running
                    -> stale -> running | lost
```

Terminal execution status is trusted at confidence `1.0` only when an atomic completion marker exists. A live managed child, tmux session, or PID provides progressively weaker evidence. Missing process and marker evidence becomes `lost`, not `succeeded`.

## Adapter contract

Every adapter exposes:

- capability inventory and a runtime probe;
- start with a list-form command, bounded workspace, timeout, and private output directory;
- observe with status, confidence, exit code, output tail, and evidence;
- cancellation without a shell-expanded user command;
- reconnect from a persisted handle where supported.

Implemented adapters:

| Adapter | Persistence | Recovery evidence |
|---|---:|---|
| managed subprocess | process lifetime | managed child, PID, atomic marker |
| tmux | host/session lifetime | tmux session, pane/log, atomic marker |
| Codex | subprocess | explicit NyaNya profile and sandbox plus marker |
| Antigravity | subprocess | explicit `--sandbox`, auth probe, marker |

The current default adapter registry deliberately excludes Orca. The existing
adapter implementation remains isolated for historical compatibility tests, but
the product does not select or operate it.

## Approval and writer lease

Mutating work follows this order:

1. Create an approval row for the exact task and action.
2. Record an operator decision through the authenticated control API.
3. Acquire a writer lease for the repository or worktree resource.
4. Persist the fence token in execution metadata.
5. Start the adapter.
6. Renew heartbeat while work is active.
7. Release the lease on success, failure, timeout, cancellation, or recovery.

An approval ID for another task, a pending/rejected approval, or a busy writer lease fails before command start.

## API security

Read APIs remain bound to the local dashboard. Mutating routes require a bearer token or `X-Nyanya-Control-Token`. The token comes from an environment variable or an owner-only local file and is never returned by `/health`.

The following routes require control authentication:

- project creation, phase updates, and phase checks;
- memory extraction and memory status updates;
- task creation, cancellation, and retry;
- execution cancellation;
- approval decisions;
- active-execution recovery reconciliation.

When no token exists, control routes return `503`. A wrong or missing token returns `401` when control authentication is configured.

The dashboard asks for the token only when the operator unlocks controls. It keeps the value in JavaScript memory for the current page lifetime and does not place it in HTML, a URL, logs, `localStorage`, or `sessionStorage`.

## SSE reconnect

`GET /v1/events/stream` emits ordered events with the SQLite sequence as the SSE `id`. Clients reconnect with `Last-Event-ID` or the `cursor` query parameter. The browser refreshes only the operational datasets after new events and uses keepalive comments during idle periods.

## Host heartbeat

The dashboard records a local host heartbeat every 30 seconds. Default projections are:

- less than 90 seconds: stored status;
- 90 to 299 seconds: `stale`;
- 300 seconds or more: `offline`.

The stored heartbeat is preserved; `observed_status` is computed on read so operators can distinguish raw and projected state.

## Backup and recovery

Create an online backup:

```bash
./scripts/backup_state.sh
```

Recovery sequence:

1. stop the Discord bridge, dashboard, and memory worker;
2. preserve current logs and create a last-chance backup;
3. verify the selected backup with `PRAGMA integrity_check`;
4. restore with `NYANYA_RESTORE_CONFIRM=YES`;
5. start dashboard and verify `/health` plus schema version;
6. start memory worker and bridge;
7. call authenticated `/v1/recovery/reconcile`;
8. keep remote writes disabled until active executions and writer leases reconcile.

## Remote boundary

Tailscale is an acceptable future private transport between approved Mac mini
hosts. The application continues to bind to `127.0.0.1` unless a separately
reviewed authenticated private proxy is configured. Tailscale connectivity does
not grant task authorization, workspace access, or credential synchronization.

The future remote worker must register host identity, capabilities, heartbeat,
task ownership, leases, and recovery evidence in this ledger. It is a separate
phase from the current local/Discord implementation.
