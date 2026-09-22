# Local Control Plane Implementation

Reviewed 2026-09-21 against source commit `bb8774b`. The four source publication
batches are integrated into main. P0 source behavior is implemented; live
acceptance and delivery/context integration remain separate completion criteria.
See [development status](development_status.md) and [P0 contracts](p0_execution_20260912.md).

## Authoritative normal flow

```text
terminal / Discord / authenticated operations API
  -> OperationService.submit()
  -> SQLite task + validated OperationSpec
  -> dedicated operation_worker + atomic claim + bounded thread pool
  -> Flash assessment -> selected model -> summary / immutable file plan
  -> exclusive new-file creation OR exact approval -> reviewed apply
  -> transactionally saved result / execution / task / events
  -> connector result watcher (delivery is not yet a durable outbox)
```

`DurableTaskService` and `ExecutionCoordinator` remain compatibility/low-level
components. They are not the normal model-request orchestration path.
The worker is an on-demand child supervised by the submitting controller;
it is not a standalone LaunchAgent or a worker on another host.

## SQLite model

| Record | Role |
|---|---|
| `agent_tasks`, `executions`, `execution_events` | Intent, attempts, persisted result/status and events |
| `task_operations`, `operation_workers` | Serialized specification, eligibility, generation and heartbeat |
| File plans and apply journal | Immutable file proposal and before/after mutation evidence |
| `approvals`, `writer_leases` | Scoped decisions and compatibility adapter coordination |
| `execution_projects`, `codex_sessions` | Logical project/session metadata; not external conversation resume |
| `agent_requests`, legacy project/memory tables | Connector envelopes and compatibility readers |

Schema v4 adds the operation/worker/file-plan structures and request read model.
Normal operation status/result/events and claim release commit together. Legacy
requests import once rather than continuously overwriting the execution ledger.
Memory/project storage still needs a separate migration.

## Interface responsibilities

- Terminal prompt/REPL and normal Discord requests use OperationService.
- Discord `codex` maps to the Luna execution profile; Flash assessment still
  happens first. An explicit profile does not grant file mutation authority.
- `POST /v1/operations` executes a validated request. `POST /v1/operations/control`
  handles operation commands. `/v1/tasks` creation remains a draft-management API.
- Remote/forwarded `/v1/` reads and all mutating control APIs require the control
  token. The browser polls events with an authorization header every five seconds.
- File uploads retain a compatibility callback path. Stored callback records do
  not make delivery restart-resumable.

## Implemented safety contracts

- Registered owner workspace at intake and execution; bounded disposable snapshot.
- Data-only versioned OperationSpec, atomic claims, renewable lease, stale result
  rejection and explicit resume limited to three total attempts.
- Default two concurrent operations, configurable from one to four. Apply work
  serializes within a workspace; controllers must use consistent concurrency limits.
- Existing-file edits/deletes require the exact reviewed plan hash, same owner,
  valid approval and unchanged file preimage. New files use exclusive creation.
- Applying work checks current worker/claim ownership before file mutations.
  Interrupted or ambiguous effects remain held for `reconcile` and `resolve`.
- Worker/parent shutdown uses bounded termination and records interruption as
  blocked, not a user cancellation. Detached descendant termination is unproven.

## Remaining integration work

1. Persist connector destinations, deduplication keys, delivery attempts and
   receipts. Current watchers cannot deliver an undelivered result after restart.
2. Carry explicit owner/project/session context into operations. The worker
   currently uses the prompt and bounded file snapshot, without implicit legacy
   conversation history or approved memory injection. The terminal REPL explicitly
   embeds bounded in-process history; Discord `reset`/`save` operate on legacy context.
3. Use request-relevant snapshot selection. A capped directory walk can omit a
   requested file; the snapshot is not a complete repository or a secret detector.
4. Verify real external Codex session continuation; logical session rows alone
   do not provide it. Complete memory/project projections and compatibility migration.
5. Implement bounded request decomposition/DAG dependencies if later required.
   Independent job concurrency and recorded model routing are already present.
6. Run live Discord/file approval/recovery acceptance and supported-platform
   installation drills. Mock subprocess and SQLite tests do not replace them.

External dashboard hosting/access, additional hosts and resource scheduling are
deferred. Existing generic adapters must not be described as verified integration
of every runtime into the normal request path.

## Verification and rollback

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q tests
.venv/bin/ruff check src/nyanya_agent tests
npm run typecheck --if-present
node --check src/nyanya_agent/dashboard_static/app.js
./packaging/release/verify_release.sh
```

Target `tests/` explicitly so ignored local verification checkouts do not enter
test collection. Use isolated test state; never point fixtures at live databases.
Before a separately authorized upgrade, stop old writers, make a consistent SQLite
backup and verify integrity. Restore matching code and pre-upgrade state together;
do not run old code against a migrated database. No service or DB change is required
for this documentation review.
