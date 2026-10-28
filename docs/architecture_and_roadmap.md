# NyaNya Agent Architecture and Roadmap

Current source review: 2026-10-12. See [development status](development_status.md), [normal execution](local_control_plane_implementation.md) and [P0 contracts](p0_execution_20260912.md).

## Product boundary

NyaNya is a single-operator, local-first Local Control Plane. Terminal and Discord are primary interfaces; the dashboard manages projects, work, attempts and memory. Workspace/approval boundaries, durable state, conversational continuity and cited memory add value around external model CLIs.

Python owns policy, operations, providers, connectors, SQLite and FastAPI. TypeScript owns npm setup, diagnostics and service wrappers. SQLite remains the accepted database. Codex/Antigravity authentication and lifecycles are independent; a working directory is not a sandbox.

## Component ownership

| Component | Responsibility |
|---|---|
| OperationService / control_intents | Owner/workspace intake, local controls, worker supervision and result observation |
| OperationSpec / operation_store / execution_store | Data-only requests, task/attempt transactions, claims, events and recovery |
| operation_worker / model_routing | Concurrency, Flash assessment, selected model, snapshot and scoped context |
| reviewed_changes | Immutable plans, exclusive creation, owner/hash/expiry/preimage approval and journal |
| conversation_store | Original turn relations, channel/thread scope, order, reset, recall and export |
| work_memory / wiki_store | Successful evidence, topics/revisions/conflicts, bounded recall and forgetting |
| Discord / dashboard | Authenticated intake, control and work/memory inspection; best-effort delivery / five-second polling |
| CLI / manager | Install/update, separate state, configuration, diagnostics, backup and services |
| Compatibility components | Envelopes/candidates/uploads and isolated adapter/approval/lease contracts |

## Normal request lifecycle

1. Resolve owner/workspace. Task queries/cancellation use the local control path.
2. Save OperationSpec/task and bind a scoped conversation relation.
3. Atomically claim work; default concurrency two, configurable one to four. Same-generation turns execute in order.
4. Select current safe files before adding screened history. The result model may receive relevant cited work/Wiki.
5. Flash scores importance/impact/complexity. Low complexity uses Flash; low importance/impact with complexity 3–4 uses Luna XHigh; importance/impact ≥4 or complexity 5 uses Sol High. `astra` aliases Sol.
6. Return an answer/question or immutable plan. Create new files exclusively; existing edits/deletes wait for exact approval.
7. Recheck current claim/workspace/owner/preimage and journal apply. Repeated approval reuses its child.
8. Save outcome and successful memory in the fenced transaction. Delivery remains a separate fact; uncertain effects stay held.

## Implemented boundaries

- Schema v9 reuses the ledger: v7 conversation relations, v8 work records and v9 topics do not create a second transcript/backend.
- Conversation recall: eight recent plus four older lexical turns within 24 KiB after explicit reset. Wiki recall: five summaries/8 KiB within the whole input bound.
- Up to three topics use the existing result call. Summaries are historical model claims, not current verified facts or permission.
- Reset/current-only/no-store/forget have different effects; original request/result/approval/effect evidence remains preserved.
- Supported POSIX UTF-8 file changes are reviewed. Arbitrary commands/tests, binary edits and directory mutations are not normal intake capabilities.
- Monthly gzip retention prunes verified housekeeping, preserving workflow/approval/delivery evidence.
- Orca, replaced bridge paths, old launch shells and graphs are removed. Intentional low-level contracts remain isolated.
- Source tests, installed state, live acceptance and publication are separate evidence.

## Remaining and deferred work

Recorded Discord message identities already have atomic duplicate suppression. Recording-disabled mode uses a bounded process-local cache and can admit duplicates after restart, eviction or across processes. A common connector inbox, durable destinations/outbox/receipts and recovery across intake/submission or send/record crashes remain incomplete; current claims do not guarantee restart-safe or exactly-once delivery. See [delivery boundaries](security_and_reliability.md#delivery-controls-and-lifecycle). All-ingress Requests statistics and Telegram parity need integration. Provider-session ownership/resume/monthly deletion is unimplemented; hidden history cannot bypass reset/current-only.

Single-request decomposition, resource scheduling, semantic/full-channel recall, automatic model changes, self-modification/deployment and additional connectors would expand the architecture and remain recommendations. PostgreSQL/Supabase, encryption and public hosting are deferred. Approved private access uses loopback, exact Host/Origin allowlists and existing authentication; actual instance values stay private. See [remote access](external_dashboard_access.md).

GitHub Wiki/Release Notes and npm publication are separate release work. LLM Wiki is product memory, not a GitHub documentation Wiki.
