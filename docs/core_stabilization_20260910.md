# CORE-STAB-01 — Structural Stabilization and Full Source Review

This is a historical design/verification record. [Development status](development_status.md) takes precedence for the current installation, conversation, Wiki and completed scope.

2026-09-12 follow-up: [P0 execution contracts and verification](p0_execution_20260912.md) supersede earlier callback-only execution, general-file write-hold and legacy mirroring statements for normal terminal/Discord operations. Retain historical verification and remaining delivery/session/platform limitations; source changes are not deployment.

Written 2026-09-10. Status: local implementation, verification and follow-up handoff; not a stable release.

## Objective and scope

Prioritize a Local Control Plane that processes a single operator's Discord requests inside registered workspaces. Python owns execution, policy, storage, connectors and FastAPI; TypeScript owns installation, configuration, diagnostics and service CLI. Retain SQLite as the ledger on a single control host. Package declarations require Python 3.11+ and Node 18+, with discord.py, FastAPI/Pydantic and TypeScript as optional or build dependencies. Declared minimum versions are separate from verified support on every platform.

This session combined analysis, implementation and testing. No separate model session or model switch occurred. Baseline commit: 52a1bb5; branch: main. Numerous modified/untracked implementation and documentation files existed at the start and were preserved. These changes were also uncommitted. Remote source equality and deployment state were not checked. Live DB, credentials and service configuration were unchanged; no service restart, publication or real model work occurred.

The operator's intended first stable version:

- Analyze Discord requests, select agy/Codex and models, and distribute work across agents when needed.
- Create task-type/date folders inside each registered owner's workspace.
- Allow new files; present targets, reasons and direction for existing-file modification/deletion and request feedback.
- Retain interrupted tasks and report them after recovery; never replay without the owner's decision.
- Prioritize single-operator usability over multi-user SaaS.

These are product goals, not guarantees that this change implemented the entire workflow.

## Review method and keep/defer decisions

Inventoried public source and reviewed Python syntax/interfaces, TypeScript entry points/commands, generated JavaScript, shell/PowerShell install/uninstall paths, static UI, configuration examples, prompts, CI and tests. Traced queue, approval, execution, paths, storage, backup and distribution boundaries in implementation/tests. This is not proof of all live behavior or an independent security audit of every line. Private configuration/data and installed-model behavior were excluded from the review input.

| Area | Decision | Changes or follow-up conditions |
|---|---|---|
| core, bridge policy/runtime/store, Discord | Keep and focus improvements | Typed outcomes, task boundaries, held writes, recovery notices and result queries |
| execution store, task service, adapters, coordinator | Keep and focus improvements | Atomic claims/results, heartbeats, stale completion rejection; execution-path unification next |
| dashboard API/store/static | Keep existing behavior; defer expansion | Block nonfunctional retry, distinguish cancellation; authenticated remote reads and ledger read-model migration needed |
| memory worker/store/prompts | Keep basics; defer expansion | Owner-scoped search and removal of automatic host injection; project isolation and retention/deletion policy needed |
| TypeScript CLI/runtime, dist, bin | Keep | dist is generated; bin provides compatible entry points; strengthen DB backup and source-distribution safety |
| manager, shell, launchd | Keep; cleanup planned | Preserve service controls; unify lifecycle ownership and separate Codex controls |
| Telegram | Preserve compatibility; defer features | Separate approval/delivery/restart acceptance after Discord |
| Orca adapter | Outside product scope; removal backlog | Remove after reference/test/config compatibility review; no new dependent features |
| project/session, Agent Office UI | Preserve basic views | Do not describe external-session resume, DAG or resource scheduling as implemented |
| local LLM, OAuth/API, agy/Codex routing | Preserve connection foundations | Explicit capability/model profiles and measured selection later |
| PowerShell/Homebrew/distribution CI | Static review; qualification deferred | Real Windows install/uninstall, minimum versions and clean-install matrix needed |
| remote host, new connectors, automatic npm publication | Defer | Independent work after local recovery/approval/delivery evidence |

## Implemented contracts

1. Schema v3 adds task_claims/task_results without altering v1/v2 definitions. One SQLite transaction claims a task, creates an execution, sets current execution and records events. Check worker ID/expiry and update heartbeats. An unreleased same-owner claim prevents duplicate execution. Expired claims are not handed over automatically. Writer leases and task ownership are separate.
2. Select queued work from all incomplete rows rather than only the latest 500 history entries. Hold saved tasks lacking a runner in the current process; do not restore/replay them automatically. This is not an independent worker: runners/responders remain in process memory.
3. Return success, failure, timeout, cancellation, awaiting approval and blocked states as TaskOutcome, not inferred from response prefixes. Commit status/result together and reject completion from stale executions/expired workers. Distinguish cancellation requests from confirmed termination.
4. Save results before sending. Record delivery separately; retain error types rather than transfer-error text. Discord `result` followed by a task ID retrieves saved results in owner scope. Durable outbox with receipts/artifacts and automatic result redelivery are still absent.
5. `recovery` and 60-second checks after connection report old work. Check allowed destinations and registered workspaces. Notices can be delayed until claim expiry/a later check. Successful-notice state lives in memory, so restarting can repeat notices. Legacy rows without destination linkage require local ledger review.
6. An approval word is not authority. Direct write requests remain held for review; Codex queries enforce read-only. A feedback.review approval records a hold decision, not CLI write permission. A separate coordinator checks actor/task/command/cwd/environment/time limit/resource hash/expiry and consumes approval once. Per-file diff/hash review and application are not yet implemented in this historical stage. Natural-language risk checks and an agy sandbox do not guarantee per-file write prohibition for arbitrary agents.
7. Remove implicit HOME access; unregistered bridge users cannot run. Scope Discord file input/output to the owner's workspace. Exclusively create attachments in task-type/date/unique-ID folders to avoid overwrites. Mediation of every general-model artifact through this path remains future work.
8. Remove implicit global memory sharing and automatic path/process-list injection into provider prompts. Preserve existing global memory rows. Project isolation and privacy retention remain incomplete at this stage.
9. TypeScript state backup uses SQLite's backup API, includes committed WAL content and checks integrity. Reject symlinks/special files, backups inside their own source directories and overwriting existing destinations. This is not an atomic snapshot of all files; failed backup directories can remain.
10. Install source by copying only public package-manifest files. Reject runtime data, secrets and external symlinks. Strengthen shell-launcher quoting and destination boundaries. Separate historical shell backup/restore paths and Windows qualification remain follow-up work.

## Remaining structural work and acceptance criteria

| Priority / ID | Next work | Completion criterion |
|---|---|---|
| P0 / EXEC-02 | Serializable OperationSpec, one application path, independent worker | Same policy for every ingress; tasks/attempts/heartbeats/cancellation; no automatic duplicate effects after crashes |
| P0 / APPLY-01 | Separate creation from changes; per-file planning/approval/application | Existing-file hashes, exclusive creation, symlink rechecks, approval actor/scope/revision/expiry/revocation; reapprove altered plans |
| P0 / RECOVERY-02 | Held/cancel/resume decisions and external-effect reconciliation | Never finish cancellation without termination evidence; resolve unreleased claims with audit events |
| P0 / LEDGER-02 | Remove legacy writes and cyclic store dependencies | Preserve task/event/project/memory references in upgrade fixtures; ledger-only writes and backup restoration |
| P1 / DELIVERY-01 | Inbox deduplication, durable destinations/outbox/receipts | Separate execution/delivery during duplicate intake, crash after send, reconnect and attachment failure |
| P1 / ROUTING-01 | Explicit agy/Codex model profiles, planner and bounded fan-out | Separate task type, complexity, importance, risk and budget; record selection reasons; merge plans into one approval/application path |
| P1 / SESSION-01 | Distinguish Project/Workspace/NyaNya Session/external Session | Registration/selection/query and actual CLI persistence proof; logical sessions are not external resume |
| P1 / OPS-02 | Unified service ownership, configuration errors, shutdown/preflight | Preserve invalid/corrupt config, independent Codex lifecycle, classify actual launch-context permission failures |
| P1 / MEMORY-02 | Project isolation and data lifetime | Explicit provider exposure and log/result/attachment/backup retention/deletion/audit-conflict policy |
| P2 / DIST-02 | Distribution qualification | Python/Node minima; macOS/Linux/Windows install/update/uninstall; disk-full/permissions/restore; dependency audit |
| P2 / UI-02 | Dashboard simplification and authenticated remote reads | Expose working controls only; test authentication/ownership for private remote reads |
| P2 / HOST-01 | Remote hosts and resource optimization | Authenticated worker API after local guarantees; no shared SQLite files or credential synchronization |

Keep multi-agent distribution as a product goal. Suggested first implementation: bounded parallel analysis/new artifacts followed by one merged change plan, approval and application. Concrete budget/model priorities were not yet decided. New connectors, Orca, public dashboards, multi-tenancy and unlimited autonomous writes are not in the current development scope.

## Verification and limits

Regression tests isolate NYANYA settings through tests/conftest.py and do not load real .env/DB. Coverage includes cross-process competing claims, 600-row history, expired leases, stale completion, restart holds, typed outcomes, preserved results after uncertain delivery, approval task/actor/scope/expiry/reuse, traversal/symlinks, memory ownership, WAL backup/corrupt DB/overwrite rejection, public-file installation and secret/external-link rejection. Real subprocess/tmux tests and bash clean installation in temporary directories (`--skip-deps`) are included. Installation tests exclude package downloads, authentication, service registration and real model execution.

Recorded final checks:

- Python regression suite: 111 passed (5.29 seconds).
- Ruff: All checks passed; TypeScript build/typecheck passed.
- Dashboard JavaScript, all dist/bin JavaScript, shell syntax and Python AST checks passed.
- Release verification: npm pack dry-run, tracked/untracked public-worktree privacy scan and version agreement passed.
- Changed Markdown relative links and `git diff --check` passed.
- An intermediate regression exposed nondeterministic ordering of same-second tasks by random IDs; insertion-order tie-breaking and a reproducer were added.
- Dependency audit, real Discord/models, Windows and minimum-version matrix were not run.

Passing unit/integration tests is not live Discord evidence. Real Discord intake → model → task-specific folder → change-plan feedback → interruption → reconnect notices requires separate operator acceptance. OS popup/permission readiness OPS-PERM-01 is also separate; security settings were not changed.

## Upgrade, restore and next-role handoff

Execution automatically upgrades schema to v3. Before deployment, stop services and obtain a verified backup of the correct state DB. No real DB migration occurred in this task. Rollback by letting old code write v3 is unsupported. Preserve newer state, then restore matching pre-upgrade state/code and check integrity/references. Never delete or replay existing queued/running records arbitrarily.

The next role should start from this CORE-STAB-01 handoff and the latest worktree to specify EXEC-02/APPLY-01. First define operator reconciliation of unreleased claims blocking the owner queue and the threat/acceptance model for per-file approved execution. No additional operator action is currently required. Live deployment/model acceptance remain separate authorized execution scope.


## Reviewed file inventory

This inventory is the historical review scope of public source, operating/distribution scripts, configuration examples and tests. Regenerate/check dist JavaScript through the TypeScript build. Private runtime files are excluded.

### src (30)

- src/nyanya_agent/__init__.py
- src/nyanya_agent/adapter_runner.py
- src/nyanya_agent/approval_contract.py
- src/nyanya_agent/bridge_common.py
- src/nyanya_agent/bridge_constants.py
- src/nyanya_agent/bridge_policy.py
- src/nyanya_agent/bridge_runtime.py
- src/nyanya_agent/bridge_store.py
- src/nyanya_agent/codex_cli.py
- src/nyanya_agent/core.py
- src/nyanya_agent/dashboard_api.py
- src/nyanya_agent/dashboard_static/app.js
- src/nyanya_agent/dashboard_static/index.html
- src/nyanya_agent/dashboard_static/styles.css
- src/nyanya_agent/dashboard_store.py
- src/nyanya_agent/discord_bridge.py
- src/nyanya_agent/distribution_copy.py
- src/nyanya_agent/execution_adapters.py
- src/nyanya_agent/execution_runtime.py
- src/nyanya_agent/execution_store.py
- src/nyanya_agent/manager.py
- src/nyanya_agent/memory_worker.py
- src/nyanya_agent/policy_documents.py
- src/nyanya_agent/runtime_paths.py
- src/nyanya_agent/state_backup.py
- src/nyanya_agent/task_outcomes.py
- src/nyanya_agent/task_service.py
- src/nyanya_agent/telegram_bridge.py
- src/nyanya_agent/work_queue.py
- src/nyanya_agent/workspace_paths.py

### cli (18)

- cli/src/bin/nyanya-agent.ts
- cli/src/bin/nyanya-dashboard.ts
- cli/src/bin/nyanya-discord.ts
- cli/src/bin/nyanya-memory-worker.ts
- cli/src/bin/nyanya-telegram.ts
- cli/src/bin/nyanya.ts
- cli/src/bin/nyanyactl.ts
- cli/src/bin/python-module.ts
- cli/src/commands/config.ts
- cli/src/commands/doctor.ts
- cli/src/commands/service.ts
- cli/src/commands/setup.ts
- cli/src/commands/state.ts
- cli/src/runtime/env-file.ts
- cli/src/runtime/process.ts
- cli/src/runtime/project.ts
- cli/src/runtime/prompt.ts
- cli/src/runtime/python.ts

### bin (7)

- bin/nyanya-agent.js
- bin/nyanya-dashboard.js
- bin/nyanya-discord.js
- bin/nyanya-memory-worker.js
- bin/nyanya-telegram.js
- bin/nyanya.js
- bin/nyanyactl.js

### scripts (14)

- scripts/backup_state.sh
- scripts/check_backend.sh
- scripts/install_discord_launch_agent.sh
- scripts/mark_dist_executable.js
- scripts/nyanya_ctl.sh
- scripts/restore_state.sh
- scripts/run_dashboard.sh
- scripts/run_discord_bridge.sh
- scripts/run_memory_worker.sh
- scripts/run_nyanya.sh
- scripts/run_telegram_bridge.sh
- scripts/runtime_env.sh
- scripts/status_launch_agents.sh
- scripts/uninstall_discord_launch_agent.sh

### packaging (13)

- packaging/README.md
- packaging/homebrew/Formula/nyanya-agent.rb.template
- packaging/install/install.ps1
- packaging/install/install.sh
- packaging/install/uninstall.ps1
- packaging/install/uninstall.sh
- packaging/launchd/com.hcs.nyanya.agent.plist.template
- packaging/launchd/com.hcs.nyanya.dashboard.plist.template
- packaging/launchd/com.hcs.nyanya.memory-worker.plist.template
- packaging/release/generate_checksums.sh
- packaging/release/package-allowlist.txt
- packaging/release/package-denylist.txt
- packaging/release/verify_release.sh

### config (2)

- config/nyanya.json
- config/user_workspaces.example.json

### prompts (5)

- prompts/agent_memory.md
- prompts/policy.md
- prompts/policy_governance.md
- prompts/policy_technical.md
- prompts/system.md

### tests (22)

- tests/conftest.py
- tests/test_agent_memory.py
- tests/test_bridge_dashboard_recording.py
- tests/test_bridge_policy.py
- tests/test_cli_distribution.py
- tests/test_cli_safety_profiles.py
- tests/test_codex_cli_resolution.py
- tests/test_dashboard_execution_api.py
- tests/test_dashboard_store.py
- tests/test_distribution_safety.py
- tests/test_execution_adapters.py
- tests/test_execution_runtime.py
- tests/test_execution_store.py
- tests/test_manager_launchd.py
- tests/test_memory_store.py
- tests/test_memory_worker.py
- tests/test_policy_documents.py
- tests/test_runtime_paths.py
- tests/test_safety_boundaries.py
- tests/test_task_service.py
- tests/test_terminal_durable_path.py
- tests/test_work_queue.py

### .github (1)

- .github/workflows/ci.yml

## Historical worktree handoff inventory

This historical list includes changes present before the session and is not a diff of this task alone. Pass untracked files to the next role too. No remote push or commit occurred.

- README.KO.md (M)
- README.md (M)
- cli/src/commands/state.ts (M)
- cli/src/runtime/process.ts (M)
- dist/commands/state.js (M)
- dist/runtime/process.js (M)
- docs/README.md (M)
- docs/architecture_and_roadmap.md (M)
- docs/execution_control_plane.md (M)
- docs/installation_and_distribution.md (M)
- docs/operations_guide.md (M)
- package.json (M)
- packaging/install/install.ps1 (M)
- packaging/install/install.sh (M)
- packaging/release/verify_release.sh (M)
- prompts/agent_memory.md (M)
- prompts/system.md (M)
- src/nyanya_agent/bridge_policy.py (M)
- src/nyanya_agent/bridge_runtime.py (M)
- src/nyanya_agent/bridge_store.py (M)
- src/nyanya_agent/core.py (M)
- src/nyanya_agent/dashboard_api.py (M)
- src/nyanya_agent/dashboard_store.py (M)
- src/nyanya_agent/discord_bridge.py (M)
- src/nyanya_agent/execution_adapters.py (M)
- src/nyanya_agent/execution_runtime.py (M)
- src/nyanya_agent/execution_store.py (M)
- src/nyanya_agent/manager.py (M)
- src/nyanya_agent/memory_worker.py (M)
- tests/test_agent_memory.py (M)
- tests/test_bridge_dashboard_recording.py (M)
- tests/test_bridge_policy.py (M)
- tests/test_cli_distribution.py (M)
- tests/test_cli_safety_profiles.py (M)
- tests/test_dashboard_execution_api.py (M)
- tests/test_execution_adapters.py (M)
- tests/test_execution_runtime.py (M)
- tests/test_execution_store.py (M)
- AGENTS.md (??)
- docs/architecture_diagnostic_20260826.md (??)
- docs/core_stabilization_20260910.md (??)
- docs/local_control_plane_implementation.md (??)
- docs/npm_release_resumption_guide.md (??)
- prompts/policy.md (??)
- prompts/policy_governance.md (??)
- prompts/policy_technical.md (??)
- src/nyanya_agent/approval_contract.py (??)
- src/nyanya_agent/codex_cli.py (??)
- src/nyanya_agent/distribution_copy.py (??)
- src/nyanya_agent/policy_documents.py (??)
- src/nyanya_agent/state_backup.py (??)
- src/nyanya_agent/task_outcomes.py (??)
- src/nyanya_agent/task_service.py (??)
- src/nyanya_agent/work_queue.py (??)
- src/nyanya_agent/workspace_paths.py (??)
- tests/conftest.py (??)
- tests/test_codex_cli_resolution.py (??)
- tests/test_distribution_safety.py (??)
- tests/test_policy_documents.py (??)
- tests/test_safety_boundaries.py (??)
- tests/test_task_service.py (??)
- tests/test_terminal_durable_path.py (??)
- tests/test_work_queue.py (??)
