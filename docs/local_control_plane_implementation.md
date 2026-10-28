# Local Control Plane Implementation

Current source review: 2026-10-12. [Development status](development_status.md) distinguishes implementation, tests, installation and live acceptance. Version `0.3.0` alone does not identify a dirty candidate.

## Authoritative normal flow

```text
terminal / Discord / authenticated operations API
  -> OperationService.submit()
  -> SQLite task + OperationSpec
  -> operation_worker + atomic claim + bounded thread pool
  -> current scoped snapshot -> Flash assessment
  -> selected result model -> reply / immutable plan
  -> exclusive creation OR exact approval -> reviewed apply
  -> fenced result / task / attempt / event commit
  -> connector watcher (not a durable outbox)
```

`OperationService.handle_intent` handles lists, selected cancellation and status before model intake. `DurableTaskService` and `ExecutionCoordinator` remain low-level/compatibility components. The on-demand child worker is supervised by the submitter, not a standalone LaunchAgent or remote worker.

## SQLite model

| Record | Role |
|---|---|
| `agent_tasks`, `executions`, `task_results`, `execution_events` | Intent, attempts, outcomes, current state and evidence |
| `task_operations`, `operation_workers` | Specs, eligibility, claim generation and heartbeat |
| File plans / apply journal | Immutable proposal and before/after mutation evidence |
| `approvals`, `writer_leases` | Decisions and isolated compatibility coordination |
| `execution_projects`, `codex_sessions` | Logical metadata, not CLI session ownership |
| `agent_requests`, legacy project/memory tables | Envelopes and compatibility readers/candidates |

V4 established operations/plans; v5 adds scoped workflow/control indexes. Normal result/state/events and claim release commit together. Legacy envelope statistics are not complete all-ingress statistics.

## Interface responsibilities

- Terminal submits its current prompt; durable conversation recall/reset/export is a separate follow-up.
- Discord binds authenticated owner and channel scope for controls and exact upload confirmation.
- Discord `codex` selects Luna after Flash assessment; profile selection grants no writes.
- `POST /v1/operations` executes validated requests; `POST /v1/operations/control` handles controls. `/v1/tasks` creation remains a draft API.
- All `/v1/` reads/mutations require a token, including loopback. Host/Origin checks precede access; API clients supply token headers. The interactive unlock UI is a separate follow-up.
- Upload callbacks/watchers are best effort, without restart-safe delivery.

## Source safety contracts

- Recheck owner/workspace at intake/execution. Explicit safe paths precede bounded discovery; private instructions/runtime/dependencies/links/detected secrets are excluded.
- Data-only specs, atomic claims, renewable leases and stale-result rejection hold interrupted work. Explicit resume creates a bounded new attempt.
- Default two operations, configurable one to four. Apply excludes workspace conflicts and uses a POSIX lock.
- Edits/deletes require same owner, exact plan/hash, valid expiry and unchanged preimage. Repeat approval reuses its child; conflicting children stay held.
- Output/final-file reads and termination are bounded. Uncertain termination is not successful cancellation; detached descendant termination remains unproven.

See [security](security_and_reliability.md) and [operations](operations_guide.md).

## Remaining integration

Durable inbox/outbox/destination/receipt handling is absent. `request_read_model` begins with legacy envelopes, so all-ingress statistics need work. Telegram lacks parity for all owner/conversation/control contracts. Provider-session ownership and safe monthly reuse/deletion need separate verification.

Commands and multi-agent DAG decomposition are isolated design primitives or recommendations. Private proxy access does not implement remote workers. Additional hosts, public hosting, resource scheduling and remote DBs remain deferred.

## Verification and rollback

```bash
python3 scripts/dev.py test
python3 scripts/dev.py lint
python3 scripts/dev.py typecheck
node --check src/nyanya_agent/dashboard_static/app.js
./packaging/release/verify_release.sh
```

Use the checkout and isolated test state. Before authorized deployment, quiesce writers, take a consistent SQLite backup, verify integrity and compare workflow rows. Preserve newer rows during selected-file rollback. Never restore an old whole DB over later work.

Common docs are edited in development and mirrored to operations. Their refresh does not imply code deployment/live acceptance.
