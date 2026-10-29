# Local Control Plane Implementation

Current source review: 2026-10-12. [Development status](development_status.md) distinguishes implementation, tests, installation and live acceptance. Version `0.3.0` alone does not identify a dirty candidate.

## Authoritative normal flow

```text
terminal / Discord / authenticated operations API
  -> OperationService.submit()
  -> SQLite task + OperationSpec + conversation relation
  -> operation_worker + atomic claim + bounded thread pool
  -> plan without originals -> exact read-scope approval -> bounded draft copies
  -> screened conversation -> Flash assessment
  -> selected result model + scoped work/Wiki -> reply / immutable plan
  -> feedback -> latest immutable candidate -> exact approval -> reviewed apply
  -> fenced result / task / attempt / event / successful-memory commit
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
| `conversation_sessions`, `conversation_turns` | Scope/reset/order relations to existing rows; additive v7 |
| `operation_drafts` | Approved input paths/copies, conversation generation, current immutable plan and revision; additive v10 |
| `task_work_records` | Successful screened excerpts/provenance; additive v8 |
| `wiki_entries` | Topic/source/revision/conflict/review/forget; additive v9 |
| `execution_projects`, `codex_sessions` | Logical metadata, not CLI session ownership |
| `agent_requests`, legacy project/memory tables | Envelopes and compatibility readers/candidates |

V4 established operations/plans, v5/v6 added indexes, v7–v9 added memory relations; v10 adds bounded draft working copies. Original rows remain without copying full transcripts. Normal result/state/events and claim release commit together. Legacy envelope statistics are not complete all-ingress statistics.

## Interface responsibilities

- Terminal submits only its current prompt with a separate conversation key. Reset/save use the common ledger implementation.
- Discord binds owner/channel/thread/workspace. Necessary questions complete successfully.
- Discord `codex` selects Luna after Flash assessment; profile selection grants no writes.
- `POST /v1/operations` executes validated requests; `POST /v1/operations/control` handles controls. `/v1/tasks` creation remains a draft API.
- All `/v1/` reads/mutations require a token, including loopback. Host/Origin checks precede access; polling uses headers and the token stays in page memory.
- Upload callbacks/watchers are best effort, without restart-safe delivery.
- Wiki/work records reuse successful outcomes. Screened legacy candidates remain separate from normal provider context.

## Source safety contracts

- Recheck owner/workspace at intake/execution. Explicit safe paths precede bounded discovery; private instructions/runtime/dependencies/links/detected secrets are excluded.
- Data-only specs, atomic claims, renewable leases and stale-result rejection hold interrupted work. Explicit resume creates a bounded new attempt.
- Default two operations, configurable one to four. Same-generation turns stay ordered; apply excludes workspace conflicts and uses a POSIX lock.
- Edits/deletes require same owner, exact plan/hash, valid expiry and unchanged preimage. Repeat approval reuses its child; conflicting children stay held.
- Completion calls `work_memory.complete_conn` / `wiki_store.capture_conn` in the fenced transaction. Invalid optional notes do not fail a valid reply.
- Recall/review rechecks owner/channel/workspace/project/reset and source evidence. Current-only suppresses recall; no-store also excludes later recall/export; forget clears derived text, retaining workflow evidence.
- Output/final-file reads and termination are bounded. Uncertain termination is not successful cancellation; detached descendant termination remains unproven.

See [security](security_and_reliability.md), [conversation controls](operations_guide.md#ongoing-discord-conversations) and [Wiki](llm_wiki.md).

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

Use the checkout and isolated test state. Before authorized deployment, quiesce writers, take a consistent SQLite backup, verify integrity and compare workflow rows. Preserve newer rows during selected-file rollback. Older code reading v9 is not safe rollback proof: it may regenerate forgotten/opted-out summaries from retained evidence. Keep current provenance/no-store/forget/conversation guards. Never restore an old whole DB over later work.

Common docs are edited in development and mirrored to operations. Their refresh does not imply code deployment/live acceptance.

Current file-work contracts and platform limits are described in [reviewed drafts](reviewed_drafts.md).
