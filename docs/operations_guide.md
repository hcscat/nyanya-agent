# nyanya-agent Operations Guide

Current source review: [development status](development_status.md).
Use the [P0 contracts](p0_execution_20260912.md) for operation commands,
file approval and held recovery. Historical verification is not current live proof.


This guide covers the local service command used to manage nyanya-agent, its
Discord bridge, and its local dashboard. NyaNya is operated as a Local Control
Plane: the SQLite execution ledger is the source of truth for task and execution
status, while the dashboard is primarily a monitoring and authenticated control
surface.

## Task queries, cancellation and reminders

Operation status comes from the SQLite ledger, not workspace handoff documents. `tasks` or `남은 작업은 무엇인가?` lists the authenticated owner's current work without starting a model or creating another execution task. `why <task-id>` also explains completed and dismissed history. `status` reports local configured limits; it does not contact a provider or prove model readiness.

An explicit list request may include a non-mutation qualifier, for example `미완료 작업 목록만 보여줘. 기존 작업은 변경하거나 취소하지 마.`. It stays in the owner-scoped control path. A mixed request that also asks for cancellation, file work or another effect requires clarification; a negative clause alone does not identify a task to list or cancel.

After listing tasks, `미완료 작업들은 하지 않겠다 취소/제거 해라` acts only on the displayed selection in that conversation, valid for 30 minutes. A changed list requires a fresh list and decision. Use `cancel <task-id>` for an explicit target. Ambiguous or quoted control language asks for clarification.

Cancellation and historical failure are different decisions:

- A failed task can be dismissed with `dismiss <task-id>`; its failure, original request and evidence remain available through `why`.
- A running task remains pending termination. Lost execution or uncertain file effects stay blocked until inspected; repeated cancellation cannot hide them.
- Revoked or expired plans settle the parent and approval state when safe. File reconciliation and hash-bound `resolve` remain explicit actions.

Automatic reminders use current state and record a receipt after successful delivery. An unchanged delivered list is not repeated simply because another request finishes or the service restarts. Saved model results do not contain a new reminder footer. Explicit lists remain available. Concurrent sends or a crash between sending and recording a receipt can still duplicate a notice; durable delivery outbox/retry remains future work. Historical saved responses are retained and may contain old text, so compare them with a fresh `tasks` query.

Background reminders exclude ordinary eligible queued work with a live worker and running/cancelling work with a matching, unexpired claim and live worker heartbeat. They retain held or stale work, failures needing a decision, approval waits and ambiguous connector sends. Explicit task lists still show active work. The existing claim/heartbeat policy defines this distinction; an arbitrary task age does not.

Local AI instructions (including AGENTS variants), backup and report paths are excluded from provider snapshots and file-change proposals. This filename policy does not establish that every permitted workspace file is safe to disclose. Explicit no-file-read or inline-only analysis requests use an empty snapshot without walking or reading workspace files. Coordinated Korean prohibitions such as `파일을 읽거나 수정하지 말고` are also handled before discovery. Prohibiting edits alone still allows requested reads. Name a file, a path such as `src/`, or a folder explicitly when workspace context is needed; a generic language name is not a directory request. Conventional `conda_envs`, `site-packages` and `venv` trees are excluded from snapshots, alongside the existing private/dependency exclusions. Secret screening still applies to user input and selected file contents.

An explicitly named full relative or in-workspace absolute file path is checked before bounded directory discovery. A named folder scopes discovery to that folder; the aggregate 200-directory/4,000-name limit remains. Exact files still obey the 80-file/50 KB context limit, no-follow ancestor checks, private/dependency exclusions, UTF-8 regular-file checks and content screening. Unsafe explicit references do not fall back to reading unrelated overview files. For a nested target in a large workspace, name its full relative path rather than only its basename.

## Ongoing Discord conversations

Ordinary requests receive a short acknowledgement followed by a natural reply. The worker's JSON fields are internal transport data, not a required human answer template. A necessary clarification question completes successfully; it does not become a failed or unfinished task merely because the operator has not answered.

Context is scoped to the authenticated owner, Discord channel/thread and registered workspace. It references existing task prompts and results rather than copying them into another transcript. Idle time no longer resets the channel session. Up to eight recent turns and four earlier turns matching words in the current request are included, within 24 KiB, after sensitive-content screening. Earlier idle generations remain searchable after the last explicit reset; other owners, channels, workspaces and projects are excluded. This is bounded lexical recall, not perfect semantic recall. The separate [LLM Wiki](llm_wiki.md) adds cited topic summaries using the existing result-model call; neither feature adds a DB backend. Oversized or unsafe turns are omitted. Turns in one context generation execute in order; independent conversations may execute concurrently. Explicitly resuming an older turn cannot overlap another running turn in that generation.

History is untrusted context for interpreting follow-up messages. Its saved response, outcome and delivery evidence describe an earlier attempt; the separate current task status describes the live ledger. Prior messages never authorize a new file change, cancel work, change model settings or expand the current file-read scope. A follow-up that needs a file must identify the file or folder again. Approval remains authenticated and bound to the reviewed plan hash; a conversational assent such as "go ahead" does not apply an existing-file modification automatically.

`reset` starts a new conversation context generation without cancelling tasks, revoking plans or deleting history. `save` creates a bounded, screened private conversation export under the configured local session directory. It does not export credentials, provider configuration or a full unlimited transcript. Current-only suppresses history for this request; no-store also excludes its source from later recall/export and derived memory. Source forgetting clears the same source's work/Wiki/linked legacy summaries while preserving original requests/results/approvals/effects/backups. Reset changes the recall boundary and is not task cancellation or secure erasure.

The dashboard Memory view supports topic search, conflict/revision selection, summary rejection and source forgetting. These are memory controls, not file approval; automatic summaries remain historical model claims. The optional legacy LLM refinement stays disabled.

These features provide text dialogue, not voice input, unrestricted shell execution or autonomous self-modification. File proposals and reviewed application remain the supported effect boundary.

## Operation model routing

The current source requests Gemini Flash for initial assessment and low-complexity execution. With importance and impact both below 4, complexity 3–4 selects `luna` (`gpt-6-luna`, `xhigh`). Importance or impact at least 4, or complexity 5, selects `sol` (`gpt-6.1-sol`, `high`). The serialized legacy profile `astra` remains accepted and explicitly aliases that Sol configuration; it does not invoke Astra. Explicit profiles also retain initial Flash assessment.

These fixed source mappings do not prove installation, account access or actual model completion. Failed access stays held without substituting a model. Automatic model discovery, model updates and self-improvement remain deferred. See the [P0 model policy](p0_execution_20260912.md#model-policy) for the full contract.

## Command

Use one management command:

```bash
./scripts/nyanya_ctl.sh status
./scripts/nyanya_ctl.sh status-all
./scripts/nyanya_ctl.sh preflight
./scripts/nyanya_ctl.sh auth
./scripts/nyanya_ctl.sh check
./scripts/nyanya_ctl.sh health
./scripts/nyanya_ctl.sh deep-health
./scripts/nyanya_ctl.sh smoke
./scripts/nyanya_ctl.sh restart
./scripts/nyanya_ctl.sh restart-all
./scripts/nyanya_ctl.sh dashboard-status
./scripts/nyanya_ctl.sh dashboard-health
```

Installed package entrypoints also expose:

```bash
nyanyactl status
nyanyactl status-all
nyanyactl preflight
nyanyactl auth
nyanyactl check
nyanyactl health
nyanyactl deep-health
nyanyactl smoke
nyanyactl restart
nyanyactl restart-all
nyanyactl dashboard-status
nyanyactl dashboard-health
```

## Service Model

The recommended macOS runtime for NyaNya Agent is LaunchAgent, not tmux.

Reason:

- LaunchAgent restarts the Discord bridge and dashboard after crashes.
- It starts automatically after login.
- Newly generated service definitions use the bounded log wrapper described below.
- Older `logs/*.launchd.*.log` files remain untouched until a reviewed deployment.
- It avoids leaving manual terminal or tmux sessions as hidden operational state.

The LaunchAgent labels are:

```text
com.hcs.nyanya.discord
com.hcs.nyanya.dashboard
```

The Discord bridge is the primary connector controller. Normal requests use
OperationService, which persists work and supervises a dedicated on-demand
operation worker process with a bounded thread pool. Terminal and dashboard
operations use the same facade. The worker is not an independent LaunchAgent;
controller shutdown closes its liveness pipe and interrupts its work. Upload
callbacks remain on the compatibility task service.

The dashboard is a separate local observability process. It serves
`http://127.0.0.1:8765` by default and reads/writes `data/nyanya_dashboard.db`.
Use `/v1/execution-projects`, `/v1/execution-projects/{id}/codex-sessions`, and
`/v1/tasks?project_id={id}` for the authoritative project/session/task view.

## Local gzip log retention

SQLite remains the local task ledger. Do not add a PostgreSQL/Supabase backend, installer or DB selection until the operator explicitly reopens that work. Archive encryption is deferred. Compressed archives are private data, not safe publication material and not replacements for consistent SQLite backups.

```bash
nyanya logs status
nyanya logs maintain
nyanya logs maintain --apply
# Python-only installs:
nyanya-logs status
```

Both `status` and `maintain` default to read-only planning. Only `maintain --apply` creates archives or removes eligible verified records. Use `--state-root` and `--db-path` for an explicit installation. The CLI reads only the DB-path setting from the selected environment file; it does not initialize a missing database. The selected database must be inside the selected state root. A stale inherited DB override pointing into another installation is rejected before any maintenance.

The running dashboard checks maintenance at startup and hourly. Audit archives catch up completed KST calendar months missed while the machine was off. Service archives cover only the preceding three completed months; older unarchived service segments remain raw for manual review. Set `NYANYA_LOG_MAINTENANCE_ENABLED=false` to disable this automatic job. Development and test launchers disable it by default. Authenticated `/v1/log-maintenance` shows the latest in-process summary; the CLI computes a fresh plan. The maintenance child has a five-minute deadline and receives no provider or messenger credentials.

- Heartbeats update the latest host timestamp; only registration and meaningful configuration/status changes generate audits.
- Migration 6 indexes the newest-first audit feed. Indexes and source changes need a verified deployment before they benefit an already installed instance.
- Audit archives live under `logs/archive/audit/`, one gzip JSONL file per completed month, with a self-contained manifest, count and checksum. A verified archive is required before pruning records older than 90 days, in short batches capped at 10,000 rows per run. The initial prune allowlist is host registration/update and memory-retrieval observations. All other audit evidence remains pinned.
- Housekeeping-only audit archives expire after 12 months only after their live rows have been pruned. Mixed/pinned-evidence archives are retained as an explicit exception. Task/request/execution events, approvals, changes and delivery records are never pruned by this job. No automatic VACUUM or DB-file replacement occurs.
- New macOS service definitions wrap Discord, dashboard and memory-worker output into private size/day segments. Closed segments are archived by their closing month under `logs/archive/service/`. Raw segments remain for at least 30 days; verified service archives retain three completed calendar months. Active files, legacy launchd logs, unknown files, task output evidence and Codex logs are excluded. Segments roll at 4 MiB or the next write after a KST day boundary. A 128 MiB per-service raw budget stops the managed child with exit 75 rather than discarding unarchived output; `logs/<service>.last-status.json` records the bounded result. Inspect blocked archives before restarting. This is a limit on retained raw output, not a replacement for application-level debug filtering.

Archives are published without overwriting an existing month and checked by decompression/readback before deletion. Corruption, late entries, unsafe paths or size bounds block the affected operation with the original evidence preserved. The audit scan is capped at 500,000 rows/128 MiB, and each monthly audit archive at 100,000 rows/64 MiB of uncompressed JSON. These are implementation safety bounds, not SQLite capacity limits. A limit error requires review rather than blind retries. Late data for an already sealed month requires inspection; do not delete an archive to bypass a conflict. Interrupted service `.pin` or `.retiring` files preserve recovery evidence and require inspection; do not treat them as disposable caches. A monthly archive may contain duplicates of recent live data during the retention overlap. Files use private permissions and are not encrypted.

Automatic archival does not imply an operating deployment. Before activating new service definitions, verify code/DB compatibility, retain a consistent backup and rollback artifact, and review old launchd files separately. Rolling back code does not restore audit records already pruned; recover those from the verified archive with explicit collision checks. Do not replace the live DB with an old backup.

## Codex Separation Policy

### Executable readiness

Management health checks and Discord delegation share `codex_cli.resolve_codex_cli`.
Set `NYANYA_CODEX_CLI` to a verified executable path or command. When unset,
discovery uses `codex` on the service PATH. An explicit invalid setting fails
closed instead of silently selecting another installation. Directories,
non-executable files, and broken symlinks are rejected. Avoid pinning the CLI to
a desktop app's internal bundle path when an independently installed CLI is used.

After changing this setting, restart the Discord bridge to reload its environment.
Verify the selected binary with `--version`, then verify bridge reconnection and
a read-only delegated request. A successful version check alone does not prove
authentication, model/profile compatibility, or end-to-end task completion.

OS launch failures are reported with a sanitized errno and actionable guidance,
not raw local executable/workspace paths. ENOENT means a missing executable,
working directory, or interpreter; EACCES means permission denied; EPERM means
operation not permitted; ENOEXEC means an invalid executable format. These errno
definitions come from the OS/Python standard library, not NyaNya-specific codes.
Permission errors must not trigger automatic privilege elevation.

Codex must remain separate from the NyaNya Agent service lifecycle.

Reason:

- Codex is a separate desktop/CLI recovery channel controlled independently by the user.
- It is useful when Discord, a dashboard, or the NyaNya bridge is unavailable.
- NyaNya may call Codex CLI for delegated work, but it must not embed Codex in the Discord bridge process.
- `start-all`, `restart-all`, `health`, and `repair` manage or validate the NyaNya runtime and dashboard. They do not start or repair Codex as part of the agent lifecycle.

Codex has separate management commands:

```bash
./scripts/nyanya_ctl.sh codex-status
./scripts/nyanya_ctl.sh codex-start
./scripts/nyanya_ctl.sh codex-install
./scripts/nyanya_ctl.sh codex-uninstall
```

The optional Codex LaunchAgent label is:

```text
com.hcs.codex.app
```

## Common Tasks

Check local Discord bridge prerequisites:

```bash
./scripts/nyanya_ctl.sh preflight
```

Check backend and Discord configuration:

```bash
./scripts/nyanya_ctl.sh check
```

Run only the configured backend authentication/connectivity check:

```bash
./scripts/nyanya_ctl.sh auth
```

For OAuth-backed backends, complete the browser consent flow and paste the authorization code into the terminal when the CLI asks for it.

Install and start the Discord bridge:

```bash
./scripts/nyanya_ctl.sh install
```

Start the NyaNya runtime entrypoint and dashboard:

```bash
./scripts/nyanya_ctl.sh start-all
```

Restart after changing `.env`, prompts, or source:

```bash
./scripts/nyanya_ctl.sh restart
```

Restart the NyaNya runtime entrypoint and dashboard:

```bash
./scripts/nyanya_ctl.sh restart-all
```

Show service status:

```bash
./scripts/nyanya_ctl.sh status
./scripts/nyanya_ctl.sh status-all
```

Manage only the dashboard:

```bash
./scripts/nyanya_ctl.sh dashboard-install
./scripts/nyanya_ctl.sh dashboard-start
./scripts/nyanya_ctl.sh dashboard-status
./scripts/nyanya_ctl.sh dashboard-health
./scripts/nyanya_ctl.sh dashboard-restart
./scripts/nyanya_ctl.sh dashboard-stop
```

Run a runtime health check:

```bash
./scripts/nyanya_ctl.sh health
```

Run a deeper health check that also checks the dashboard HTTP endpoint and configured backend:

```bash
./scripts/nyanya_ctl.sh deep-health
```

Run a local no-message smoke check:

```bash
./scripts/nyanya_ctl.sh smoke
```

Try to repair the Discord bridge if health fails:

```bash
./scripts/nyanya_ctl.sh repair
```

Stop the service:

```bash
./scripts/nyanya_ctl.sh stop
```

Remove the service:

```bash
./scripts/nyanya_ctl.sh uninstall
```

Read or change the Discord bot username:

```bash
./scripts/nyanya_ctl.sh bot-name
./scripts/nyanya_ctl.sh bot-name NyaNya
```

The Discord application username, server nickname, and NyaNya command prefix are
separate settings. The command above changes the application username when the
bot token has permission. Change the server nickname in Discord server settings,
and configure `NYANYA_DISCORD_PREFIX` for the command prefix. Restart the bridge
after changing runtime configuration.

## Invocation Behavior

Discord handling is configured for:

- prefix requests through `!nyanya`,
- direct mention requests through `@NyaNya`,
- DM requests without a prefix.

The file-share channel remains quiet for ordinary channel chatter. Explicit prefix or mention requests are still processed.

## Dashboard Behavior

The dashboard records Discord-triggered work in SQLite:

- original request text,
- trigger and command mode,
- provider and model,
- status: received, queued, running, completed, failed, cancelled, ignored,
- start/end/duration,
- token fields when a backend exposes them,
- result summary or error summary,
- request events and audit log.

Current Gemini/Codex CLI paths do not expose stable token accounting, so token fields may be empty. This is intentional; the dashboard does not invent estimates.

The dashboard also includes project phase tracking for:

- planning,
- design,
- implementation,
- test.

Use phase `next_action` and the phase check endpoint/UI to identify work that requires Discord confirmation. The Discord bridge can also run a periodic phase checker when explicitly enabled:

```text
NYANYA_PHASE_CHECK_ENABLED=true
NYANYA_PHASE_CHECK_INTERVAL_SECONDS=21600
NYANYA_DASHBOARD_CONFIRMATION_CHANNEL_ID=<discord_channel_id>
```

The checker is disabled by default to avoid unsolicited Discord messages.

## Private Runtime Files

These files are local-only and must not be committed:

```text
.env
config/user_workspaces.json
prompts/local_system.md
logs/
data/
sessions/
downloads/
run/
```

## CORE-STAB-01 recovery behavior

See [the current stabilization handoff](core_stabilization_20260910.md) before upgrading. Schema v3 is applied on runtime initialization; preserve a verified pre-upgrade backup. No live upgrade was performed by the source change.

Discord `recovery` / `복구` lists held work; `result <task-id>` / `결과 <task-id>` retrieves the caller's persisted result. Reconnect notices are checked every 60 seconds and may wait for lease expiry. Records without a known allowed destination need local review. Notices can repeat across bridge restart; this is not a durable outbox.

Interrupted work is not replayed automatically. Review external processes and side effects before cancelling or making a replacement request. An unresolved claim can hold later owner work; do not edit SQLite to bypass it or assume a cancellation request terminated a process. Dashboard retry returns a conflict until explicit reconciliation is implemented.

The TypeScript state backup command uses SQLite online backup and rejects unsafe destinations/symlinks. Backups are per database/file, not an atomic snapshot of all state. Legacy shell backup/restore helpers use separate path selection; inspect that path and stop writers before a restore. Never restore over a running service.

## Inspected document upload

Explicit file transfer performs bounded local document inspection before Discord transmission. Personal-information patterns require exact one-use owner/hash/destination confirmation; authentication material is blocked. PDF/image and other uninspectable content remain held. See [the upload contract](security_and_reliability.md#upload-file-boundary).

## Memory review controls

Legacy candidate **승인** patches only `memory_items.status` to `approved`; **거부** changes it to `rejected`. Changed status is audited and the candidate's text/source history remains stored. A rejected candidate is excluded from the legacy approved-memory search, but rejection is not source forgetting or secure erasure. Those legacy search/format functions are not called by normal operation-model context, so candidate approval alone does not alter an ordinary Discord response. The **요청 이력에서 후보 추출** button runs bounded, rule-based extraction of eligible successful requests, without an extra model call. Review only useful candidates; there is no requirement to approve every row.

Automatic LLM Wiki summaries are eligible scoped historical context before manual review. **기억 버전 선택** selects a version and supersedes other pending/approved versions of that topic; **요약 거부** excludes that summary; **이 근거 기억 제외** clears and suppresses the same source's derived Wiki/work/linked legacy memory while preserving the original work ledger. Work-record **기억에서 제외** applies the same source boundary. Use review for conflicts/corrections, not as mandatory approval for all automatic memories. See [LLM Wiki](llm_wiki.md) for provenance, no-store and reset limits.

## Scoped completed-work memory

Successful normal operations retain screened request/result excerpts and ledger references in task_work_records. The result model may reuse relevant records from the same owner, workspace and project; this adds no LLM refinement call. The separate legacy candidate worker remains independent. This is a source capability, not proof that an operating instance has been upgraded to schema v8.

Use the dashboard memory tab to select an explicit work-record scope. Forgetting one record clears its excerpts and excludes it from reuse; it does not cancel a task or erase its request, result, approvals or file effects. The authenticated work-record list/forget APIs require the same explicit scope.

NYANYA_WORK_MEMORY_ENABLED=false disables new records and automatic retrieval. A request that explicitly forbids storing memory is not recorded. Current-input-only or explicit history exclusion suppresses both dialogue and completed-work context; a no-files request alone can still use conversational references. Questions are stored as questions but never retrieved as completed knowledge.

Records expire from retrieval after 90 days; workflow evidence is not automatically deleted. An explicit reset excludes earlier work from that same conversation; a simple idle conversation rollover does not prevent next-day work reuse. Other scopes never become visible through a global fallback.

NyaNya does not delete Antigravity CLI/app conversations. Automatic cleanup requires a supported exact-ID operation and proven NyaNya ownership after durable recording. Do not delete provider folders or infer ownership from recency. Codex invocations already use ephemeral sessions.
