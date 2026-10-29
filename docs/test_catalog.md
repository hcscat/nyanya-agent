# Python Test Catalog

Historical inventory baseline: 2026-10-13, **55 test files, 470 test functions and 961 parameterized cases**. These are the earlier baseline's figures, not a current candidate count. Later detailed TC-001–111 and 327-case inventories retain their historical baselines. Distinguish function counts from parameterized case counts.


The release-preparation candidate adds `test_release_control_memory.py`, `test_release_profile_policy.py`, `test_release_context_upload.py` and `test_release_ingress.py` for the focused boundary corrections described in [security and reliability](security_and_reliability.md#release-candidate-boundary-corrections). The earlier isolated candidate completed **1089 tests before the current document-upload change**. That historical result does not validate the new follow-up. Use each review branch's verification results for its exact snapshot, collection and full run; do not substitute the historical count.

The document-upload follow-up adds the four test files below. They use synthetic documents/identities, temporary state and fake Discord; they do not read operating credentials or exercise real delivery, services, OCR or models. Their collected case counts belong to the exact review-branch snapshot and must not be added to historical full-suite totals.

| New test file | Intended regression scope |
|---|---|
| [test_upload_document_privacy.py](../tests/test_upload_document_privacy.py) | Strict supported text decoding, bounded text-only OOXML extraction/metadata, nine pattern kinds/counts, credential blocks and unsupported/incomplete extraction held without exposing values |
| [test_upload_approval.py](../tests/test_upload_approval.py) | Original actor/conversation/file/hash/destination binding, expiry, pending bound, one-use atomic consumption, reject/cancel and independent upload action/audit state |
| [test_upload_transfer_policy.py](../tests/test_upload_transfer_policy.py) | Secure path/descriptor boundary, upload-only folder policy, frozen bytes and identity, former 2,000,000-byte compatibility, app/SDK transfer limits and fail-closed unsupported content |
| [test_upload_discord_privacy.py](../tests/test_upload_discord_privacy.py) | Fake Discord intake-to-send/confirmation flow, destination metadata/routing, no send on invalid or stale confirmation, and uncertain delivery without automatic retry |

## Review-branch memory UI regression

[test_dashboard_memory_ui.py](../tests/test_dashboard_memory_ui.py) executes the shipped memory render/control functions with Node and a synthetic DOM. It checks empty/populated views, HTML escaping, owner/workspace/project/session payloads, review/forget actions and full-script locked-page bootstrap against the shipped HTML IDs. Its pager stub keeps the memory contract separate from the shared pagination tests. It does not establish real-browser layout, live Discord delivery or operating-service acceptance. Use the exact review branch's collection and execution results for its current count.

## Reviewed-copy workflow regression

[test_draft_workflow.py](../tests/test_draft_workflow.py) uses isolated state and synthetic models/files to check scope approval before copying, unchanged originals, iterative feedback, exact final create/modify/delete approval, wrong/stale hashes, closure/expiry/retention and native direct-access/ancestor-rename denial. Existing conversation/provider and apply tests now follow the two approval boundaries. Real provider startup and operating connector acceptance require separate results.

[test_telegram_drafts.py](../tests/test_telegram_drafts.py) exercises synthetic Telegram update-to-operation routing: bare/slash/bot-suffixed approvals, duplicate admission, read scopes, feedback/show/close, wrong actor/channel/hash, unlisted chats and help rendering. The fake sender and model make no Bot API/provider calls; this is not live Telegram acceptance.

## Current complete test files

The table in this section is the historical 2026-10-13 inventory. Its dashboard follow-up recorded **961 passed, one external Starlette/AnyIO warning**. The earlier 948/957-case results describe preceding candidates. These records and the later pre-upload 1089-test result do not validate a separated review branch. Tests used temporary state/env/DB and called neither real models nor operating services.

| File | Functions | Collected cases | Current primary checks |
|---|---:|---:|---|
| [test_agent_memory.py](../tests/test_agent_memory.py) | 3 | 3 | Compatible owner-scoped approved memory and optional baseline prompts |
| [test_apply_admission.py](../tests/test_apply_admission.py) | 4 | 5 | Repeated approval uses one child/event; thread/process competition and forced-death rollback |
| [test_artifact_manifest.py](../tests/test_artifact_manifest.py) | 10 | 10 | File/permission/provenance manifests; modification/addition/tampering/install integrity |
| [test_audit_logging.py](../tests/test_audit_logging.py) | 4 | 4 | Heartbeat deduplication, concurrent host registration, audit redaction and indexes |
| [test_bridge_dashboard_recording.py](../tests/test_bridge_dashboard_recording.py) | 4 | 4 | Asynchronous bridge task records/results/execution-status messages |
| [test_bridge_policy.py](../tests/test_bridge_policy.py) | 5 | 5 | Registered workspaces/risk classification; approval words do not grant authority |
| [test_cli_distribution.py](../tests/test_cli_distribution.py) | 6 | 6 | npm manifests/configuration validation/separate state/install boundaries |
| [test_cli_safety_profiles.py](../tests/test_cli_safety_profiles.py) | 4 | 5 | Backend URL schemes, CLI sandbox defaults and safe options |
| [test_codex_cli_resolution.py](../tests/test_codex_cli_resolution.py) | 9 | 14 | PATH/override binary discovery and authentication/OS-error classification |
| [test_context_security.py](../tests/test_context_security.py) | 33 | 94 | Current read scopes, Korean prohibitions, exact-file priority, sensitive content and child environments |
| [test_conversation_dispatch.py](../tests/test_conversation_dispatch.py) | 12 | 15 | Intake/follow-up/reset/save; scoped private export versus cancellation |
| [test_conversation_retention.py](../tests/test_conversation_retention.py) | 5 | 6 | Older lexical turns, explicit reset, sensitive/oversize exclusion and current-only terminal prompts |
| [test_conversation_state.py](../tests/test_conversation_state.py) | 18 | 20 | Transactional binding, conversation order, generation/owner isolation, late results and migration |
| [test_conversation_worker.py](../tests/test_conversation_worker.py) | 14 | 28 | Follow-up references, necessary questions, context bounds, no inherited authority and storage refusal |
| [test_dashboard_execution_api.py](../tests/test_dashboard_execution_api.py) | 4 | 4 | Authenticated task/attempt/approval controls, project/session filters and cursors; exact-attempt request/result joins, bounded excerpts, full detail and missing results |
| [test_dashboard_memory_review.py](../tests/test_dashboard_memory_review.py) | 4 | 4 | Local assets/content hashes/no-store and views after graph removal |
| [test_dashboard_pagination.py](../tests/test_dashboard_pagination.py) | 6 | 12 | Five-item pages, all menus, status-count filtering/refresh, original-only bounded request previews, escaped attempt details/late-response fencing, approval deduplication and project checks without execution |
| [test_dashboard_read_security.py](../tests/test_dashboard_read_security.py) | 10 | 17 | Unauthenticated/Host/Origin rejection, IPv6/CORS and lazy-import isolation |
| [test_dashboard_store.py](../tests/test_dashboard_store.py) | 3 | 3 | Request/usage aggregation, project phases and confirmation decisions |
| [test_dashboard_wiki.py](../tests/test_dashboard_wiki.py) | 5 | 6 | Explicit authenticated scope/review/forget, inactive-summary clearing and retained ledgers |
| [test_dashboard_work_records.py](../tests/test_dashboard_work_records.py) | 4 | 4 | Work-memory scope/authentication/Origin and restricted forgetting |
| [test_deployment_safety.py](../tests/test_deployment_safety.py) | 16 | 36 | Quiescence, held live work, ledger preservation and restore/deployment/service boundaries |
| [test_dev_environment.py](../tests/test_dev_environment.py) | 8 | 9 | Removed inherited settings, separate dev state/venv and blocked service commands |
| [test_distribution_safety.py](../tests/test_distribution_safety.py) | 3 | 3 | Public-manifest copy, private/symlink rejection and isolated installation |
| [test_execution_adapters.py](../tests/test_execution_adapters.py) | 6 | 6 | Intentional low-level subprocess/tmux handles, markers and termination |
| [test_execution_runtime.py](../tests/test_execution_runtime.py) | 4 | 4 | Low-level coordinator cancellation/handle recovery/single-use approval and leases |
| [test_execution_store.py](../tests/test_execution_store.py) | 8 | 8 | Migration/idempotence, tasks/attempts/events and fenced writer leases |
| [test_hardening_workflow.py](../tests/test_hardening_workflow.py) | 10 | 10 | Competing watchers send once; stale/ambiguous delivery and control/approval lifecycle |
| [test_log_archive.py](../tests/test_log_archive.py) | 22 | 27 | Verified monthly gzip, housekeeping-only pruning, retention/path/trigger/interruption safety |
| [test_log_maintenance.py](../tests/test_log_maintenance.py) | 8 | 8 | Unchanged dry-run/status, DB/state agreement, environment isolation and cleanup-child cancellation |
| [test_manager_launchd.py](../tests/test_manager_launchd.py) | 2 | 2 | Retry transient launchd transitions and reject nonretryable errors |
| [test_memory_store.py](../tests/test_memory_store.py) | 11 | 28 | Candidate extraction/search/review, current successful sources, no-store/forget and legacy preservation |
| [test_memory_worker.py](../tests/test_memory_worker.py) | 1 | 1 | Safe rule-based extraction from completed envelopes |
| [test_model_stdin.py](../tests/test_model_stdin.py) | 1 | 2 | Isolated stdin EOF with controller-pipe preservation |
| [test_operation_shutdown.py](../tests/test_operation_shutdown.py) | 14 | 24 | Hold claims/effects on shutdown; distinguish cancellation/completion and recover |
| [test_p0_operations.py](../tests/test_p0_operations.py) | 35 | 170 | Specifications/claims/routing/scopes/plan hashes/apply/journals/resume/worker/API |
| [test_package_followup.py](../tests/test_package_followup.py) | 7 | 11 | Trust versus registration/approval; exclude node_modules from Git/packages/scans |
| [test_policy_documents.py](../tests/test_policy_documents.py) | 1 | 1 | Common/technical/governance policy-loading contract |
| [test_provider_limits.py](../tests/test_provider_limits.py) | 11 | 20 | 4 MB during/after execution; regular/no-follow handles and growing files |
| [test_publication_privacy.py](../tests/test_publication_privacy.py) | 7 | 86 | Forbidden public-manifest/package paths and synthetic sensitive-data detection |
| [test_runtime_paths.py](../tests/test_runtime_paths.py) | 5 | 5 | OS state/environment/legacy/source paths and code/state separation |
| [test_safety_boundaries.py](../tests/test_safety_boundaries.py) | 11 | 13 | Block unregistered HOME; owner mappings/traversal/symlinks/file safety |
| [test_service_logs.py](../tests/test_service_logs.py) | 13 | 13 | Bounded log rotation, competing writers, signals/reaping, gzip replacement/corruption and retention |
| [test_task_service.py](../tests/test_task_service.py) | 2 | 2 | Compatible callback-queue persistence, owner order and running/queued cancellation |
| [test_telegram_diagnostics.py](../tests/test_telegram_diagnostics.py) | 1 | 1 | No provider URL/credential exposure from Telegram poll errors |
| [test_terminal_durable_path.py](../tests/test_terminal_durable_path.py) | 1 | 1 | Terminal single requests use the normal operation ledger |
| [test_upload_safety.py](../tests/test_upload_safety.py) | 4 | 7 | Upload path/parent replacement while waiting, symlinks and verified-inode handles |
| [test_wiki_store.py](../tests/test_wiki_store.py) | 18 | 38 | Topic/revision/provenance isolation/reset/no-store/forget and recall budget |
| [test_work_memory.py](../tests/test_work_memory.py) | 20 | 31 | Store successful evidence only; fencing/scopes/sensitivity/refusal/forgetting/ledger preservation |
| [test_work_queue.py](../tests/test_work_queue.py) | 12 | 16 | Single cross-process claim, queue/lease expiry and stale-result rejection |
| [test_worker_efficiency.py](../tests/test_worker_efficiency.py) | 2 | 2 | Index upgrade and reduced idle-poll claim/recovery writes |
| [test_workflow_dispatch.py](../tests/test_workflow_dispatch.py) | 10 | 62 | Natural-language intent/selection revisions/safety clauses/current-attempt waits/no-file scopes |
| [test_workflow_lifecycle.py](../tests/test_workflow_lifecycle.py) | 12 | 13 | Dismiss/expiry/revoke, uncertain-effect preservation and private-plan rejection |
| [test_workflow_notifications.py](../tests/test_workflow_notifications.py) | 15 | 22 | Exclude live work; held/stale notices, owners and receipt deduplication |
| [test_workspace_intake.py](../tests/test_workspace_intake.py) | 2 | 10 | No execution for missing owners/prerequisites; safe diagnostics |

Test counts are neither feature counts nor coverage percentages. Read the [current security regressions](security_and_reliability.md#regression-coverage) and [direct acceptance plan](user_acceptance_tests.md) together. Operating installation and real provider/Discord acceptance require evidence separate from automated tests.

## Reading the historical detailed inventory

The 2026-09-21 recheck also recorded 318 passed. Newly identified defects and acceptance gaps are tracked in [development status](development_status.md). Do not read test counts as feature completion.

## Earlier added regressions

The 2026-10-11 conversation-retention correction recorded **858 passed** and one external Starlette/AnyIO warning. The latest full run including Wiki/storage-refusal/forgetting fixes is the 948-case record above. Log management recorded 496 cases on 2026-10-05; model/control/context/conversation tests followed. See [regression coverage](security_and_reliability.md#regression-coverage) for security/stability scope and file roles. Check current counts with `python -m pytest --collect-only -q tests`. Korean fixtures `파일을 읽거나 수정하지 말고` and prohibitions linking read/access/write verbs block traversal before it begins; `파일을 읽지 마`, `파일을 열지 마` and `파일에 접근하지 마` exercise the same boundary. Distinguish write-only prohibitions, positive read requests and negation of a prohibition itself; negating a quoted clause must not invalidate another actual read prohibition.

The 327-case and TC inventories below refer to 2026-09-22, not the latest total.

The following 52 log-management cases use temporary DBs and synthetic logs. They do not replace operating DB cleanup, service restart or real Discord acceptance.

The following 63 conversation cases and 11 later retention/approval-admission cases use fake models/clients and temporary DBs/files. Real Discord follow-up understanding is separate acceptance.

| File | Cases | Inputs and expected results |
|---|---:|---|
| [test_apply_admission.py](../tests/test_apply_admission.py) | 5 | Concurrent thread/process repeat approvals → one child/event; post-completion approval → existing task; forced death/worker failure during admission → rollback; legacy duplicates → preserved evidence and hold |
| [test_conversation_retention.py](../tests/test_conversation_retention.py) | 6 | Search conversations 100 days old/beyond the latest 80; exclude sensitive/oversized turns; isolate owner/channel/reset; find old idle generations; terminal current prompt/separate context/private save/reset |
| [test_conversation_state.py](../tests/test_conversation_state.py) | 20 | Duplicate intake, owner/channel/workspace separation, same-context order, earlier retries, idle retention/explicit reset, late results/migration → isolation/order/fencing; distinguish applied state from historical approval-wait answers |
| [test_conversation_worker.py](../tests/test_conversation_worker.py) | 28 | Prior-answer references, necessary questions/answers, invalid questions, sensitive/oversize history, current read prohibitions and full-file limits → successful questions, bounded context and no inherited approval/model/file authority |
| [test_conversation_dispatch.py](../tests/test_conversation_dispatch.py) | 15 | Brief acknowledgement/conversation binding/reset/save/export links and failed/completed/running cancellation → state-correct answers, private export and preserved task/uncertain history |

Fifteen added background-notice regressions are in [test_workflow_notifications.py](../tests/test_workflow_notifications.py): fresh queued/running/cancelling work and other completions produce no recovery notice for live work; expired claims/dead workers/lost/held work/approval waits/exhausted attempts/uncertain sends retain necessary notices. Owners/exclusions/receipts preserve isolation and deduplication; state decisions and displayed items use the same read snapshot. Current total: seven earlier plus fifteen added, or 22.

[test_context_security.py](../tests/test_context_security.py) gained 32 exact-path-priority cases and 17 linked/short Korean-prohibition cases, bringing it to 94. Exact files beyond traversal limits/after multiple directories, Korean particles and absolute/relative paths retrieve full originals; private/outside/parent paths, linked parents, sensitive/oversized/abnormal files, read prohibitions and unsupported POSIX features transfer nothing. Scoped directories, cumulative traversal limits and ordinary-language filenames retain existing bounds. All use synthetic files/temporary paths.

| File | Cases | Inputs and expected results |
|---|---:|---|
| [test_audit_logging.py](../tests/test_audit_logging.py) | 4 | Repeated/concurrent heartbeat → audit initial registration/changes only; memory search/edit → exclude original text; audit reads → indexes |
| [test_log_archive.py](../tests/test_log_archive.py) | 27 | Month boundaries/retention/changed rows/corrupt gzip/paths/triggers/interruption → bounded deletion of verified housekeeping preimages only; retain work evidence |
| [test_service_logs.py](../tests/test_service_logs.py) | 13 | Size/date rotation, floods/exit/duplicate writers/corruption/replacement/symlinks → bounds/interruption handling and preserved originals or recovery evidence |
| [test_log_maintenance.py](../tests/test_log_maintenance.py) | 8 | Empty state/default dry-run/mixed DB paths/inherited CLI secrets/dashboard status → unchanged reads, blocked dangerous paths and stripped credentials |

## Meaning of the counts

The directory is `tests`. This historical inventory has 29 test files, 186 test functions and 327 parameterized pytest cases; including conftest.py gives 30 Python files. Development isolation added eight functions/nine cases on 2026-09-22. The 2026-09-12 baseline of 22 files/132 functions/150 cases gained shutdown 14 functions/24 cases, deployment safety 16/36, packaging 7/11 and stdin isolation 1/2. By 2026-09-13 verification recorded **311 passed and one upstream Starlette deprecation warning**. Seven node_modules Git-ignore/forced-add/package-exclusion cases followed on 2026-09-17. Historical total: 150 + shutdown 24 + deployment 36 + packaging 11 + stdin 2 + intake 10 + publication boundaries 85 + development isolation 9 = 327. The earlier 111-case baseline is 2026-09-10; P0 added 32 functions/39 cases. Some prior cases changed from callback/legacy synchronization to worker/ledger contracts.

Case counts are not product features or coverage percentages. Real models were checked outside pytest in separate temporary environments; see [P0 verification](p0_execution_20260912.md). Preserve TC-001–111 identifiers and list new P0 inputs in a separate table.

## Execution types and environment

- Temporary DB/files: actual SQLite/filesystems on pytest temporary paths rather than operating data.
- Fake responses: monkeypatch replaces external calls with fixed responses/errors to reproduce success and failure.
- Real subprocesses: test Python/shell/Node/tmux processes, distinct from real Codex/agy model calls.
- In-process API calls: FastAPI TestClient sends requests inside the app, not to the internet or a live server port.
- Assertions: code checks expected outcomes; a failed condition fails its case.

[conftest.py](../tests/conftest.py) provides common setup. On pytest start it saves/removes NYANYA variables, sets temporary state, a nonexistent env path, temporary DB and test workspace, and disables default memory search. On exit it restores environment and cleans shared temporary state. Individual tests override needed settings. This reduces operating-state mixing; it is not an OS sandbox or isolation of every environment variable.

## Historical per-file summary — 2026-09-22

| File | Functions | Cases | Primary coverage |
|---|---:|---:|---|
| [test_agent_memory.py](../tests/test_agent_memory.py) | 3 | 3 | System/long-term-memory context |
| [test_bridge_dashboard_recording.py](../tests/test_bridge_dashboard_recording.py) | 4 | 4 | Bridge task records/status |
| [test_bridge_policy.py](../tests/test_bridge_policy.py) | 5 | 5 | Request risk/approval classification |
| [test_cli_distribution.py](../tests/test_cli_distribution.py) | 6 | 6 | Node CLI/state distribution |
| [test_cli_safety_profiles.py](../tests/test_cli_safety_profiles.py) | 4 | 4 | Backend URLs/CLI safety options |
| [test_codex_cli_resolution.py](../tests/test_codex_cli_resolution.py) | 9 | 14 | Codex binaries/OS errors |
| [test_dashboard_execution_api.py](../tests/test_dashboard_execution_api.py) | 3 | 3 | FastAPI tasks/approvals/reads |
| [test_dashboard_store.py](../tests/test_dashboard_store.py) | 3 | 3 | Request/project aggregation |
| [test_dev_environment.py](../tests/test_dev_environment.py) | 8 | 9 | Development settings/venv/command boundaries/private-state copy rejection |
| [test_distribution_safety.py](../tests/test_distribution_safety.py) | 3 | 3 | Public-file copy/install |
| [test_execution_adapters.py](../tests/test_execution_adapters.py) | 10 | 10 | Execution adapters/artifacts |
| [test_execution_runtime.py](../tests/test_execution_runtime.py) | 3 | 3 | Execution coordination/approval/cancellation |
| [test_execution_store.py](../tests/test_execution_store.py) | 8 | 8 | Ledger/schema/leases |
| [test_manager_launchd.py](../tests/test_manager_launchd.py) | 2 | 2 | launchd retries |
| [test_memory_store.py](../tests/test_memory_store.py) | 3 | 3 | Memory candidate extraction/approval/search |
| [test_memory_worker.py](../tests/test_memory_worker.py) | 1 | 1 | One memory-worker run |
| [test_p0_operations.py](../tests/test_p0_operations.py) | 32 | 39 | Serialization/concurrent workers/file approval/recovery/migration |
| [test_policy_documents.py](../tests/test_policy_documents.py) | 1 | 1 | Combined Markdown policies |
| [test_runtime_paths.py](../tests/test_runtime_paths.py) | 5 | 5 | Code/state path separation |
| [test_safety_boundaries.py](../tests/test_safety_boundaries.py) | 11 | 13 | Permissions/paths/backups/memory isolation |
| [test_task_service.py](../tests/test_task_service.py) | 2 | 2 | Owner-specific execution/cancellation |
| [test_terminal_durable_path.py](../tests/test_terminal_durable_path.py) | 1 | 1 | Terminal ledger path |
| [test_work_queue.py](../tests/test_work_queue.py) | 12 | 16 | Claims/interruption holds/result persistence |
| [test_operation_shutdown.py](../tests/test_operation_shutdown.py) | 14 | 24 | Worker/bridge shutdown, parent loss and held partial application |
| [test_deployment_safety.py](../tests/test_deployment_safety.py) | 16 | 36 | Legacy holds/cancellation ownership/rechecks before file mutation |
| [test_package_followup.py](../tests/test_package_followup.py) | 7 | 11 | Explicit trust/privacy scanning/distribution files and links |
| [test_model_stdin.py](../tests/test_model_stdin.py) | 1 | 2 | Open parent pipes and model stdin isolation |
| [test_workspace_intake.py](../tests/test_workspace_intake.py) | 2 | 10 | Missing registration/intake failures/sensitive diagnostics |
| [test_publication_privacy.py](../tests/test_publication_privacy.py) | 6 | 85 | Reject private/dependency Git/package paths; retain required public files |
| **Total** | **186** | **327** | Excludes common configuration |

## test_dev_environment.py — 9 cases

Use temporary source trees and fake runners, without real operating services/models. Follow the [development installation guide](installation_and_distribution.md#development-install).

| Scenario | Setup/action → expected result | Cases |
|---|---|---:|
| Environment inheritance | Inject operating NYANYA/provider-auth/Python paths → replace with development paths or remove; retain HOME | 1 |
| Path diagnostics | paths without a venv → JSON diagnostics only, no state files | 1 |
| Command boundaries | service/setup requests → unsupported-command rejection | 1 |
| State path | State-directory symlink outside the tree → reject before execution | 1 |
| Command execution | Fake runner for a test command → development Python/cwd/state, preserved exit code | 1 |
| Lazy creation | Prepare lint then dashboard → only dashboard creates development state | 1 |
| Missing venv | Run without development venv → explicit failure without installation/runner invocation | 1 |
| Distribution boundary | Copy root/nested .dev-state through a public manifest → reject before destination creation | 2 |

Environment isolation is not an OS sandbox. CLI authentication files under preserved HOME remain accessible; real model/Discord/operating-recovery acceptance is separate.

## test_agent_memory.py — 3 cases

Use real temporary files/SQLite. Baseline assembly is an optional legacy-helper contract, not proof of normal worker injection. Verify approved-memory store APIs and owner filters without model APIs or semantic-quality assessment.

| ID | Setup/action → expected result | Input variant | Source function |
|---|---|---|---|
| TC-001 | Supply baseline system text and a temporary memory file → system message contains memory title/body | One case | [test_build_messages_includes_agent_memory](../tests/test_agent_memory.py#L7) |
| TC-002 | Missing memory file → baseline system message without error | One case | [test_build_messages_allows_missing_agent_memory](../tests/test_agent_memory.py#L26) |
| TC-003 | Approve extracted memory and query store API → only its owner can retrieve/format it; other owners get nothing | One case | [test_approved_memory_api_preserves_owner_scope](../tests/test_agent_memory.py) |

## test_bridge_dashboard_recording.py — 4 cases

Combine real stores/threads/SQLite with fake task responses. Do not exercise Discord intake/uploads/Gateway communication.

| ID | Setup/action → expected result | Input variant | Source function |
|---|---|---|---|
| TC-004 | Async fake done response → acknowledgement/objective/schedule/final answer; completed ledger/saved result/legacy read view | One case | [test_bridge_submit_records_async_completion](../tests/test_bridge_dashboard_recording.py#L34) |
| TC-005 | Hold first fake task and submit second → show first running, second queued and both titles | One case | [test_bridge_task_status_lists_running_and_queued](../tests/test_bridge_dashboard_recording.py#L89) |
| TC-006 | Submit upload callback returning uploaded → task ID, completed task and successful execution | One case | [test_bridge_custom_external_operation_is_durable](../tests/test_bridge_dashboard_recording.py#L112) |
| TC-007 | Unapproved README edit → plan/approval-required response instead of execution | One case | [test_bridge_answer_returns_plan_for_unapproved_file_mutation](../tests/test_bridge_dashboard_recording.py#L137) |

## test_bridge_policy.py — 5 cases

Check risk-classification functions and output wording, not every natural-language bypass or actual model compliance.

| ID | Setup/action → expected result | Input variant | Source function |
|---|---|---|---|
| TC-008 | Edit in an allowed but untrusted workspace → extended/high risk, approval required and not granted | One case | [test_extended_workspace_write_requires_approval](../tests/test_bridge_policy.py#L8) |
| TC-009 | Edit trusted workspace → trusted/medium risk still requires approval | One case | [test_trusted_file_mutation_still_gets_plan_gate](../tests/test_bridge_policy.py#L25) |
| TC-010 | Edit request containing an approval word → approval still required; no execution authority | One case | [test_approval_words_are_not_execution_authorization](../tests/test_bridge_policy.py#L38) |
| TC-011 | Build operating protocol → objective/scope/schedule/procedure/verification/interruption/replanning clauses | One case | [test_task_operating_protocol_preserves_objective_and_requires_replanning](../tests/test_bridge_policy.py#L48) |
| TC-012 | Web summary with hidden HTML instruction to ignore prior rules → blocked risk and stop/injection notice | One case | [test_external_hidden_prompt_injection_stops](../tests/test_bridge_policy.py#L59) |

## test_cli_distribution.py — 6 cases

Run Node and built CLI commands. If CLI files are absent, five tests skip while the manifest check remains. That check is not an npm-pack result; the update test checks instructions only.

| ID | Setup/action → expected result | Input variant | Source function |
|---|---|---|---|
| TC-013 | Inspect npm manifest/static files → dashboard patterns and actual HTML/CSS/JS exist | One case | [test_npm_manifest_includes_dashboard_assets](../tests/test_cli_distribution.py#L16) |
| TC-014 | Node config show with temporary state → separate path/user mode, owner-only config and no venv | One case | [test_config_show_creates_separate_state](../tests/test_cli_distribution.py#L40) |
| TC-015 | Set port 99999 and validate → exit 1 with port/validation errors | One case | [test_config_validate_rejects_invalid_port](../tests/test_cli_distribution.py#L54) |
| TC-016 | Node update → npm update instructions and state-preservation notice; no package update | One case | [test_update_command_preserves_user_state_policy](../tests/test_cli_distribution.py#L67) |
| TC-017 | Back up temporary config/SQLite/logs → copy config/DB, exclude logs | One case | [test_state_backup_copies_only_durable_items](../tests/test_cli_distribution.py#L76) |
| TC-018 | Migrate legacy config/SQLite/PID/venv → copy config/DB, exclude run/venv | One case | [test_state_migrate_excludes_venv_and_run](../tests/test_cli_distribution.py#L97) |

## test_cli_safety_profiles.py — 4 cases

Replace networking/CLI execution. Verify forwarded options rather than actual agy/Codex sandbox enforcement.

| ID | Setup/action → expected result | Input variant | Source function |
|---|---|---|---|
| TC-019 | Backend URL with file scheme → ValueError requiring HTTP/HTTPS | One case | [test_backend_request_rejects_non_http_scheme](../tests/test_cli_safety_profiles.py#L15) |
| TC-020 | HTTPS URL/fake JSON → parsed JSON object; no real HTTPS connection | One case | [test_backend_request_accepts_https](../tests/test_cli_safety_profiles.py#L20) |
| TC-021 | Fake agy runner → generated command includes sandbox and returns fake result | One case | [test_antigravity_uses_sandbox_by_default](../tests/test_cli_safety_profiles.py#L36) |
| TC-022 | Fake runner for normal Luna/Sol Codex → ignore user config, read-only and explicit model/effort | Two profiles | [test_codex_read_only_invocation_uses_isolated_config](../tests/test_cli_safety_profiles.py#L56) |

## test_codex_cli_resolution.py — 14 cases

Use actual temporary files/symlinks/permissions; one case runs a temporary shell. Other OS-error/preflight dependencies are mocked. No real Codex model calls.

| ID | Setup/action → expected result | Input variant | Source function |
|---|---|---|---|
| TC-023 | Temporary executable on PATH, no override → discover that binary | One case | [test_path_discovery](../tests/test_codex_cli_resolution.py#L21) |
| TC-024 | Valid PATH binary but missing override → None, no fallback | One case | [test_broken_override_does_not_fallback](../tests/test_codex_cli_resolution.py#L27) |
| TC-025 | Override first a nonexecutable file then directory → reject both | One case | [test_non_executable_and_directory_rejected](../tests/test_codex_cli_resolution.py#L33) |
| TC-026 | Override a broken symlink → reject | One case | [test_broken_symlink_rejected](../tests/test_codex_cli_resolution.py#L41) |
| TC-027 | Resolve/run temporary shell → exit 0, stdout ok and empty stderr | One case | [test_resolved_binary_starts](../tests/test_codex_cli_resolution.py#L48) |
| TC-028 | Missing normal-router binary → blocked, no alternative-model call | One case | [test_missing_binary_fails_before_spawn](../tests/test_codex_cli_resolution.py#L55) |
| TC-029 | Injected spawn OS error → safe failure only; exclude errno/private paths/details | ENOENT: missing file | [test_spawn_error_is_sanitized](../tests/test_codex_cli_resolution.py#L65) |
| TC-030 | Injected spawn OS error → safe failure only; exclude errno/private paths/details | EACCES: denied | [test_spawn_error_is_sanitized](../tests/test_codex_cli_resolution.py#L65) |
| TC-031 | Injected spawn OS error → safe failure only; exclude errno/private paths/details | EPERM: operation denied | [test_spawn_error_is_sanitized](../tests/test_codex_cli_resolution.py#L65) |
| TC-032 | Injected spawn OS error → safe failure only; exclude errno/private paths/details | ENOEXEC: invalid executable format | [test_spawn_error_is_sanitized](../tests/test_codex_cli_resolution.py#L65) |
| TC-033 | Injected spawn OS error → safe failure only; exclude errno/private paths/details | EMFILE: too many open files | [test_spawn_error_is_sanitized](../tests/test_codex_cli_resolution.py#L65) |
| TC-034 | Same manager/bridge override → matching resolution; missing path rejected by manager too | One case | [test_manager_uses_same_resolution](../tests/test_codex_cli_resolution.py#L81) |
| TC-035 | Preflight without Codex binary → exit according to whether Codex is enabled | Enabled: exit 1 | [test_preflight_checks_enabled_codex](../tests/test_codex_cli_resolution.py#L91) |
| TC-036 | Preflight without Codex binary → exit according to whether Codex is enabled | Disabled: exit 0 | [test_preflight_checks_enabled_codex](../tests/test_codex_cli_resolution.py#L91) |

## test_dashboard_execution_api.py — 3 cases

Use FastAPI TestClient/temporary DB, not TCP servers, browsers or remote-user environments. The historical read cases exercised unauthenticated reads and did not establish remote authentication; current authenticated-read regressions are listed above.

| ID | Setup/action → expected result | Input variant | Source function |
|---|---|---|---|
| TC-037 | TestClient task create/read/cancel/retry/health → unauthenticated create 401, authenticated 201, cancellation, retry 409 with cancelled state, historical schema 4 | One case | [test_execution_read_api_and_authenticated_control_actions](../tests/test_dashboard_execution_api.py#L43) |
| TC-038 | Authenticated project/logical Codex-session/task creation → retained links, API-key masking, project filtering/session query | One case | [test_execution_project_codex_session_and_task_filters](../tests/test_dashboard_execution_api.py#L86) |
| TC-039 | Authenticated approval decision/event cursor → approved response, events after cursor sequence | One case | [test_approval_decision_and_cursor_event_read](../tests/test_dashboard_execution_api.py#L130) |

## test_dashboard_store.py — 3 cases

Use actual SQLite storage/aggregation on temporary data. Generated Discord confirmation text is not sent.

| ID | Setup/action → expected result | Input variant | Source function |
|---|---|---|---|
| TC-040 | Request running→completed → duration/intake event/summary/daily completion aggregation | One case | [test_agent_request_lifecycle_and_usage](../tests/test_dashboard_store.py#L6) |
| TC-041 | Next action in planning phase → confirmation-required state and user notice | One case | [test_project_phase_check_requires_confirmation_when_next_action_exists](../tests/test_dashboard_store.py#L40) |
| TC-042 | Two phase checks in one interval → only first returns confirmation items | One case | [test_due_phase_checks_respects_interval](../tests/test_dashboard_store.py#L59) |

## test_distribution_safety.py — 3 cases

Copy files and run bash installation in temporary directories. One bash case skips on Windows. No dependency downloads, service registration, npm publication or Windows installation qualification.

| ID | Setup/action → expected result | Input variant | Source function |
|---|---|---|---|
| TC-043 | Public manifest alongside private fixtures → install public files/package manifest only | One case | [test_source_copy_uses_public_manifest_not_entire_checkout](../tests/test_distribution_safety.py#L11) |
| TC-044 | Private config or symlink in manifest → ValueError; no destination on first failure | One case | [test_source_copy_rejects_private_manifest_and_symlinks](../tests/test_distribution_safety.py#L24) |
| TC-045 | Bash installer in temporary path with spaces, no dependencies → success/private exclusion/state config/launcher help | One case | [test_clean_source_install_without_network_or_services](../tests/test_distribution_safety.py#L39) |

## test_execution_adapters.py — 5 cases

Run real subprocesses/tmux; tmux cases skip if unavailable. Orca/unused command-generation tests were removed. Some workspace checks are mocked, so this file alone does not prove path policy. Every descendant termination is not checked individually.

| ID | Setup/action → expected result | Input variant | Source function |
|---|---|---|---|
| TC-046 | Actual Python prints adapter-ok → succeeded, exit 0, output and completion marker | One case | [test_managed_subprocess_persists_completion_marker](../tests/test_execution_adapters.py#L54) |
| TC-047 | Cancel actual sleeping subprocess → cancelled and running false | One case | [test_managed_subprocess_can_cancel_process_group](../tests/test_execution_adapters.py#L73) |
| TC-048 | Short Python in actual tmux → succeeded, exit 0 and output | One case | [test_tmux_adapter_discovers_and_completes_session](../tests/test_execution_adapters.py#L91) |
| TC-054 | Stored live PID without an owned process object → lost/running true without signals | One case | [test_restarted_adapter_does_not_signal_unowned_pid](../tests/test_execution_adapters.py#L109) |
| TC-055 | Live fake process with signal permission error → lost/running true rather than cancelled | One case | [test_permission_denied_is_not_reported_as_cancelled](../tests/test_execution_adapters.py#L119) |

## test_execution_runtime.py — 3 cases

Use real Python subprocesses/SQLite with mocked workspace admission. Recovery recreates objects within one test, not a forced OS/service crash. The approval command prints, so it does not test actual file modification/application.

| ID | Setup/action → expected result | Input variant | Source function |
|---|---|---|---|
| TC-056 | Run short Python, recreate coordinator/adapter → saved handle/marker recovers success, task completed/session stopped | One case | [test_coordinator_recovers_from_persisted_handle_and_marker](../tests/test_execution_runtime.py#L37) |
| TC-057 | Observe completion marker with writer lease → release old lease; next execution can acquire | One case | [test_recovery_releases_persisted_writer_lease](../tests/test_execution_runtime.py#L58) |
| TC-058 | Coordinator cancels actual sleeping Python → execution/task cancelled | One case | [test_coordinator_cancels_active_execution](../tests/test_execution_runtime.py#L80) |

## test_execution_store.py — 8 cases

Use actual SQLite/threads; host/profile names are fixtures. Heartbeat checks assert offline directly, not the stale branch or raw-status invariance. Append-only checks exercise UPDATE only.

| ID | Setup/action → expected result | Input variant | Source function |
|---|---|---|---|
| TC-059 | Initialize schema twice, UPDATE event → same latest schema and append-only rejection | One case | [test_versioned_migration_is_idempotent_and_events_are_append_only](../tests/test_execution_store.py#L13) |
| TC-060 | Twelve initializations across six threads → all latest schema, final agreement | One case | [test_concurrent_schema_bootstrap_is_serialized](../tests/test_execution_store.py#L32) |
| TC-061 | Host/profile/task/execution running→succeeded → end time/task completed; reject reversal to running | One case | [test_task_execution_lifecycle_and_status_projection](../tests/test_execution_store.py#L42) |
| TC-062 | Project/logical Codex-session/task links → aggregation/redacted metadata; reject session from another project | One case | [test_projects_and_codex_sessions_are_linked_to_tasks](../tests/test_execution_store.py#L65) |
| TC-063 | Approval with sensitive synthetic metadata → approved while password/reason/events hide fixture values | One case | [test_approval_and_audit_metadata_are_redacted](../tests/test_execution_store.py#L105) |
| TC-064 | Worker A obtains lease, B competes → fence 1, B rejected, A renew/release succeeds | One case | [test_writer_lease_uses_fencing_and_owner_checks](../tests/test_execution_store.py#L129) |
| TC-065 | Host/runtime-session heartbeat 400 seconds old → offline read projection | One case | [test_heartbeat_reports_stale_and_offline_without_destroying_raw_status](../tests/test_execution_store.py#L151) |
| TC-066 | One-time legacy import, then change legacy state → no overwrite of existing task state | One case | [test_legacy_import_is_one_way_and_never_overwrites_current_ledger](../tests/test_execution_store.py#L169) |

## test_manager_launchd.py — 2 cases

Mock launchctl and sleep; no proof of real macOS service recovery/permissions/registration.

| ID | Setup/action → expected result | Input variant | Source function |
|---|---|---|---|
| TC-067 | Fake bootstrap error 5 then success → one requested 0.25-second wait; second call succeeds | One case | [test_bootstrap_with_retry_recovers_launchd_transition](../tests/test_manager_launchd.py#L9) |
| TC-068 | Fake bootstrap error 78 → unchanged error without wait/retry | One case | [test_bootstrap_with_retry_does_not_retry_other_errors](../tests/test_manager_launchd.py#L33) |

## test_memory_store.py — 3 cases

SQLite checks for rule-based candidate extraction/approval/search. Graphs were removed. Not an assessment of real LLM summary quality.

| ID | Setup/action → expected result | Input variant | Source function |
|---|---|---|---|
| TC-069 | Extract report-format memory from completed request → one pending candidate with importance rule | One case | [test_extract_memory_candidates](../tests/test_memory_store.py#L6) |
| TC-070 | Change candidate status/importance → approved and importance 90 persisted | One case | [test_update_memory_status](../tests/test_memory_store.py#L35) |
| TC-071 | Search same phrase before/after approval → exclude pending, include approved in results/context | One case | [test_search_approved_memories_returns_only_approved](../tests/test_memory_store.py#L48) |

## test_memory_worker.py — 1 cases

Call the worker once; long-running residence, periodic execution and LLM refinement are not tested.

| ID | Setup/action → expected result | Input variant | Source function |
|---|---|---|---|
| TC-073 | One worker run with completed request and refinement disabled → one pending/normal candidate, one refinement skipped | One case | [test_memory_worker_run_once_creates_pending_candidate](../tests/test_memory_worker.py#L7) |

## test_policy_documents.py — 1 cases

Check included files/specific wording, not policy validity or runtime enforcement.

| ID | Setup/action → expected result | Input variant | Source function |
|---|---|---|---|
| TC-074 | Load policies/build protocol → specified files and ledger/Tailscale/review-gate clauses | One case | [test_markdown_policy_set_is_loaded_into_operating_protocol](../tests/test_policy_documents.py#L7) |

## test_runtime_paths.py — 5 cases

Check path calculation and temporary plist generation without registering launchd services.

| ID | Setup/action → expected result | Input variant | Source function |
|---|---|---|---|
| TC-075 | macOS with temporary home → application state under Library/Application Support | One case | [test_default_user_state_root_uses_macos_application_support](../tests/test_runtime_paths.py#L10) |
| TC-076 | Legacy config in code tree without state override → keep code tree as legacy state | One case | [test_resolve_state_root_preserves_legacy_source_env](../tests/test_runtime_paths.py#L16) |
| TC-077 | Legacy config plus explicit state override → override wins | One case | [test_resolve_state_root_honors_explicit_home](../tests/test_runtime_paths.py#L24) |
| TC-078 | Relative DB path with temporary state root → absolute path relative to state | One case | [test_dashboard_relative_db_path_uses_state_root](../tests/test_runtime_paths.py#L34) |
| TC-079 | Generate plist with separate code/state/LaunchAgents → Python command/environments/log paths separated; no registration | One case | [test_launchagent_uses_separate_code_and_state_paths](../tests/test_runtime_paths.py#L47) |

## test_safety_boundaries.py — 13 cases

Use temporary DB/files and fake backend. Check three representative approval phrases and specific paths; revocation, just-before-write races and mediation of every CLI artifact are not covered here.

| ID | Setup/action → expected result | Input variant | Source function |
|---|---|---|---|
| TC-080 | Remove workspace settings → no allowed root/HOME access; default-workspace selection errors | One case | [test_unconfigured_roots_do_not_grant_home](../tests/test_safety_boundaries.py#L15) |
| TC-081 | Allowed root without owner mapping → block owner execution-workspace selection | One case | [test_unassigned_user_cannot_fallback_to_an_allowed_root](../tests/test_safety_boundaries.py#L24) |
| TC-082 | Parent traversal/outside symlink/outside absolute path → reject; allow internal new path, unique task folders, reject invalid kind | One case | [test_paths_reject_traversal_and_symlink_escape](../tests/test_safety_boundaries.py#L35) |
| TC-083 | Edit/delete with approval words → awaiting_approval without backend call | Korean fixture: `승인: README.md 파일을 수정해` | [test_terminal_write_gate_cannot_be_bypassed_by_words](../tests/test_safety_boundaries.py#L51) |
| TC-084 | Edit/delete with approval words → awaiting_approval without backend call | Korean fixture: `승인하지 않았지만 README.md 수정` | [test_terminal_write_gate_cannot_be_bypassed_by_words](../tests/test_safety_boundaries.py#L51) |
| TC-085 | Edit/delete with approval words → awaiting_approval without backend call | approved delete file.txt | [test_terminal_write_gate_cannot_be_bypassed_by_words](../tests/test_safety_boundaries.py#L51) |
| TC-086 | Make host-inventory collection fail if called, then build context → user message without collection | One case | [test_model_context_does_not_collect_process_or_directory_inventory](../tests/test_safety_boundaries.py#L59) |
| TC-087 | Exact approval, altered scope, other task, reuse after consumption → allow first only; one use | One case | [test_approval_checks_scope_actor_expiry_and_single_use](../tests/test_safety_boundaries.py#L74) |
| TC-088 | Set approved command expiry in the past → reject execution authorization | One case | [test_expired_approved_command_is_rejected](../tests/test_safety_boundaries.py#L87) |
| TC-089 | Wrong actor/expired approval decisions → reject; persist expired state | One case | [test_approval_wrong_decider_and_expiry_persist](../tests/test_safety_boundaries.py#L95) |
| TC-090 | Back up committed WAL rows while connection stays open → preserve row; reject overwrite | One case | [test_backup_includes_committed_wal_and_refuses_overwrite](../tests/test_safety_boundaries.py#L109) |
| TC-091 | Back up non-DB bytes → DatabaseError, unchanged source, failed destination removed | One case | [test_corrupt_database_backup_fails_without_touching_source](../tests/test_safety_boundaries.py#L126) |
| TC-092 | Extract/approve owner one memory → one finds it, two does not | One case | [test_memory_is_not_globally_promoted_or_retrieved](../tests/test_safety_boundaries.py#L135) |

## test_task_service.py — 2 cases

Connect fake runners/responders to actual threads/SQLite. Not evidence of restartable independent workers or model-process termination.

| ID | Setup/action → expected result | Input variant | Source function |
|---|---|---|---|
| TC-093 | Hold first same-owner runner, submit second → queued/project-linked; release first → two replies/success states | One case | [test_service_persists_queue_and_runs_one_task_per_owner](../tests/test_task_service.py#L21) |
| TC-094 | Cancel running/queued work → queued cancelled, runner receives cancellation and returns cancelled; one execution reply | One case | [test_service_cancellation_reaches_running_handler_and_queued_task](../tests/test_task_service.py#L69) |

## test_terminal_durable_path.py — 1 cases

Use the actual terminal function/worker thread/SQLite with fake models, not real external-model connections.

| ID | Setup/action → expected result | Input variant | Source function |
|---|---|---|---|
| TC-095 | Terminal request with fake model worker → answer/exit 0 and completed operator task/operation | One case | [test_terminal_single_prompt_uses_durable_execution_path](../tests/test_terminal_durable_path.py#L4) |

## test_work_queue.py — 16 cases

Use actual SQLite, threads and cross-process competition. Build expiry/stale/v2 fixtures inside tests. No crash-site fault injection or Discord delivery. Atomicity-labelled tests check status/result consistency without forced death during commit.

| ID | Setup/action → expected result | Input variant | Source function |
|---|---|---|---|
| TC-096 | Six competing claims across three processes → one claim/execution | One case | [test_separate_processes_claim_once](../tests/test_work_queue.py#L18) |
| TC-097 | Old queued row plus 600 completed rows → old queued work remains visible | One case | [test_pending_queue_not_limited_by_history](../tests/test_work_queue.py#L27) |
| TC-098 | Expired claim → reject renewal/completion/reclaim; recovery list retains raw running state | One case | [test_expired_worker_cannot_renew_commit_or_be_replayed](../tests/test_work_queue.py#L37) |
| TC-099 | Failure-like response text with typed outcome → type-based status, reject other-owner reads; approval wait creates feedback.review | awaiting_approval-awaiting_approval | [test_typed_outcomes_are_saved_atomically](../tests/test_work_queue.py#L53) |
| TC-100 | Failure-like response text with typed outcome → type-based status, reject other-owner reads; approval wait creates feedback.review | blocked-blocked | [test_typed_outcomes_are_saved_atomically](../tests/test_work_queue.py#L53) |
| TC-101 | Failure-like response text with typed outcome → type-based status, reject other-owner reads; approval wait creates feedback.review | timed_out-failed | [test_typed_outcomes_are_saved_atomically](../tests/test_work_queue.py#L53) |
| TC-102 | Failure-like response text with typed outcome → type-based status, reject other-owner reads; approval wait creates feedback.review | failed-failed | [test_typed_outcomes_are_saved_atomically](../tests/test_work_queue.py#L53) |
| TC-103 | Failure-like response text with typed outcome → type-based status, reject other-owner reads; approval wait creates feedback.review | succeeded-completed | [test_typed_outcomes_are_saved_atomically](../tests/test_work_queue.py#L53) |
| TC-104 | Runner success after cancellation request → task blocked, not confirmed cancellation | One case | [test_cancellation_request_does_not_prove_termination](../tests/test_work_queue.py#L65) |
| TC-105 | Runner succeeds/responder raises → preserve result, delivery uncertain; save error type rather than sensitive details | One case | [test_delivery_failure_preserves_completed_result](../tests/test_work_queue.py#L74) |
| TC-106 | Old queued task/new service/new callback → new callback does not run for 0.6 seconds; old work remains in recovery | One case | [test_restarted_service_does_not_run_old_callbacks](../tests/test_work_queue.py#L92) |
| TC-107 | New execution then force old success → Stale error and preserved current execution | One case | [test_old_attempt_cannot_override_new_attempt_even_with_force](../tests/test_work_queue.py#L104) |
| TC-108 | Release/reacquire/expire lease → increased fence, expired renewal rejected | One case | [test_lease_fence_survives_release_and_expired_renewal_fails](../tests/test_work_queue.py#L114) |
| TC-109 | Build v2 queued fixture then migrate → latest schema, queued state/recovery preserved | One case | [test_schema_two_upgrades_preserving_queued_work](../tests/test_work_queue.py#L126) |
| TC-110 | Claim as another owner → reject, task stays queued | One case | [test_claim_cannot_change_task_owner](../tests/test_work_queue.py#L137) |
| TC-111 | Insert z-old then a-new at same time → insertion order rather than lexical ID order | One case | [test_equal_timestamp_queue_preserves_insertion_order](../tests/test_work_queue.py#L144) |

## Test support code

These helpers are not counted as separate cases.

| Helper | Purpose |
|---|---|
| [conftest.py: pytest_configure](../tests/conftest.py#L8) | Prepare common temporary environment |
| [conftest.py: pytest_unconfigure](../tests/conftest.py#L23) | Restore/clean common environment |
| [test_bridge_dashboard_recording.py: registered_workspace](../tests/test_bridge_dashboard_recording.py#L16) | Register temporary owner workspace for each bridge test |
| [test_cli_distribution.py: run_cli](../tests/test_cli_distribution.py#L24) | Run built Node CLI with temporary state |
| [test_codex_cli_resolution.py: executable](../tests/test_codex_cli_resolution.py#L10) | Temporary shell fixture standing in for Codex |
| [test_execution_adapters.py: wait_for_terminal](../tests/test_execution_adapters.py#L14) | Bounded polling until adapter terminal state |
| [test_safety_boundaries.py: approved_command](../tests/test_safety_boundaries.py#L64) | Approval fixture tied to exact scope/actor |
| [test_task_service.py: wait_for](../tests/test_task_service.py#L11) | Bounded wait for an asynchronous condition |
| [test_work_queue.py: competing_claim](../tests/test_work_queue.py#L13) | Competing claim from a separate process |

## What the historical tests did not establish

| Product expectation | Historical evidence | Remaining verification |
|---|---|---|
| Actual Discord completion | Bridge callback/DB integration | Gateway intake → actual model → message/attachment delivery |
| Post-interruption reminders | Queued preservation/recovery queries/fake responder failure | Actual bridge/worker death, reconnect notices, duplicate intake and receipt failures |
| Existing files only after approval | Representative phrase rejection/command-scope approval | Per-file diff/hash, revocation, just-before-write races and real apply paths |
| Safe Codex/agy execution | Command flags/fake binaries/OS errors | Installed sandbox/model responses/authentication/OS permissions |
| Task-specific folders/artifacts | Path helpers/unique directories/artifact records | Mediate every model-generated path and actual Discord attachment flow |
| Cancellation | Test child processes/callback cancellation | Grandchildren/detached processes/provider cancellation/post-restart termination confirmation |
| Upgrade/restore | v2→v4 queued fixture, v3→v4 task/execution/approval/event backup/restore, WAL backup | Full legacy/v1 references, restore/rollback, disk-full and concurrent changes |
| Privacy | Selected metadata masking/owner search | Retention/deletion for all logs/artifacts/backups, project/concurrent-owner isolation |
| Reliable distribution | Temporary bash install/Node state commands | Windows/minimum-version matrix, dependency audit and actual install/update/uninstall |
| Multi-agent/model routing | No direct evidence at this historical stage | Planner/capabilities/distribution/cost/concurrency/result merging |

Names such as atomic, restart, recover or sandbox do not broaden the actual assertions. Separate manual scenarios are in [user acceptance tests](user_acceptance_tests.md).

## Running and collecting

Use the repository venv from the source root. These are examples; the full suite was not rerun for this documentation update.

```bash
# Collect cases only, without executing test bodies
PYTHONPATH=src .venv/bin/python -m pytest --collect-only -q tests

# Run the full suite
PYTHONPATH=src .venv/bin/python -m pytest -q tests

# Run important queue and safety boundaries
PYTHONPATH=src .venv/bin/python -m pytest -v tests/test_work_queue.py tests/test_safety_boundaries.py

# Run one test function
PYTHONPATH=src .venv/bin/python -m pytest -v tests/test_work_queue.py::test_separate_processes_claim_once

# Include skip reasons
PYTHONPATH=src .venv/bin/python -m pytest -q -rs tests
```

Build Node CLI artifacts before CLI tests. Five skips caused by a missing CLI are not passes. Two tmux cases skip without tmux; one bash-install case skips on Windows. Other missing dependencies can cause collection errors/failures rather than skips. Report passed/failed/skipped separately.

Ruff, TypeScript typecheck/build, JavaScript syntax, release/privacy and document-link checks are separate commands, outside the historical 233 pytest cases.

## Documentation handoff — historical 2026-09-12

2026-09-12 / CORE-STAB-01 P0 follow-up, main, baseline 52a1bb5. Preserved uncommitted work and updated this guide for runtime/tests. At that time: 22 files/132 functions/150 collected cases. The original 111-case documentation-only work is a separate 2026-09-10 record. [P0 handoff](p0_execution_20260912.md) defines source/verification/rollback/not-installed scope.

## Added P0 cases — 39

Common setup is a temporary workspace/DB and fake model Worker. Cases without an explicit real-model label do not access model accounts. Real-model evidence is separate in the P0 handoff.

| ID | Inputs and expected results | Parameters | Source |
|---|---|---|---|
| TC-112 | Specification JSON roundtrip; reject shell field/unsupported version | One case | [test_operation_roundtrip_and_unknown_executable_fields](../tests/test_p0_operations.py#L38) |
| TC-113 | Execute data-only specification without submitter callback; save result/routing event | One case | [test_data_only_operation_runs_without_submitter_callback](../tests/test_p0_operations.py#L48) |
| TC-114 | Three same-owner requests compete → two distinct claims; third queued | One case | [test_same_owner_parallelism_and_global_capacity](../tests/test_p0_operations.py#L57) |
| TC-115 | Dead-worker request held; other completion reminds about it; reject cross-owner reads | One case | [test_dead_worker_queue_is_held_but_other_tasks_can_complete](../tests/test_p0_operations.py#L67) |
| TC-116 | Reject old worker completion; explicit resume runs a new attempt on a new worker | One case | [test_recovery_rejects_old_worker_result_and_requires_explicit_resume](../tests/test_p0_operations.py#L88) |
| TC-117 | Historical score/profile mapping with Luna xhigh/Astra low | 1-1-1-flash | [test_routing_axes](../tests/test_p0_operations.py#L107) |
| TC-118 | Historical score/profile mapping with Luna xhigh/Astra low | 2-2-3-luna | [test_routing_axes](../tests/test_p0_operations.py#L107) |
| TC-119 | Historical score/profile mapping with Luna xhigh/Astra low | 4-1-2-astra | [test_routing_axes](../tests/test_p0_operations.py#L107) |
| TC-120 | Historical score/profile mapping with Luna xhigh/Astra low | 1-4-1-astra | [test_routing_axes](../tests/test_p0_operations.py#L107) |
| TC-121 | Historical score/profile mapping with Luna xhigh/Astra low | 1-1-5-astra | [test_routing_axes](../tests/test_p0_operations.py#L107) |
| TC-122 | Invalid boolean score → hold/saved cause, no model fallback | One case | [test_bad_model_assessment_fails_without_fallback](../tests/test_p0_operations.py#L118) |
| TC-123 | Unchanged before approval; wrong owner/hash rejected; apply/journal backup after approval, no reuse | One case | [test_review_preview_approval_and_exact_apply](../tests/test_p0_operations.py#L142) |
| TC-124 | Create under document/date folder; preserve existing files | One case | [test_create_is_exclusive_and_under_dated_task_directory](../tests/test_p0_operations.py#L165) |
| TC-125 | Changed preimage/expiry/revocation/symlink → reject even after approval | edited | [test_approval_revalidation_before_apply](../tests/test_p0_operations.py#L185) |
| TC-126 | Changed preimage/expiry/revocation/symlink → reject even after approval | expired | [test_approval_revalidation_before_apply](../tests/test_p0_operations.py#L185) |
| TC-127 | Changed preimage/expiry/revocation/symlink → reject even after approval | revoked | [test_approval_revalidation_before_apply](../tests/test_p0_operations.py#L185) |
| TC-128 | Changed preimage/expiry/revocation/symlink → reject even after approval | symlink | [test_approval_revalidation_before_apply](../tests/test_p0_operations.py#L185) |
| TC-129 | Deletion preserves file until approval, then removes only specified file | One case | [test_delete_needs_approval](../tests/test_p0_operations.py#L206) |
| TC-130 | Second of two replacements fails → preserve first effect/preimages/journal; reject replay | One case | [test_partial_apply_failure_has_journal_and_no_automatic_replay](../tests/test_p0_operations.py#L217) |
| TC-131 | Model edit → awaiting_approval → exact human approval → apply and original task completed | One case | [test_worker_executes_generated_plan_but_waits_for_modification_approval](../tests/test_p0_operations.py#L250) |
| TC-132 | Remove workspace registration after intake → worker recheck rejects file operation | One case | [test_workspace_registration_revalidated_in_worker](../tests/test_p0_operations.py#L281) |
| TC-133 | Exclude env/workspace mapping/symlinks from snapshot; public files only | One case | [test_snapshot_does_not_include_private_state_or_symlinks](../tests/test_p0_operations.py#L292) |
| TC-134 | Barrier proves two threads enter model stage simultaneously | One case | [test_two_real_worker_threads_run_simultaneously](../tests/test_p0_operations.py#L302) |
| TC-135 | Separate actual Python worker/fake CLI → process specification, retrieve result, exit | One case | [test_dedicated_worker_process_executes_spec_with_fake_cli](../tests/test_p0_operations.py#L336) |
| TC-136 | Stop/kill actual worker → queued request preserved, hold/reason query | One case | [test_real_worker_death_preserves_queued_request](../tests/test_p0_operations.py#L364) |
| TC-137 | Immediately after resume, no old result returned/delivered; receive new attempt only | One case | [test_resume_wait_and_delivery_never_return_previous_attempt](../tests/test_p0_operations.py#L387) |
| TC-138 | Reject resume without live worker; reject attempts beyond three total | One case | [test_explicit_retries_are_bounded_and_require_live_generation](../tests/test_p0_operations.py#L408) |
| TC-139 | Reject other-owner resolve; changed files invalidate observation hash; confirmation never rewrites | One case | [test_interrupted_apply_resolution_binds_owner_and_observed_files](../tests/test_p0_operations.py#L423) |
| TC-140 | Preserve reviewed original/diff after external edits; warn about changed state | One case | [test_preview_preserves_original_review_even_after_external_change](../tests/test_p0_operations.py#L451) |
| TC-141 | Reject unauthenticated intake; authenticated API uses worker; unsent result stays pending | One case | [test_api_operation_submission_uses_worker_and_preserves_undelivered_result](../tests/test_p0_operations.py#L469) |
| TC-142 | Four actual processes compete → only two distinct tasks claimed | One case | [test_separate_process_claims_share_atomic_capacity](../tests/test_p0_operations.py#L494) |
| TC-143 | Expired claim held even with live worker heartbeat; stale completion rejected | One case | [test_expired_claim_is_held_even_with_live_worker_heartbeat](../tests/test_p0_operations.py#L507) |
| TC-144 | File created/result lost → request resume must not create again | One case | [test_creation_side_effects_cannot_be_replayed_after_result_loss](../tests/test_p0_operations.py#L519) |
| TC-145 | Cancelled original request → reject approved plan apply | One case | [test_cancelled_original_task_cannot_apply_approved_plan](../tests/test_p0_operations.py#L541) |
| TC-146 | Worker startup error → saved original request/cause and immediate held-result query | One case | [test_worker_start_failure_retains_request_and_reason](../tests/test_p0_operations.py#L560) |
| TC-147 | Remote/forwarded reads require tokens; check loopback/health boundary | One case | [test_remote_and_forwarded_reads_require_authentication](../tests/test_p0_operations.py#L575) |
| TC-148 | Back up v3 tasks/executions/approvals/events → latest upgrade/v3 restore preserve integrity/references | One case | [test_schema_three_backup_upgrade_and_restore_preserve_work](../tests/test_p0_operations.py#L591) |
| TC-149 | Cancel/reap actual test process; 5 MB output exceeds bound and is held | One case | [test_owned_process_cancellation_and_output_limit](../tests/test_p0_operations.py#L619) |
| TC-150 | Kill actual apply process just after replace/fsync → after file/prepared journal; no replay, complete via observation-hash confirmation | Actual POSIX process kill | [test_real_apply_crash_after_file_commit_is_reconciled_without_replay](../tests/test_p0_operations.py#L652) |

## Added OPS-DEPLOY-01 cases — 71

Static comparison on 2026-09-13: 37 new functions produce 71 parameter combinations. Each row represents a function; grouped TC IDs represent the input-column combination count. Internal loops do not create separate pytest cases. Preserve TC-001–150 and 111/150-stage explanations as history. The preceding limits table describes that stage; shutdown/apply/trust/package evidence is separated below.

### test_operation_shutdown.py — Shutdown

Use temporary SQLite/workspaces and actual threads/OS pipes. Startup failures use fake processes/clocks, Discord uses FakeClient, Telegram uses mocked settings/execution. Four signal cases and one controller-loss case run actual temporary Python processes with mocked models. One partial-apply and those five process cases skip outside POSIX. They do not prove operating-service shutdown, real Discord Gateway/Telegram communication, real Codex/agy calls or termination of every detached descendant.

| ID | Input/variant | Expected assertions | Source function |
|---|---|---|---|
| TC-151–154 | once=False/True × explicit_cancel=False/True, four combinations | Resident/run_once shutdown holds running/queued work; only explicitly cancelled running work becomes cancelled. Preserve already-cancelled queued tasks/completed results, original request/stages/non-user-cancellation notice. Worker closes, all claims release/events settle, no automatic claim by a new worker | [test_shutdown_holds_work_but_preserves_explicit_cancel_and_completion](../tests/test_operation_shutdown.py#L56) |
| TC-155 | One case | Explicit cancellation during mocked execution plus termination acknowledgement → cancelled task; worker stop remains unset | [test_explicit_cancel_without_worker_shutdown](../tests/test_operation_shutdown.py#L102) |
| TC-156 | One case | perform sets stop and returns success → preserve completed task, clean worker/claim/events rather than relabel blocked | [test_completed_result_during_shutdown_is_not_relabelled](../tests/test_operation_shutdown.py#L117) |
| TC-157 | One case | Stop before run_once → no execution, False, blocked task, attempts=0, worker cleanup | [test_run_once_already_stopped_does_not_claim](../tests/test_operation_shutdown.py#L131) |
| TC-158 | One case | KeyboardInterrupt in perform → rethrow; blocked task, closed worker, no unreleased claims, event cleanup | [test_run_once_base_exception_stops_monitor_and_recovers](../tests/test_operation_shutdown.py#L142) |
| TC-159 | One POSIX-only case | Shutdown just after first of two replacements → first after/second before, blocked apply/uncertain plan. New worker rejects parent/apply resume for reconciliation; no automatic claim; old worker cleaned | [test_shutdown_during_partial_apply_keeps_reconciliation_gate](../tests/test_operation_shutdown.py#L157) |
| TC-160–161 | cannot_reap=False/True, two combinations | Fake clock/process startup timeout → terminate→wait(5)→kill→wait(3); preserve blocked task/start-failure cause even if unreapable. Check closed stdin, unset generation, parent PID and PIPE arguments | [test_startup_timeout_bounds_terminate_kill_reap_and_retains_request](../tests/test_operation_shutdown.py#L222) |
| TC-162 | One case, two spawn attempts | Injected Popen OSError each time → exception/unset generation; second call retries spawn rather than caching readiness | [test_failed_spawn_is_not_cached_as_ready](../tests/test_operation_shutdown.py#L246) |
| TC-163 | One case: parent-pipe EOF and invalid parent | Actual OS pipe stays open → no stop; closing writer → stop. Invalid parent identity fails closed immediately | [test_parent_pipe_loss_stops_worker_and_wrong_parent_fails_closed](../tests/test_operation_shutdown.py#L262) |
| TC-164–167 | SIGTERM/SIGINT × once=False/True, four POSIX combinations | Actual temporary Python worker prints RUNNING then receives signal → one closed worker, two blocked running/queued tasks, CLOSED_AND_HELD, exit 0/no stderr; mocked model | [test_standalone_worker_main_signals_close_and_hold](../tests/test_operation_shutdown.py#L283) |
| TC-168 | One POSIX-only case | Kill test-created controller → child watches inherited pipe, holds running/queued tasks, prints CLOSED_AND_HELD/no stderr. Mocked model; never discovers arbitrary operating PIDs | [test_real_controller_death_closes_orphan_worker_without_replay](../tests/test_operation_shutdown.py#L331) |
| TC-169–171 | termination=sigterm/cancel/failure, three combinations | Repeated SIGTERM/async cancellation/startup error on fake Discord client → close client first, store close once off-loop, event loop stays responsive. Restore SIGTERM; no SIGINT registration; rethrow cancellation/failure | [test_discord_orderly_close_is_off_loop_and_restores_signal](../tests/test_operation_shutdown.py#L396) |
| TC-172 | One helper-thread case | Close fake Discord client on a helper-thread event loop → thread exits, one close, no signal registration | [test_discord_does_not_register_signals_off_main_thread](../tests/test_operation_shutdown.py#L447) |
| TC-173–174 | main_thread=False/True, two combinations | Mock Telegram config/store/run → main thread handles SIGTERM/restores handler/returns; helper thread registers no signals and exits. Close store once in both | [test_telegram_sigterm_cleanup_and_thread_guard](../tests/test_operation_shutdown.py#L466) |

### test_deployment_safety.py — Deployment safety

Use actual temporary SQLite/filesystems and monkeypatch fault injection. Six API cases call FastAPI TestClient in-process, not a live server. Legacy-writer quiescence/backup confirmation are fixture prerequisites/arguments, not proof of operating-process shutdown, backups or live migration. Stored typed outcomes simulate cancellation confirmation; no real models/Discord/service deployment. File-application evidence applies to the candidate host, not guaranteed Windows support.

| ID | Input/variant | Expected assertions | Source function |
|---|---|---|---|
| TC-175–176 | version=2/3, two combinations | Upgrade temporary legacy DB; ordinary recovery does not hold legacy running work. Reject writers_stopped=False; explicit True holds two tasks/all attempts lost/releases claims. Repeated call returns zero; preserve original request/reason/attempt counts 2/0; two events and FK integrity. No new operation/automatic claim; no resume, explicit cancellation allowed | [test_quiesced_legacy_upgrade_holds_all_attempts_without_replay](../tests/test_deployment_safety.py#L43) |
| TC-177–178 | attempts=0/2, two combinations | Set operation attempt count independently of one execution row → incomplete/explain use explicit attempts rather than execution count | [test_incomplete_preserves_operation_attempts_over_execution_count](../tests/test_deployment_safety.py#L91) |
| TC-179 | One case | Inject legacy-hold audit failure → exception and atomic preservation of running task/execution/unreleased claim | [test_upgrade_audit_failure_rolls_back_task_execution_and_claim](../tests/test_deployment_safety.py#L100) |
| TC-180–181 | claim_state=expired/released, two combinations | Cancel unusable claim → blocked task/lost execution/released claim/eligible=0 rather than indefinite cancelling; late success raises Stale | [test_cancellation_without_usable_claim_does_not_wait_forever](../tests/test_deployment_safety.py#L122) |
| TC-182 | One case | Cancel valid claim → task/execution stay cancelling until worker cancelled result completes task | [test_active_cancel_still_requires_worker_acknowledgement](../tests/test_deployment_safety.py#L140) |
| TC-183 | One case | Close worker after cancellation but before acknowledgement → one recovered item, blocked task/lost execution | [test_cancel_remains_recoverable_if_worker_dies_before_acknowledgement](../tests/test_deployment_safety.py#L150) |
| TC-184 | One case | Cancel with old expected_execution_id → no-longer-current error, current execution remains running | [test_old_execution_cancellation_cannot_cancel_a_new_attempt](../tests/test_deployment_safety.py#L160) |
| TC-185–188 | endpoint=tasks/executions × approved=False/True, four combinations | API cancel approval-wait parent → unauthenticated 401/authenticated 200/cancelled. Pending/approved plans both reject later approval/apply; preimage unchanged | [test_dashboard_cancel_waiting_parent_prevents_approval_and_apply](../tests/test_deployment_safety.py#L170) |
| TC-189–190 | endpoint=tasks/executions, two combinations | Forge another task owner in payload and authenticated cancellation → 403; execution remains running | [test_dashboard_cancel_does_not_trust_payload_owner](../tests/test_deployment_safety.py#L197) |
| TC-191–198 | loss=eligible/released/expired/current/worker/execution/parent/missing_record, eight combinations | Remove eligibility/release or expire claim/remove current linkage/close worker/cancel execution or parent/remove record → apply rejected, zero journals, preimage/original file set preserved | [test_stale_apply_rejected_before_journal](../tests/test_deployment_safety.py#L217) |
| TC-199–201 | action=create/modify/delete, three combinations | Remove eligibility after journal but before first workspace mutation → ownership error/uncertain plan, identical before/after bytes; creation does not make directories | [test_eligibility_lost_after_journal_before_any_workspace_mutation](../tests/test_deployment_safety.py#L246) |
| TC-202 | One case | Remove eligibility immediately after temporary-file fsync transaction → ownership error, original before, one preserved after-content temp, uncertain plan; no replacement or further temp cleanup | [test_eligibility_loss_after_temp_write_prevents_replace_and_cleanup](../tests/test_deployment_safety.py#L277) |
| TC-203–207 | (create,mkdir), (create,open), (modify,open), (modify,fchmod), (modify,replace), five combinations | Remove eligibility at DB boundary immediately after selected mutation → ownership error/uncertain plan. Observed paths/permissions/bytes at loss equal final inventory; no subsequent mutation | [test_no_further_mutations_after_ownership_loss_at_each_boundary](../tests/test_deployment_safety.py#L313) |
| TC-208 | One case | Valid approval/current product record → apply/finish, after content and completed parent | [test_valid_product_record_applies_and_completes_parent](../tests/test_deployment_safety.py#L359) |
| TC-209 | One case | Create with valid product record then simulate lost result with blocked outcome → resume rejected for file effects. Reconcile/resolve observation hash → completed, only one created file | [test_product_creation_result_loss_still_requires_reconciliation](../tests/test_deployment_safety.py#L368) |
| TC-210 | One case, never-claimed isolated helper | Isolated never-started creation plan without record → new content at specified path; not permission to bypass running product-record validation | [test_never_started_isolated_plan_helper_contract](../tests/test_deployment_safety.py#L385) |

### test_package_followup.py — Packaging and trust

Monkeypatch isolates environment; temporary paths exercise trust/symlinks/scanning/copying. Use package_checks/public distribution copy and synthetic personal-data fixtures. The final case copies locally, but does not npm-pack, install, build, publish or test networking. It does not guarantee detection of every real secret.

| ID | Input/variant | Expected assertions | Source function |
|---|---|---|---|
| TC-211–215 | configured=None, empty string, two spaces, commas/spaces only, root slash; five combinations | Absent/empty/root trusted settings → no implicit trusted root. Explicit registered workspace still resolves; edits remain extended/approval-required/unapproved | [test_no_implicit_trust_preserves_registered_workspace_and_approval](../tests/test_package_followup.py#L18) |
| TC-216 | One case: duplicate/unregistered roots, root slash, external symlink | Explicit trust deduplicates/excludes root slash; only registered root trusted. Unregistered root/internal symlink to it blocked and path resolution rejected | [test_explicit_trust_never_grants_unregistered_access](../tests/test_package_followup.py#L34) |
| TC-217 | One case | Remove both workspace-registration settings but set trust → blocked; default selection requires explicit workspace root | [test_trust_alone_cannot_replace_workspace_registration](../tests/test_package_followup.py#L52) |
| TC-218 | One case: six detected/six permitted examples | Detect two Path.home personal defaults, one shortened-home document and three relative set_home personal defaults. Permit author/copyright names, explicit trusted-path placeholder, two set_home placeholders and standard Library path. No blanket name ban | [test_privacy_scan_detects_defaults_without_blacklisting_author_names](../tests/test_package_followup.py#L61) |
| TC-219 | One case: text and NUL-containing binary | Same synthetic personal path in text/binary → personal report lists text filename only, empty secret report; no matching value or binary filename printed | [test_privacy_reports_keep_matching_values_out_of_output](../tests/test_package_followup.py#L85) |
| TC-220 | One case: missing/included link target, missing required/private files | A relative target existing in checkout but absent from manifest → unpackaged-link error; inclusion fixes it. Permit web links/internal anchors; missing build helper/sessions path each error | [test_manifest_requires_packaged_link_targets_even_if_they_exist_in_checkout](../tests/test_package_followup.py#L96) |
| TC-221 | One actual temporary copy | Copy public manifest → no package_errors; build helper/catalog/conftest included; package.json files has no three broad docs patterns | [test_public_distribution_has_build_helper_and_resolvable_documentation](../tests/test_package_followup.py#L113) |

### OPS-DEPLOY-01 documentation handoff

The historical catalog update statically checked 27 files and 172 functions, including 37 newly documented functions. Its associated isolated run recorded 233 passed with one upstream warning. These figures describe that earlier snapshot; real Discord/model acceptance was outside its automated cases.

### test_model_stdin.py — Stdin waiting found during real-model checks

| Case | Input | Assertions | Function |
|---|---|---|---|
| TC-222–223 | Open parent writer with empty data or controller-liveness bytes | Actual Python child gets immediate stdin EOF and exits; argument prompt retained, parent-pipe bytes unconsumed. Failed at two-second bound before DEVNULL, passed after; no real Codex call | [test_model_stdin_eof_preserves_open_controller_pipe](../tests/test_model_stdin.py#L16) |

### test_workspace_intake.py — Admission records found during real Discord acceptance

| ID | Input/condition | Expected result | Implementation |
|---|---|---|---|
| TC-224–227 | auto/gemini/codex/codex_write owner lacks registration; another owner and allowed roots exist | Record blocked/prerequisite_failed; zero operations/executions/workers | [test_missing_owner_workspace_records_block_without_submission](../tests/test_workspace_intake.py#L62) |
| TC-228–233 | workspace/submission × ValueError/OSError/RuntimeError | Reply/store safe exception type only; no private details in replies/records/output | [test_generic_prerequisite_failure_records_only_safe_diagnostic](../tests/test_workspace_intake.py#L81) |

The full candidate-host run including intake follow-up recorded 233 passed and one upstream warning.

### test_publication_privacy.py — Public distribution boundaries

| ID | Input/condition | Expected result | Implementation |
|---|---|---|---|
| TC-234–271 | 38 PRIVATE_PATHS variants: nested instructions/env/private config/keys/DB backups/reports | Even explicit manifest entries fail before installation-destination creation | [test_private_manifest_rejected_before_any_copy](../tests/test_publication_privacy.py#L69) |
| TC-272–309 | Same 38 private paths inserted into package file list | Path-based package errors without reading content | [test_package_audit_rejects_same_private_paths_without_reading_them](../tests/test_publication_privacy.py#L80) |
| TC-310 | Public env example/config/launchd templates/product HTML/source/design docs | Required public files copy and pass package audit | [test_required_public_templates_copy_and_pass_package_audit](../tests/test_publication_privacy.py#L89) |
| TC-311 | Python isolated mode; checker without PYTHONPATH | Standalone checker succeeds, creates empty result reports | [test_package_checker_runs_standalone_without_pythonpath](../tests/test_publication_privacy.py#L101) |

2026-09-13 publication-boundary follow-up: 311 passed and one upstream warning. The preceding 233-case evidence is the earlier stage; 78 path/install/package regressions were added.

### CI dependency-boundary follow-up — 2026-09-17

Preserve existing TC IDs. Two dependency paths were added to PRIVATE_PATHS, increasing each copy/package parameter set from 38 to 40.

| ID | Input/condition | Expected result | Implementation |
|---|---|---|---|
| TC-312–313 | Root/nested node_modules explicitly in install manifest | Reject copy before destination creation | [Installation boundary tests](../tests/test_publication_privacy.py) |
| TC-314–315 | Same dependency paths in npm file list | Forbidden-path error before reading files | [Package boundary tests](../tests/test_publication_privacy.py) |
| TC-316 | Root/nested dependencies in new repo without global/system Git config/local excludes | Shared .gitignore excludes them from untracked public candidates | [Git exclusion regressions](../tests/test_publication_privacy.py) |
| TC-317–318 | Force-stage root/nested dependency files lacking personal-data patterns with git add -f | Actual verify_release.sh reports forbidden tracked paths and fails | [Release-gate regressions](../tests/test_publication_privacy.py) |

Run Git and the Bash release gate in temporary repositories. Distinguish untracked installed node_modules from files admitted to Git. Do not relax privacy scanning or skip tracked dependencies unconditionally.

Recorded full follow-up: `PYTHONPATH=src .venv/bin/python -m pytest -q tests` → **318 passed**, one upstream Starlette warning. Ruff and full release/privacy/package checks also passed.

### Query, cancellation and notice regressions

Earlier TC IDs/counts describe their historical stage. Later files follow; verify total execution counts from the current checkout’s pytest collection.

| File | Inputs and coverage |
|---|---|
| [test_workflow_dispatch.py](../tests/test_workflow_dispatch.py) | Korean queries/cancellation, quoting/negation/invalid commands, owner/conversation selections, stale lists, FakeClient control without model/task creation, held retry with prior results |
| [test_workflow_lifecycle.py](../tests/test_workflow_lifecycle.py) | Dismiss preserved failures, repeated cancellation/lost evidence, atomic status/timestamps, revoke/expiry/approval propagation, reject active reconciliation, resolve exact execution, exclude instructions/backups/reports |
| [test_workflow_notifications.py](../tests/test_workflow_notifications.py) | Receipt rechecks/undelivered retries, no control-record reimport on restart, revoke/approval/result races, nonexecuting API reads, actual temporary subprocess cancellation and periodic expiry |

Use temporary DB/files and fake Discord clients; only subprocess cancellation runs test-only local processes. Automated results are not proof of user Discord sends, real models or operating-file changes.

## Added work-memory and graph-removal tests

- [Dashboard memory review](../tests/test_dashboard_memory_review.py): remove external scripts/graph APIs; preserve project/request/task views and candidate approval/rejection.
- [Dashboard work memory](../tests/test_dashboard_work_records.py): authentication, owner/workspace scopes, bounded lists, rejection of cross-scope forgetting, retained task ledgers and explicit missing-workspace errors.
- [Completed-work memory](../tests/test_work_memory.py): successful-result transactions, duplicate/stale claims, sensitivity/byte/count limits, project/owner/workspace isolation, reset/current-input boundaries, apply provenance and parent projects.
- [LLM Wiki](../tests/test_wiki_store.py): successful-source topics, conflicts/selected revisions/stale review, channel/project/reset/late-result isolation, forgetting across recall, current source/journal rechecks, optional-note errors/sensitive/oversized notes, old topics, unchanged provider-call counts/file scope.
- [Dashboard Wiki](../tests/test_dashboard_wiki.py): authenticated reads/review, Origin/explicit scopes, stale-review rejection, retained ledgers/results/approvals after forgetting, UI escaping/async scope revisions and nonexecuting HTML for malformed dates.

Historical totals remain historical; final pytest results determine totals after removals/additions. Memory uses bounded lexical search. Topic-Wiki tests do not establish complete semantic recall, model training or agy-session deletion acceptance. See [Wiki implementation and limits](llm_wiki.md).
