# CORE-STAB-01 / P0 Execution, File Approval, Recovery and Ledger Implementation

This records implementation contracts and verification from 2026-09-12. See [development status](development_status.md) for subsequent main integration, CI corrections, current tests and new review items. The 150-test/uncommitted/undeployed statements below describe that historical state, not the current one.

2026-09-12. Work IDs: EXEC-02 / APPLY-01 / RECOVERY-02 / LEDGER-02. This task combined design review, implementation and testing without switching the development-session model. Operating deployment, service restart, operating DB migration and public publication were excluded.

## Objective and decisions

Preserve one owner's Discord/terminal requests and process independent requests concurrently, while existing files change only after human approval of concrete plans. Never replay interrupted requests automatically; remind the owner after other work completes and expose recorded evidence. Reimplement execution paths while retaining the product, distribution CLI, connectors, configuration, backup and compatible readers.

Parallel processing is appropriate. Serialization differs from serial execution: serializable OperationSpec stores work as data rather than a function/callback. Multiple worker threads can execute separate specifications concurrently.

```json
{
  "version": 1,
  "kind": "request",
  "prompt": "Please analyze the request",
  "workspace": "/absolute/workspace/path",
  "profile": "auto",
  "timeout_seconds": 600,
  "plan_id": ""
}
```

Specifications contain no arbitrary shell, Python objects, credentials or serialized callbacks. Supported kinds are request/apply; apply references a saved plan ID. Unsupported versions/fields/profiles do not execute. JSON reconstruction is separate from resuming a model-provider conversation. Resume after interruption is an owner-authorized **new attempt**.

## Implementation flow

```text
terminal / Discord / authenticated operations API
  → OperationService → SQLite task + OperationSpec
  → dedicated operation_worker process
  → atomic claim + bounded thread pool
  → Flash assessment → selected executor → summary / file plan
  → new-file exclusive creation OR owner approval → reviewed apply
  → atomic execution/task/result/event commit → connector delivery
```

| Work | Implementation | Important limit |
|---|---|---|
| EXEC-02 | Data specification, separate process, worker identity/heartbeat, atomic claim, concurrency, lease validation, bounded retries and typed outcomes | No arbitrary shell/browser tasks or DAG scheduler that decomposes one request |
| APPLY-01 | Immutable file plans, prior content/hash, diffs, actor/plan/hash/expiry approval, execution-time path checks, journals and workspace locks | UTF-8 regular files only; no directory deletion/move or binary editing |
| RECOVERY-02 | Interruption holds, original request/stage/evidence/attempt count, incomplete-work reminders, explicit resume and reconcile/resolve | Full delivery outbox is separate; no invented causes or automatic replay |
| LEDGER-02 | Shared DB module removes cyclic imports; schema v4; authoritative execution ledger; one-time legacy import/read view | Preserve legacy envelopes/memory/project tables for compatibility; not a completed migration of every domain |

Normal model requests no longer use the old in-process runner. Discord uploads retain the callback delivery path, which is not durable delivery. Existing dashboard `/v1/tasks` creates draft records without executable specifications and never runs them automatically. Executable intake uses authenticated `POST /v1/operations`. Dashboard UI prioritizes monitoring.

## Model policy

Source routing was updated on 2026-10-07. These are explicit requested model/effort IDs, not proof of operating installation or authenticated responses for a particular account.

| Alias | Runtime | Model ID | Effort | Selection rule |
|---|---|---|---|---|
| flash | agy | gemini-3.8-flash-medium | medium | Initial assessment for every request; lower-complexity execution |
| luna | Codex | gpt-6-luna | xhigh | Importance and impact both <4, complexity 3–4 |
| sol | Codex | gpt-6.1-sol | high | Importance or impact ≥4, or complexity 5 |
| astra | Codex | gpt-6.1-sol | high | Compatibility alias for saved older specifications; same settings as sol |

Each score is 1–5 and includes a saved reason. Malformed output, unavailable models or failed authentication hold the request. Never silently substitute a model. Explicit flash/luna/sol/astra profiles still require initial Flash assessment, with actual selection recorded in a separate event.

Automatic higher-tier selection records sol. Preserve older astra specifications/event labels, but execute the Sol model shown above, not Astra. Retain initial Flash assessment and Flash execution for importance/impact <4 with complexity 1–2. Do not use “latest model” as a permanent alias; recheck supported IDs, permissions and actual responses when updating. Reasoning effort never changes write authority. Preserve existing provider/model configuration and CLI overrides for backend `--check`, but explicitly reject those overrides in normal execution. Automatic model discovery/change and self-improvement remain deferred pending separate authorization.

Referenced model documentation: [Gemini 3.8 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash), [GPT 6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna), [GPT 6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol).

## Execution and concurrency

Default concurrency is two; `NYANYA_WORKER_CONCURRENCY` permits 1–4. Count operation claims within a DB transaction to prevent duplicate/excess claims. Ordinary analysis may run concurrently in one workspace. Apply operations do not overlap other operations in that workspace; an additional POSIX lock serializes actual writes. Controllers sharing a DB must use the same concurrency limit.

Flash assesses each request after claiming it. Score-based routing is implemented, but unassessed requests are not pre-evaluated to optimize queue ordering and running work is not preempted. Workers use priority/intake order and retain assessment scores. Decomposition DAGs, automatic reassignment, resource prediction and cost optimization are future work.

Worker heartbeats/claims expire after 30 seconds and renew during execution. Lease expiry or worker death holds work and rejects completion from the old attempt. New workers never take over old tasks automatically; independent new requests continue. Preserve task/specification/start-failure evidence where possible. Requests without registered workspaces are not admitted as executable work.

Cancellation/timeout attempts to terminate owned subprocess groups and reap parents. Termination permission errors or lack of confirmation are not reported as successful cancellation. Termination of every detached descendant needs separate live verification. Output is bounded to 4 MB per stream and CLI input to 100 KB.

## File contracts

- Recheck owner-registered workspace at admission and execution; no implicit HOME access.
- Model snapshots contain at most 80 UTF-8 files/50 KB total and traverse at most 200 directories. Exclude known private/runtime/credential paths and symlinks; copy into temporary directories. This is not DLP that detects every secret; curate the workspace content supplied to providers.
- Models return analysis or file-plan JSON only. Invoke agy in plan/sandbox and Codex read-only. Temporary snapshots and CLI options do not establish complete OS isolation.
- Put new files under `nyanya-tasks/task_kind/YYYYMMDD-HHMMSS-plan_id/`. Task kinds are analysis/code/document/data/work; default work when omitted. Use UTC and a unique ID. Do not write on existing-path collisions.
- Existing-file modification/deletion plans require snapshot hashes matching current content. Save paths, operations, reasons, before/after content and plan hashes.
- Mark truncated diffs and expose full content through plan-file. Approval is tied to exact plan ID/hash, same owner and one-hour expiry. Approval words, feedback.review rows and stronger models do not grant write permission.
- At apply time recheck registration, approval, expiry, immutable content hash and preimage hashes. Allow single-link regular files only; dir-fd/O_NOFOLLOW rejects symlink traversal. Cancelling the original task prevents application of its approved plan.
- Journal prior bytes/hashes before writing. New creation uses O_EXCL, replacement uses a fsynced temporary file, deletion unlinks only approved files. Multi-file application is not one filesystem transaction; expose partial states.
- Interrupted application remains applying/uncertain and blocks later apply in the same workspace. Reconcile observes actual files; resolve confirms the reviewed observation hash. Resolve does not rewrite or roll back files. Partial application needs a new request/plan based on current files. Resume also rejects prior requests with file effects.

An external editor can still race between checks and replacement. Operating procedure must prevent other tools editing the same files during apply. Windows no-follow apply is unsupported and remains held. Content rollback uses journals/pre-upgrade backups and separate human review.

## User commands

Use these after the existing Discord prefix, or as terminal prompts/REPL input. Dashboard controls use operator ownership. The actual sender determines a Discord actor; callers cannot substitute an arbitrary identity string.

| Command | Behavior |
|---|---|
| recovery | Summarize the owner's incomplete work |
| why <task-id> | Original request, state, recorded stages/reasons and attempt count |
| plan <plan-id> | Concrete changes and per-file diffs |
| plan-file <plan-id> <relative-path> | Complete content of that file plan |
| approve <plan-id> <plan-hash> | Approve reviewed plan and admit apply |
| revoke <plan-id> | Reject/revoke an unconsumed plan |
| resume <task-id> | Explicit new attempt of a safe request, at most three total |
| cancel <task-id> | Request individual cancellation; await termination confirmation if running |
| reconcile <plan-id> | Observe before/after/diverged file states and return a hash |
| resolve <plan-id> <observation-hash> | Confirm matching observed state; never replay files |
| result <task-id> (Discord) | Retrieve saved results, including delivery failures |

Successful answers append an incomplete-work count and up to five IDs/summaries. Exclude the current analysis and the original request just completed by apply. Include failures. If evidence cannot establish a cause, say so. These reminders coexist with reconnect notices; exactly once receipt/outbox delivery is not guaranteed.

API: send prompt/workspace/profile to `POST /v1/operations` and commands to `POST /v1/operations/control`. Intake is asynchronous and never marks work delivered without actual delivery. Remote/forwarded reads also require tokens. The dashboard sends tokens in GET/POST headers and polls every five seconds. The control-enable button checks authentication without changing recovery state. Health/static shells do not grant public execution authority.

## Ledger, migration and rollback

Schema v4 adds worker/specification/plan/journal tables and request_read_model. The database module imports neither providers nor dashboard. Remove cyclic initialization between dashboard_store/execution_store. Do not resynchronize already-imported legacy rows. Commit each new operation's state/result/event/claim release/retry eligibility in one transaction; approved apply completion and original-request completion events also share a transaction. Preserve attempt history/prior results; old attempts cannot overwrite current task state.

agent_requests remains for connector envelopes/compatible data. Read current state/results through the ledger view. Full migration of legacy memory extraction/project views, every pre-schema data form and removal of compatible tables require separate review. Keep compatible readers at least until the next deployment's upgrade/restore verification completes.

Before deployment, use SQLite backup and check integrity/foreign keys. Stop all related old processes before upgrading to v4. Do not roll back by allowing old code to keep writing the v4 DB. Restore the pre-deployment backup separately while stopped and restore matching code/state. This task migrated/backed up/restored temporary fixtures only, not the operating DB. Current rollback requirements in development status take precedence after later rollouts.

## Verification and follow-up

These results belong to this historical implementation task. The previous 111 tests refer to 2026-09-10, not the current suite. Read the test guide together with [test_p0_operations.py](../tests/test_p0_operations.py).

- Full Python suite: 150 passed; the added P0 file contains 32 functions/39 cases.
- Unit/integration coverage: specifications, scores/routing, concurrent claims, stale completion, owners/paths, approval hashes/expiry/revocation, symlinks, changed before/after hashes, deletion, partial apply, observation confirmation, retry limits, no stale-result redelivery, API authentication/admission and preserved startup failures.
- Actual OS/SQLite: cross-process competing claims, separate worker/fake CLI, forced worker death, two concurrent model threads, file journals/backups, v3→v4 upgrade/v3 backup restore, cancellation/output bounds. Forced death just after replace+fsync also exercised reconciliation with the journal still prepared.
- Real models: all three profiles returned minimal JSON from temporary directories. A real model generated a temporary note.txt plan → awaiting_approval → unchanged preimage → explicit approval → successful apply. This was not Discord-network or operating-account acceptance.

The next paragraph is the 2026-09-12 backlog. Channel/project conversation, work/Wiki memory, request-related snapshot selection and some live acceptance have since completed. DELIVERY-01, all-ingress Requests statistics and external provider-session lifecycle remain. Follow [development status](development_status.md) for current disposition. Orca is outside the product direction.

Historical priorities: DELIVERY-01 inbox/outbox/receipt/redelivery; session/project context and external-session continuation; legacy-memory sources/read-model migration; intent-based snapshot selection; multi-agent DAG decomposition of one request; resource scheduling. Telegram expansion, Orca, remote hosts, public dashboards and npm publication were not done.

Historical next acceptance: after backup in an authorized deployment, verify real Discord intake/concurrent requests/file approval/interruption notices/why/reconcile. Operating changes/deployment need their own authority. Tests do not establish operating deployment or compatibility on every OS/platform.

## Final handoff

- Branch: main; baseline: 52a1bb5. Preexisting uncommitted changes and this work remained uncommitted.
- Main new source: database, operation_schema/spec/service/store/worker, model_routing, process_runner, reviewed_changes. Common work_queue result transactions and intake were updated.
- Updated ingress/compatibility: core, bridge_store/policy, discord_bridge, telegram_bridge, dashboard_api/store/static app.js, execution_store, task_outcomes; related tests/prompts/README/AGENTS.
- Documentation: this file, docs/README.md, test_catalog.md and existing contract guides gained follow-up links.
- Checks: PYTHONPATH=src .venv/bin/python -m pytest -q — 150 passed. Ruff, npm typecheck/build and dashboard JavaScript syntax passed. Release verification passed Python/shell syntax, npm pack/public manifests, privacy/secrets and version agreement. git diff --check and Markdown links passed. Node checks verified dashboard GET/POST authorization-header merging and no token in URLs.
- Environment: repository Python venv, POSIX/macOS, Node/TypeScript and test dependencies. pytest uses temporary NYANYA_HOME/env/DB and forbids real model calls. Separate real-model smoke/synthetic-file acceptance used temporary paths.
- Not done: operating DB migration, service restart, real Discord intake/delivery, operating-user file edits, permission changes, remote-host drill, Windows acceptance, commit/push/publication.
