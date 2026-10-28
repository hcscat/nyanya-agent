# Security and reliability contracts

These contracts describe the source implementation. Installing a verified artifact, migrating a backed-up ledger, restarting services and exercising real connectors are separate acceptance steps. An unchanged version string is not proof of identical installed code; use the artifact file hashes and source provenance.

## Provider context and subprocesses

Normal operations select context using the request's file paths, directory names, filenames or filename topics before reading contents. Name explicit files or a subdirectory when requesting focused work. A broad request without matching files gets overview documentation instead of the entire workspace. The snapshot retains at most 80 files and 50 KB, with bounded metadata traversal.

Files containing detected credential fields, credential assignments, recognized secret formats or known sensitive environment values are excluded as a whole. Instruction files, runtime state and private paths remain excluded. The original bytes and hashes of accepted files are preserved for subsequent approval checks. Provider prompts receive an additional content check before invocation.

The filter is conservative and incomplete: it may exclude harmless examples and cannot identify every private document or secret format. Keep registered workspaces narrow. Provider children receive OS necessities and only their provider's required authentication variables, not unrelated connector/dashboard tokens or Python injection variables. HOME remains available for CLI authentication files; this is not an OS sandbox or complete credential isolation.

Codex final-result files have the same 4 MB limit as process output. The runner checks during execution and after exit; the reader opens a non-followed, single-link regular file and reads at most the limit plus one byte. Oversized or unsafe results produce a held outcome. Polling can allow temporary growth between checks. The final-file reader requires POSIX no-follow directory/file operations. Unsupported platforms return an explicit held outcome; there is no Windows fallback.

## Dashboard data access

The dashboard uses local scripts only. Memory/technology graphs and the mutable external visualization dependency were removed; project, task and request history and authenticated memory candidate review remain available.

All `/v1/` routes require the dashboard token, including reads from loopback. Unexpected Host headers are rejected. Origin headers must match the request origin or an explicitly configured CORS origin. Localhost, IPv4 loopback and IPv6 loopback are accepted hosts; `NYANYA_DASHBOARD_ALLOWED_HOSTS` adds exact hostnames without ports or wildcards. This does not expose the service to other networks.

The page shell and health endpoint remain available without a token. Unlock the page to read operational data; authentication stays only in page memory and request headers. Development dashboard startup creates a separate owner-only token under its development state directory and never prints it. Production token configuration remains separate. Tokens must not appear in URLs, logs or Git.

Importing the dashboard module or requesting CLI help does not initialize the database or start a server. The ASGI application is created by an explicit factory; the legacy `module:app` entry point initializes lazily when explicitly accessed. Installation probes must still set an isolated working directory, code root, state root, environment-file path and database path for every subprocess.

## Private completed-work records

Schema v8 adds bounded successful task/attempt records inside the existing fenced result transaction. Request/result excerpts are limited to 1 KiB/2 KiB and screened before storage and again before context transfer. Saved model answers are historical conclusions, not verified tests or effects. Applied plans require matching owner, workspace, parent project and applied journal evidence.

Retrieval uses exact owner/workspace/project scope with no global fallback, scans at most 64 recent records and supplies at most 8 KiB only to the result model. The current snapshot and conversation budget take priority; assessment receives no additional work records. Explicit current-input/history exclusion is respected. Questions are not reused as answers. Records expire from retrieval after 90 days; this is not automatic deletion of task evidence or a complete long-term Wiki.

The authenticated operator can list a selected scope or forget a specific record. Forgetting clears private excerpts and prevents their reuse while preserving task, attempt, result, approval and effect history. NYANYA_WORK_MEMORY_ENABLED disables new record storage and automatic retrieval. No extra LLM call or legacy memory refinement is enabled. Provider session deletion requires supported exact-ID operations and proven ownership; never infer that the newest provider session is a disposable NyaNya session.

## Topic memory and privacy controls

Schema v9 adds cited Wiki topic revisions in the existing completion transaction. The existing result-model call returns up to three optional summaries; malformed/sensitive notes do not fail valid work. Owner/channel/workspace/project/reset and current successful source evidence are rechecked at capture, recall and authenticated review. Summaries remain historical claims, not authorization or verified current facts. See [LLM Wiki](llm_wiki.md).

Current-only suppresses present recall. No-store excludes future derived memory and source transfer through recent/lexical conversation recall or private export. Source forgetting clears all same-source work/Wiki/linked legacy text, including superseded/rejected notes, while keeping original tasks/results/approvals/journals and unrelated sources. Legacy extraction/review also checks refusal, forgetting and successful screened provenance atomically. This is not erasure of SQLite pages, backups or provider conversations.

Reviewed file approval and apply admission share one transaction. Exact plan/hash/child relations deduplicate repeat approvals; conflicting older children stay held. Memory selection is never a file approval. Older code reading v9 is not safe rollback proof; preserve current privacy guards and new work rows.

## Delivery, controls and lifecycle

A result sender is bound to a specific task attempt. The ledger atomically claims a pending result before the callback runs. Competing watchers cannot send the same claimed result, and an old watcher cannot follow a resumed attempt. Callback errors are ambiguous delivery, not evidence that no message arrived. Sending/uncertain records remain inspectable and are not automatically replayed. Use `ack-delivery <task-id>` to acknowledge an ambiguous delivery reminder. This records `acknowledged`, not `delivered`, and does not resend, cancel or alter the execution outcome. Task ownership and the current result are checked atomically.

This prevents the reproduced concurrent duplicate-send race. It does not implement a complete delivery outbox or exactly-once network delivery. Discord ingress claims have the scoped limits described below; general delivery guarantees require a separate destination/receipt/retry contract.

Control classification distinguishes explicit code work, such as fixing timeout logic, from requests for execution limits. Quoted, negated or ambiguous cancellation still needs clarification. File-planning requests cannot silently cancel tasks.

Closing a review plan settles the associated approval wait only when claims, children and effect evidence permit it. Older terminal-parent/awaiting-review inconsistencies are reconciled conservatively; lost or uncertain effects stay held and historical events remain intact.

## Upload file boundary

An explicit upload stays inside the authenticated requester's registered workspace. Each path component is opened with POSIX no-follow operations, and the opened target must be a single-link regular file. Symlinks, hardlinks, special files and paths outside the workspace are refused. The reader checks device, inode, size, nanosecond mtime and ctime before/after the bounded read, then freezes the exact original bytes. Inspection and the SDK sender use those same frozen bytes; a later reopen must match both file identity and SHA-256. Unsupported platforms fail explicitly.

Upload path policy is separate from automatic model-context selection. Explicit files under ordinary `reports`, `data`, `private`, `logs`, `run` or `downloads` folders are no longer excluded solely by those names. Hidden paths, authentication/session/instruction/dependency locations and credential/database/log/backup suffixes remain blocked. This relaxation does not change the broader model-context `PRIVATE_PATH_PARTS` exclusions or authorize workspace writes.

The effective transfer cap is the smaller of the destination's SDK `guild.filesize_limit` and 8 MiB (8,388,608 bytes). Missing/invalid SDK limit or guild/channel identity holds the upload; a DM without guild metadata does not bypass it. A configured destination lookup failure holds the transfer instead of falling back to the ordinary request channel. The 8 MiB value is an application-selected per-file resource cap, not a claim about Discord subscription limits. It permits files above the former 2,000,000-byte boundary while keeping input memory bounded; the missing-SDK fallback is to hold rather than guess a server limit.

### Local extraction and detection limits

`upload_document_privacy.py` uses the Python standard library locally, with no network, subprocess, OCR, additional parser installation or document conversion. Explicitly supported text extensions are decoded strictly as UTF-8 (with optional BOM), BOM-marked UTF-16, or CP949; original bytes are retained for transmission. DOCX/XLSX/PPTX support is limited to text-only OOXML packages whose complete XML parts, relationships and package metadata can be inspected within the bounds. It is not general Office rendering or all-file compatibility.

PDFs, images/scans, legacy Office files, ordinary archives, encrypted files, executables, unknown formats and incomplete/failed extraction are held. OOXML images/media, external relationships, missing targets and unknown binary parts are held too. Embedded visual content in supported markup is also held. An extension change cannot make uninspected binary content safe.

The bounds are 8 MiB of input, 256 Office entries, 4 MiB per XML part, 16 MiB total uncompressed Office content, a 100:1 compression ratio, 50,000 XML nodes and depth 64. Unsupported ZIP metadata/compression, duplicate/unsafe member paths and XML entity/DOCTYPE declarations are refused. Classic ZIP records must cover the file without unlisted gaps or unused deflate payload; only stored empty directory entries are supported. Ambiguous XML/HTML attributes and duplicate decoded JSON keys are held. Extraction is additionally bounded to 64 Mi characters of inspection views and 10,000 unique findings per kind, with a cooperative 10-second deadline checked between stages (not a preemptive timeout for a running parser/regex). These conservative checks can reject otherwise usable documents; the reader never silently skips an uninspected part and calls the remainder clean.

The nine pattern kinds are `email`, `phone`, `resident_id`, `payment_card`, `bank_account`, `passport`, `person_name`, `address` and `local_path`. Counts are unique normalized matches per kind, not a count of people or an exhaustive inventory. Phone patterns focus on Korean mobile numbers; bank accounts, passports, names and addresses rely on labels. Card candidates use a Luhn check. Unlabeled names/addresses, unsupported national formats, obfuscation and unknown secret formats can be missed, and harmless examples/metadata can be flagged. A zero count means only that these patterns were not found in the supported extracted representation. It is not a personal-information, malware or DLP safety guarantee.

Detected authentication material remains a hard block and cannot be approved for transfer. Reports/errors do not expose extracted text, matched values, parser diagnostics or document-member names. Inspection failures remain held rather than being described as clean.

### Exact transfer confirmation and delivery

Detected personal-information patterns create a pending confirmation and send no attachment. The original authenticated actor must issue `upload-approve <id> <sha256>` in the original request channel; `upload-reject <id>` and `upload-cancel <id>` close a pending confirmation. Generic file-plan `approve` is separate and cannot authorize an upload. Confirmation permits a specific transfer of already inspected content; it does not waive extraction, credential, path or size checks.

The existing `approvals` table stores the separate action `discord.upload.pii`; the existing audit ledger stores status events. Approval metadata binds actor, conversation/request channel, registered workspace, relative path, device/inode/size/mtime/ctime, exact frozen SHA-256, destination guild/channel and detection counts. It stores scope and counts rather than extracted content or matched personal values. At most 16 pending confirmations are allowed per owner, with a 300-second TTL. Immediately before the SDK call, an atomic pending-to-consumed compare-and-set allows one send attempt. Changed scope/file/destination, wrong hash, rejection, cancellation before sending, expiry or reuse cannot authorize a wrong or additional send.

After an SDK send starts, cancellation or failure can leave delivery uncertain. A consumed confirmation cannot prove non-delivery or authorize an automatic retry; inspect the destination and use a fresh explicit request when appropriate. Fake-client tests do not establish live permissions, rate limits, reconnect behavior, durable outbox delivery or exactly-once network delivery. This file-transfer path makes no model call and does not add PDF/image understanding to provider context.

## Dependency and efficiency policy

The optional security tooling requires urllib3 2.8.0 or later within major version 2. Audit the actual installed dependency set, including development tools. Runtime installations should contain only required runtime extras; a source dependency change does not update an existing operating environment.

Migration 5 adds scoped indexes for workflow delivery notices and control selections. The worker uses lightweight state reads, checks for eligible queued work before claiming, and separates recovery/heartbeat intervals from the short work poll. These changes reduce idle writes and history scans. Measure representative workload latency before making broader performance or throughput claims. Migration 6 adds the newest-first audit index. Repeated heartbeat updates no longer generate audit rows, and memory audits omit query text and edited values.

## Artifact and publication boundaries

Source installation records `artifact-manifest.json` with package version, source commit/dirty state and hashes/modes of selected public files. Verify the artifact before promotion and retain a compatible code/DB rollback pair. The content digest is an integrity check, not a publisher signature. The verifier allows narrowly recognized generated Python bytecode/build metadata; those generated entries are not a privacy scan or executable provenance proof. Generated build copies must match recorded source bytes and retain safe permissions or setuptools' 0644 normalization; recorded source modes are still verified exactly. A dirty source artifact must be reported as such; a commit ID alone does not identify its extra changes.

All project `AGENTS.md` and `AGENTS.override.md` files, including root and nested copies, are local-only by default. A specific file requires the operator's explicit authorization for each staging, commit, push or publication action; a previous approval or general release request is insufficient. Runtime configuration, private reports and credentials stay excluded. Instruction files remain excluded from install packages. See the [publication policy](source_publication_policy.md) and [installation procedure](installation_and_distribution.md).

## Regression coverage

- `test_context_security.py`: request scope, sensitive content, child environments, worker staging and preserved preimages.
- `test_provider_limits.py`: running/final output size, descriptor type, bounded reads and fake CLI output; no real model invocation.
- `test_upload_safety.py`: path-component replacement, links and safe file handles.
- `test_dashboard_read_security.py`: unauthenticated local reads, hostile Host/Origin, authenticated requests, IPv6, explicit CORS configuration, and import/help startup isolation with lazy ASGI compatibility.
- `test_hardening_workflow.py`: duplicate send, attempt ownership, ambiguous callbacks, request classification and review-state settlement.
- `test_worker_efficiency.py`: old-schema upgrade, indexed lookups and idle polling.
- `test_artifact_manifest.py`: artifact contents, provenance and tamper detection.

- `test_apply_admission.py`: thread/process repeat approvals, single child/event and crash rollback.

- `test_conversation_state.py` / `test_conversation_retention.py`: ledger scope/order, reset, late results, older lexical recall and current prompt intake.
- `test_conversation_worker.py` / `test_conversation_dispatch.py`: natural questions, safe follow-ups, controls and screened private export.
- `test_wiki_store.py` / `test_dashboard_wiki.py`: provenance, topic conflicts/revisions, recall limits, forgetting and authenticated review.
- `test_work_memory.py` / `test_memory_store.py`: no-store/forget and legacy successful-source filtering.
Use the checked-in tests for collected counts. Run the full suite and release/privacy gate for code/release changes as well as focused regressions. Documentation-only changes use structural/link/privacy/package verification; they do not require repeating runtime acceptance. Installed health, live model completion, connector delivery and restart recovery need their own evidence; they are not inferred from unit tests.

## Release-candidate boundary corrections

Complete file/settings write prohibitions are kept in the original request while the intake classifier evaluates the remaining question. A remaining ambiguous or mutating control is held for clarification. These constraints do not authorize commands or existing-file changes.

Task-list queries also accept a complete prohibition on rerunning or resuming existing work, including Korean `재실행`, `다시 실행` and `재개` variants. The entire qualifier must match the negative-only grammar; a positive action, trailing instruction or quoted constraint remains held for clarification. These queries use the owner-scoped ledger path without submitting model work, changing task/approval state or applying files. List selection still records the observed task revisions for a later explicit control request.

Selection cancellation requires a complete task or previous-list command; generic quantifiers such as “all” do not authorize cancelling the saved selection. File-target and mixed-effect requests stay outside this mutation path, and interrogative cancellation shorthand remains held. Exact supported cancellation commands, owner checks and observed-list revision fencing still apply.

Automatic recovery reminders and notices appended to successful results are scoped by owner, connector and original request channel, including child operations that inherit their parent's request. Their delivered receipts use the same destination scope; sending one channel's notice does not acknowledge another channel's notice. Tasks without a known connector destination are not included in connector notices. Explicit owner-requested lists remain separate from automatic reminders.

Discord task-list aliases, including `/tasks` and administrator-only `/tasks all`, dispatch before generic control interception without bypassing global-list permissions. Technical questions about source-file or other-system timeouts remain normal work requests; only bounded questions about the agent's own limits use the local runtime-status response. Upload inspection and confirmation turn unavailable-workspace outcomes into blocked request records with a safe response, without scheduling or consuming a transfer.

Snapshot availability distinguishes a verified missing path from private/sensitive filtering, unreadable data, unsupported types/encoding and bounds. Availability metadata uses fixed path/status fields and shares the prompt budget. An excluded or unlisted file is not evidence of absence. Empty public env examples and credential-file references are not embedded credentials; referenced files are never opened by that exception, and credential literals and known secret values remain screened.

The authenticated API and OperationSpec share `auto`, `flash`, `luna`, `sol` and `astra` profile validation. An explicit profile retains the Flash assessment step. Generic requests not to use memory disable conversation, completed-work and Wiki recall together; a request not to store a turn is a separate storage boundary, and reset remains explicit.

Discord claims a recorded source/channel/user/message identity atomically before attachment downloads, task/control mutation or acknowledgement. Duplicate events do not repeat those effects. With dashboard recording disabled, no additional request row, payload or event is stored: an existing receipt is checked with a read-only connection, then a process-local cache retains at most 4096 identities. Restart, multiple bridge processes or oldest-entry eviction can admit duplicates in that mode. SQLite read-only WAL access may involve sidecar files; this is a no-additional-request-record guarantee, not a claim of zero filesystem activity. Claim failures hold execution. A crash after committing the receipt but before task submission leaves a held/orphan receipt: replay is suppressed, so inspect the ledger and submit a new explicit request if needed. Existing uncertain-delivery handling remains conservative; this is not an exactly-once network delivery guarantee.

The document-upload follow-up replaces the temporary UTF-8-only 2,000,000-byte restriction with the bounded local extraction and exact privacy-confirmation contract in [Upload file boundary](#upload-file-boundary). Text-only OOXML and supported UTF-16/CP949 text are eligible; PDF/image and other uninspectable content remain held. The 8 MiB app cap is further limited by the destination SDK metadata. Personal-information counts require scoped one-use confirmation; authentication material remains blocked without an override. Model-context exclusions remain unchanged.

This feature stage requires its focused/full isolated verification before publication. Live connector delivery and installed-service behavior require separate authorized evidence.
