# Development Status and Remaining Work

The source version is `0.3.0`. This document separates implemented contracts, historical validation and deferred work. Git review publication does not deploy an operating instance or publish an npm release.

## PR 2 review correction

The task-list classifier now accepts complete negative rerun/resume qualifiers while holding mixed-effect requests for clarification. `tests/test_workflow_dispatch.py` covers classification, unchanged tasks/approvals, owner/conversation selection fences and synthetic Discord intake without model submission. This is a source correction; live connector acceptance and operating deployment remain separate. The dated review below is historical evidence, not the current PR validation result.

Complete existing-file safety clauses may also start with `읽거나` ("read or"), for example `기존 파일을 읽거나 수정하거나 삭제하지 마`. The classifier removes that constraint only for intent recognition and preserves the full original request at intake. The existing inline-input guard recognizes the coordinated read ban and skips workspace traversal and reads; an explicitly negated quotation still permits a separately requested read. Quoted/incomplete clauses and mixed task-cancellation commands still require clarification. Regression coverage reproduces the previously blocked new-file request through classification and service intake without mutating a held task, and denies filesystem calls for read-ban requests.

Ordinary Codex review identified four additional corrections: destination-scoped automatic reminders/receipts, preserved Discord task-list aliases and admin checks, bounded agent-limit detection that leaves technical timeout questions as work, and safe blocked outcomes for unavailable upload workspaces. Focused regressions cover periodic and completion notices, parent/child origin inheritance, cross-channel/connector/owner separation, alias permissions, model intake and upload confirmation without effects. These are source contracts and synthetic test evidence, not an installed-service security certification.

A follow-up review also identified that generic “all/remove” wording could cancel an unrelated saved task selection. Cancellation now requires a complete task/previous-list target; file targets, mixed clauses and interrogative shortcuts cannot mutate the selection. Regression tests retain a valid queued selection before the non-task request and verify unchanged tasks/approvals through the service and authenticated API.

## Public review guidance

The reviewed root `AGENTS.md` now supplies contributor instructions and three scoped code-review rules; `SECURITY.md` supplies the threat model, security invariants, finding criteria and reporting policy. The Git release check permits only the explicitly approved root guide; nested/override instructions remain blocked, and npm/source-install checks still exclude all AGENTS files. `SECURITY.md` is included as public distribution policy. These files do not enable automatic reviews, private vulnerability reporting or a security scanner, and do not establish operational deployment or a completed security scan.

## Dashboard installation follow-up

Normal CLI setup and the Bash/PowerShell installers now provision a private dashboard token before service admission, preserving configured credentials on reruns. Authentication and Host/Origin checks remain unchanged. [Token provisioning](installation_and_distribution.md#dashboard-token-provisioning) describes behavior and recovery. Regression coverage is in `tests/test_dashboard_token_setup.py` and the source-installer integration test; Windows CI additionally exercises the native ACL and PowerShell installer. A source fix and automated checks do not establish operational installation or live Discord acceptance.

## Managed service-log correction

Raw log accounting skips a closed segment retired concurrently after enumeration. Missing current streams and unsafe-file failures still fail closed. Deterministic startup and runtime budget-rescan regressions preserve the wrapped service output and exit status. Source/CI evidence remains separate from operating acceptance.


Release-preparation follow-up: the isolated candidate includes safety-clause intake, snapshot availability/public env examples, shared API profiles, memory recall opt-out and Discord ingress claims. An earlier isolated candidate completed 1089 tests and the Node/package checks before the current document-upload change; those are historical results, not validation of this follow-up.

The current upload implementation locally inspects supported UTF-8/BOM UTF-16/CP949 text and bounded text-only DOCX/XLSX/PPTX, then requires exact original-actor/channel/file/hash/destination confirmation when personal-information patterns are found. Credentials cannot be overridden. PDF/image/OCR, legacy Office, ordinary archives, encrypted or incompletely inspected content remain unsupported and held; no parser/OCR download or model call is added. The cap is the smaller of 8 MiB and the destination SDK guild limit, with missing metadata held. Explicit ordinary folder names are relaxed only for uploads; model-context private-path exclusions remain unchanged.

Each review branch must report focused/full tests and package/build results for its exact snapshot. Historical integrated-candidate counts do not validate a separated branch. Operating installation, real Discord delivery, service restart, real model acceptance and release publication require separate verification.

## Current implementation

| Area | Implemented behavior | Boundaries and remaining work |
|---|---|---|
| Request processing | Terminal, Discord and authenticated API → OperationService → data-only OperationSpec → atomic claim by a separate worker | Two independent requests by default, configurable concurrency of 1–4; no decomposition of one request into multiple agents |
| Model routing | Flash assessment first; importance and impact below 4 with complexity 3–4 select Luna XHigh; importance or impact ≥4, or complexity 5, selects Sol High | Lower complexity uses Flash; `astra` is a compatible Sol alias; no automatic model discovery or switching |
| File operations | Bounded snapshots of registered workspaces, exclusive new-file creation, immutable existing-file plans with owner/hash/expiry/preimage approval and journals | POSIX UTF-8 regular-file editing; arbitrary shell/test execution, binary editing and directory moves/deletion are not connected to normal intake |
| Document upload | Local whole-document extraction within bounds; counts-only personal-information report and original-actor/channel/file/hash/destination-bound confirmation, TTL 300 seconds and one send attempt | Supported text and text-only OOXML only; credentials and uninspectable content held; at most 8 MiB subject to SDK guild metadata; zero patterns is not a safety guarantee and uncertain delivery is never auto-retried |
| Duplicate approval | Approval and apply admission share one BEGIN IMMEDIATE transaction; reuse the child for the same plan/hash | Conflicting legacy children remain held rather than being deleted or selected automatically |
| Queries, cancellation and recovery | Owner-scoped tasks/why/cancel/dismiss, conversation selection revisions, interruption holds and explicit resume/reconcile/resolve | Queries and cancellation do not create model tasks; uncertain effects are never replayed automatically |
| Conversation continuity | Existing request/result ledgers are linked by owner, channel/thread, workspace, project and explicit reset | Eight recent turns plus four relevant older turns within 24 KiB; no idle reset; not collection of every ordinary chat message |
| Completed-work memory | Successful task/attempt excerpts in schema v8 with current evidence checks | A 90-day search window, separate from ledger retention; no extra model call |
| LLM Wiki | Topics, sources, revisions and conflicts in schema v9; dashboard search, selection, rejection and source forgetting | At most three notes from the same result call, recall at most five/8 KiB; historical model claims rather than verified current facts |
| Memory controls | current-only/reset/no-store/forget checked across conversation, work memory, Wiki, related legacy candidates and export | Restricts derived-memory reuse; preserves original requests/results, approvals, journals, recovery ledgers and backups |
| Dashboard | Authenticated project/task/attempt/memory views, common five-item pages without nested vertical scrolling, status-count execution popups, original-request/attempt-result previews, consistent typography, right-aligned phase-check badges with attention findings/time, memory-area guidance and task-based approval waits; five-second execution-event polling | Local paging of bounded loaded windows, not unlimited DB history; office is monitoring, projects do not auto-develop, legacy candidate approvals do not feed normal model context |
| Log management | Reduced heartbeat audit, closed-month gzip, verified pruning of old housekeeping and managed log rotation | Preserve workflow/approval/delivery evidence; retain SQLite; no automatic VACUUM or encryption |
| Installation and distribution | Python runtime / TypeScript CLI, separated operating/development state, public-file and package checks | Operating installation, Git publication and npm publication are separate; not acceptance proof for every platform |

The [execution implementation](local_control_plane_implementation.md), [operations guide](operations_guide.md), [LLM Wiki guide](llm_wiki.md) and [security guide](security_and_reliability.md) describe actual functions, commands and limits. Orca, memory/technology graphs, replaced bridge paths and old LaunchAgent shells were removed. The scoped command coordinator, single-use approval/lease contracts and CLI request builders remain intentional isolated test components and are not connected to normal intake.

## Verification levels

| Evidence | Observed result | Limit |
|---|---|---|
| Historical full source checks | Dashboard follow-up on 2026-10-13: 961 passed, one external Starlette/AnyIO warning | Full suite execution of that working candidate; earlier 948/957-case results remain historical, not a coverage percentage |
| Historical test inventory | 55 files, 470 test functions, 961 parameterized cases | Distinguish collected cases from coverage; see the [current file table](test_catalog.md#current-complete-test-files) |
| Dashboard follow-up | Synthetic browser checks of all menus at four widths, natural list height, two-line previews, modal paging/detail/back/Escape; authenticated API binds results to each attempt; phase checks create no tasks/executions | Browser fixture/isolated API evidence rather than autonomous project development or new model acceptance |
| Operating dashboard UX acceptance | Five selected source files installed, dashboard-only restart, authenticated original-request/attempt-result reads and five-item popup checks | No schema/configuration/credential change; preserved work evidence; no new provider request or public publication |
| Operating installation | Schema v9 candidate/selected files verified; Discord, dashboard and memory worker restarted | Local installation rather than a public release; actual settings, DB and evidence remain private |
| Direct Discord acceptance | Basic answers, channel follow-up, restart recall, reset/current-only, question/answer, new files, exact approved application and duplicate approval with one child/journal | Only the requests actually tested; not proof for every failure condition or arbitrary tool execution |
| Direct memory/dashboard acceptance | Topic conflicts/selection/source forgetting, inactive-summary clearing, no-store exclusion from recall/export, authentication and Host/Origin rejection, ordinary reload | Other sources and ledgers preserved; not secure erasure of DB pages, backups or provider conversations |
| Remote access | Host/Origin and authentication boundaries checked for an approved private-network HTTPS proxy in front of loopback | Actual addresses stay in private operating documentation; public hosting/Funnel deferred |

Operating rollback must preserve newer rows and provenance, storage-refusal and forgetting filters. Older code being able to read v9 does not establish safe rollback. Never overwrite a DB containing newer requests with an old whole-DB snapshot. Documentation synchronization is neither a runtime code change nor a new live acceptance test.

## Current disposition of REV-01–03

| ID | Correction | Existing regression evidence |
|---|---|---|
| REV-01 | Wait distinguishes old saved results from the current attempt and immediately reports a held retry | `test_wait_reports_blocked_retry_when_only_prior_result_exists` in [test_workflow_dispatch.py](../tests/test_workflow_dispatch.py) |
| REV-02 | Check size during execution and after exit; read at most 4 MB+1 through a no-follow regular-file handle; hold oversize, linked and abnormal files | Oversize output, immediately-after-exit, symlink/hardlink/FIFO and file-growth cases in [test_provider_limits.py](../tests/test_provider_limits.py) |
| REV-03 | Exclude AGENTS variants, nested instructions and backup/report/private paths from snapshots and file plans | Synthetic collection/application rejection in [test_context_security.py](../tests/test_context_security.py) and [test_workflow_lifecycle.py](../tests/test_workflow_lifecycle.py) |

All three corrections have regression coverage. Real private documents were not sent to models for testing. This does not guarantee automatic detection of every sensitive document or provide an OS sandbox.

## Remaining and deferred work

| Item | Missing capability | Status |
|---|---|---|
| DELIVERY-01 | Common connector inbox, durable destinations, outbox/receipts and recovery across intake/submission or send/record crashes | Recorded Discord message identities already have atomic duplicate suppression; recording-disabled mode uses a bounded process-local cache. Common delivery recovery remains incomplete; current result/send claims do not guarantee restart-safe or exactly-once delivery. See [delivery boundaries](security_and_reliability.md#delivery-controls-and-lifecycle). |
| Requests statistics | Include terminal/API/some connector requests without legacy envelopes | Partially incomplete; `request_read_model` is based on legacy `agent_requests` |
| Telegram parity | Common owner/conversation boundaries and natural-language control classification | Compatibility retained; separate review required |
| Provider sessions | Exact-ID ownership, safe resume/reset and monthly reuse/close/delete | Unimplemented/deferred; do not arbitrarily reuse or delete hidden history/DBs |
| Platform/failure acceptance | Repeated installation/restore, actual concurrency, interrupted recovery and delivery-failure testing | Additional scope requires the next authorized task |
| Multi-agent/DAG/resource and cost scheduling | Decomposition, dependencies, merge and resource allocation for one request | Architecture expansion; recommendation only |
| Automatic model switching/self-improvement/deployment | Model discovery/change and automatic source modification/installation | Deferred by the operator |
| External DB/encryption/public hosting | PostgreSQL/Supabase, DB selection/installers, encryption and public hosting | Deferred by the operator; retain SQLite+gzip |
| GitHub Wiki/Release Notes/npm publication | External publication after version/tag/change selection | Separate from LLM Wiki and outside this task |

Further development waits for the operator's next scope and priority decision. Do not put completed conversation continuity, Wiki or operating installation back on the unfinished list.

## Development timeline

| Stage | Main changes | How to interpret the evidence |
|---|---|---|
| 2026-08–09 design/stabilization | Local Control Plane direction, ledgers, tasks/attempts, approval and recovery | [August diagnosis](architecture_diagnostic_20260826.md) and [CORE-STAB-01](core_stabilization_20260910.md) are historical |
| Four integration batches | Batch 1 privacy/design; batch 2 storage/execution/approval/recovery; batch 3 interfaces/dashboard; batch 4 installation/checks/docs | Then 89 files, +10,394/-991 lines and five commits including a lint correction; not the latest diff or completion percentage |
| 2026-09 environment/publication separation | Operating root/development checkout, separate state/dependencies and independent repository after history cleaning | Original/operating evidence is local-only; old remote checks do not prove current remote state |
| 2026-09–10 control/security/efficiency | Cancellation misclassification, repeated reminders, output/upload, authentication and audit/log fixes | Current operations/security guides take precedence |
| 2026-10-07–11 conversations and simplification | Channel conversations/work memory, old paths/graphs removed, isolated contracts preserved and duplicate approval fixed | Reuse v7/v8 relations and ledgers; old idle/terminal-history descriptions no longer apply |
| 2026-10-11–12 Wiki/live acceptance | v9, topics/sources/conflicts/forgetting/no-store, installation and Discord/dashboard acceptance | Current status/verification table and Wiki guide take precedence |
| 2026-10-12 documentation | Common docs/READMEs synchronized, current/historical/deferred distinctions, paragraph-based line breaks and English/Korean editions | No runtime code or release-version change |
| 2026-10-13 dashboard UX | Status-count popups, readable original requests/results, natural list heights and consistent phase/memory text | Read-only attempt context; no schema or model workflow expansion |
| 2026-10-12 dashboard lists | Shared five-item pages, responsive full-width panels, phase-check findings and current approval-wait visibility | Static UI changes and isolated tests; no new DB schema, autonomous workflow or public release |

Dates identify the baseline of a record. Update current contracts under stable document names and preserve detailed operating evidence privately. Read old counts, commits and conclusions as facts about their original point in time.
