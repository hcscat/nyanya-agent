# NyaNya Agent Architecture and Roadmap

Reviewed 2026-09-21 against source commit `bb8774b`. See
[development status](development_status.md) for the four-batch review and
[P0 contracts](p0_execution_20260912.md) for detailed execution limits.

## Product boundary

NyaNya Agent is a single-operator, local-first Python **Local Control Plane**.
Terminal and Discord are the primary request interfaces. The dashboard is a
lower-priority local monitoring and authenticated management surface.
Codex, Antigravity, tmux and model runtimes remain independent systems. Orca is
excluded from the product direction. Telegram remains compatibility code.

## Component ownership

| Component | Responsibility |
|---|---|
| Python runtime | Workspace policy, operations, file plans, model calls, memory and dashboard API |
| TypeScript CLI | Installation, configuration, diagnostics, backup and service management |
| SQLite | Authoritative operation/task/execution state, approvals, results, events and apply journal |
| OperationService | Validate intake, supervise an on-demand worker and watch saved results |
| Dedicated operation worker | Claim serialized operations and execute a bounded thread pool |
| Discord bridge | Authenticated intake, workspace ownership, commands and result/file delivery |
| Dashboard | Local FastAPI/static UI, authenticated operations API and event polling |
| Compatibility services | Upload callbacks, legacy request/project records and memory extraction |

## Normal request lifecycle

1. Resolve the registered workspace and authenticated owner.
2. Persist a validated request OperationSpec and task before model execution.
3. A dedicated worker atomically claims work; concurrency defaults to two.
4. Flash assesses importance, impact and complexity; the selected Flash/Luna/Astra
   profile returns a summary and optional file plan from a bounded snapshot.
5. Create new files exclusively in a task directory. Existing-file modification
   or deletion waits for exact owner/plan/hash/expiry-bound approval.
6. Apply with ownership, workspace and file preimage checks, a workspace lock
   and a journal. Commit task/result/event state atomically.
7. Attempt connector delivery; retain results independently of delivery success.
   Interrupted work stays held for explicit review, resume or reconciliation.

Parallelism currently means independent operations, not decomposition of one
request into collaborating agents. A failed worker is not automatically replaced
to replay old work. Detailed limits are in the P0 contract.

## Implemented baseline and boundaries

- Schema v4 and normal terminal/Discord/authenticated API operations use the
  serializable worker path. Legacy upload callbacks remain separate.
- Reviewed UTF-8 regular-file creation/modification/deletion is implemented on
  supported POSIX systems. Binary edits, directory moves/deletion and Windows
  file apply are outside the supported contract.
- Model routing records scores and selection. It is not resource-aware scheduling
  and does not establish that a configured model is available in every install.
- Dashboard updates use authenticated polling every five seconds. The SSE API
  remains available, but the current browser does not use it.
- Logical project/session tables, legacy memory extraction and owner-scoped
  retrieval helpers exist. Normal Discord operations do not inject prior
  conversation or approved memory; the terminal REPL embeds bounded in-process
  history. Durable context integration remains unfinished.
- Installation, backup/restore, packaging/privacy checks and CI exist. Automated
  checks are separate from live Discord and operational acceptance.

## Next priorities

1. Complete live Discord acceptance for a fresh result, approved file change,
   held restart recovery and independent concurrent requests.
2. DELIVERY-01: durable inbox deduplication, delivery destinations, outbox retry
   and receipts; handle send-success/receipt-write failure explicitly.
3. CONTEXT-01: explicit project/session selection, request-relevant snapshot
   selection and owner/project-scoped memory in the normal operation path.
4. Complete legacy memory/project read-model migration with upgrade/restore
   evidence before removing compatibility storage.
5. Design bounded single-request decomposition only after delivery/context
   contracts are reliable. Add resource/latency/cost scheduling when measured.

## Deferred work

External dashboard access and its server/database/hosting setup are deferred by
the operator as of 2026-09-21. The [access guide](external_dashboard_access.md)
is reference material, not a deployment instruction for the current phase.
Remote hosts, credential/host enrollment, broader connectors and npm publishing
remain separate work. Wiki and Release Notes publication also remain separate.

## Non-goals

- unrestricted autonomous writes or public unauthenticated controls;
- credential synchronization or shared SQLite files between hosts;
- open-ended bot-to-bot conversations;
- replacing independent terminal, VPN or model runtimes.
