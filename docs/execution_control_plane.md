# NyaNya Execution Control Plane

This document retains the low-level adapter/state design. The normal executable path is now [OperationService and its dedicated worker](local_control_plane_implementation.md). Use [development status](development_status.md) for current completion and [P0 contracts](p0_execution_20260912.md) for reviewed file apply. Adapter marker recovery and writer leases below must not be confused with operation claims and the file-plan journal; logical project/session tables do not establish normal operation linkage or real external-session continuation.

2026-09-12 follow-up: [P0 execution contracts and verification](p0_execution_20260912.md) supersede earlier callback-only execution, general-file write-hold and legacy mirroring statements for normal terminal/Discord operations. Retain historical verification and remaining delivery/session/platform limitations; source changes are not deployment.


> Historical baseline (2026-09-10): [CORE-STAB-01](core_stabilization_20260910.md) records the earlier schema-v3 design. This feature stage uses schema v5 with atomic reviewed-apply admission and scoped workflow/control indexes; durable conversation/work/Wiki memory is a separate follow-up. The implementation guide and development status supersede older phase descriptions below; retained adapter contracts are not normal command intake.

## Scope

Current normal work uses one local operation worker path. The adapter/remote-host model below is retained design and compatibility code, not proof of remote-worker integration. New execution paths must preserve durable intake, authenticated scope, claim and approval boundaries. Public access, credential synchronization and unattended writes are outside this contract.

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

`codex_sessions` is logical project/session metadata. Durable conversational recall remains a separate follow-up, distinct from hidden provider history. The registry does not prove ownership or resume/deletion of a provider conversation; such integration needs its own verified CLI and recovery contract.

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

The retained compatibility adapters provide runtime inventory, persisted-handle observation/cancellation and recovery evidence. Managed subprocess and tmux helpers remain for compatibility recovery and its isolated tests. Codex/Antigravity probes remain available. The scoped `start_command` and Codex/Antigravity request builders are retained as low-level design primitives with isolated tests. No worker, connector or API route uses them for normal intake. They do not supply an authenticated intake boundary, provider readiness or normal file mutation authority.

The command approval contract binds task, actor, expiry and exact command scope, consumes one approved invocation, and uses a fenced writer lease when requested. This compatibility contract does not replace current operation claims or reviewed file plans. Further integration requires a separate reviewed design.

Orca support and the unused artifact collector remain removed. Normal requests use OperationService and the bounded model runner; file artifacts use the reviewed apply/provenance engine.

## Approval and writer lease

Normal file changes use an immutable reviewed plan, authenticated owner/hash/expiry decision and preimage validation inside reviewed_changes. Existing-file writes are not authorized by a generic provider or command approval. Execution claims fence current work, and writer leases remain available to reconcile recorded legacy executions. Cancellation and recovery preserve uncertain effects for review.

## API security

All `/v1/` reads and mutating routes require a bearer token or `X-Nyanya-Control-Token`, including loopback connections. Host and Origin validation applies before data access. The token comes from an environment variable or an owner-only local file and is never returned by `/health`.

Remote/forwarded `/v1/` reads require the same token. Execution intake uses `POST /v1/operations` and `/v1/operations/control`; `/v1/tasks` creation is a draft.

The following routes require control authentication:

- project creation, phase updates, and phase checks;
- memory extraction and memory status updates;
- task creation, cancellation, and retry;
- execution cancellation;
- approval decisions;
- active-execution recovery reconciliation.

When no token exists, control routes return `503`. A wrong or missing token returns `401` when control authentication is configured.

All operational API clients must supply the control token in request headers. The page shell does not grant data access; the interactive unlock interface is a separate UI follow-up. Tokens must not appear in HTML, URLs or logs.

## Event updates and SSE compatibility

`GET /v1/events/stream` retains the ordered SSE API with sequence IDs and `Last-Event-ID`/`cursor` support. The current dashboard instead polls `/v1/events` every five seconds with authentication headers and refreshes operational views when new events arrive. Do not put a token in an EventSource URL.

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

Recovery sequence for a selected consistent snapshot under an authorized recovery task. After newer work, do not restore an old whole DB: preserve current rows, approvals, delivery state and effect journals during selected-file rollback. Previous-code schema readability is not a safe rollback guarantee.

The sequence below concerns low-level adapter recovery. For normal operations, inspect `recovery` and `why`; explicitly `resume` safe requests or use `reconcile`/`resolve` for file plans. The legacy recovery endpoint is not a replacement for file-plan reconciliation and does not authorize replay.

1. stop the Discord bridge, dashboard, and memory worker;
2. preserve current logs and create a last-chance backup;
3. verify the selected backup with `PRAGMA integrity_check`;
4. restore with `NYANYA_RESTORE_CONFIRM=YES`;
5. start dashboard and verify `/health` plus schema version;
6. start memory worker and bridge;
7. call authenticated `/v1/recovery/reconcile`;
8. keep remote writes disabled until active executions and writer leases reconcile.

## Remote boundary

An approved private proxy may forward to loopback with exact Host/Origin allowlists and application authentication. See [private dashboard access](external_dashboard_access.md). Network reachability grants no task/workspace authority or credential synchronization. Remote-worker coordination remains a future phase.

The future remote worker must register host identity, capabilities, heartbeat, task ownership, leases, and recovery evidence in this ledger. It is a separate phase from the current local/Discord implementation.
