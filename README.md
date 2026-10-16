# NyaNya Agent

NyaNya Agent is a Python-first **Local Control Plane** for operator-managed
workspaces. Terminal and Discord requests enter a SQLite durable task/execution
ledger before configured providers or Codex are called. The dashboard is a
monitoring-first operational surface.

It is designed for a single-operator workspace that needs:

- a terminal LLM wrapper,
- Discord or Telegram request intake,
- controlled file and workspace access,
- optional Codex delegation for complex code/file work,
- a local SQLite-backed task and execution ledger plus operations dashboard,
- macOS LaunchAgent service management,
- clear separation between public source code and private runtime data.

Korean guide: [README.KO.md](README.KO.md)

Current completion, limitations and verification: [development status](docs/development_status.md).

For a workspace with separate installed and development copies, run Git and
development checks from the `source` checkout. See
[development isolation](docs/installation_and_distribution.md#separate-an-operational-workspace-from-development).

## P0 execution update (2026-09-12)

Normal terminal/Discord requests now use serialized operations and a dedicated
worker with bounded parallelism. Gemini Flash assesses requests and selects a
Flash/Luna/Astra execution profile. Existing-file edits require a concrete reviewed
plan and exact approval hash; interrupted work stays held with queryable reasons.
See the [P0 implementation and command guide](docs/p0_execution_20260912.md) for
supported file operations, recovery commands, model mappings and verification limits.
This is source implementation, not evidence of a deployed Discord service.

## Project Status

This repository is an independent lightweight project. It is not the official Hermes Agent and does not vendor another agent project's source tree.

The current source version is `0.3.0`. Check the published npm version with `npm view @hcscat-dev/nyanya-agent version`.

The implementation is intentionally small and inspectable:

```text
src/nyanya_agent/core.py              # CLI and backend providers
src/nyanya_agent/bridge_common.py     # compatibility exports for bridge helpers
src/nyanya_agent/bridge_constants.py  # command names and routing keyword tables
src/nyanya_agent/bridge_policy.py     # workspace, command, and safety policy helpers
src/nyanya_agent/bridge_runtime.py    # Codex delegation and runtime helpers
src/nyanya_agent/bridge_store.py      # conversation context and durable task service
src/nyanya_agent/task_service.py      # compatibility callback task service
src/nyanya_agent/operation_service.py # normal serialized request/control facade
src/nyanya_agent/operation_worker.py  # dedicated worker and bounded concurrency
src/nyanya_agent/reviewed_changes.py  # immutable file plans, approved apply and journal
src/nyanya_agent/dashboard_store.py   # SQLite dashboard/event store
src/nyanya_agent/execution_store.py   # versioned task/execution/approval ledger
src/nyanya_agent/execution_adapters.py # subprocess, tmux, Codex, and Antigravity adapters
src/nyanya_agent/execution_runtime.py # adapter lifecycle, recovery, and writer-lease coordinator
src/nyanya_agent/dashboard_api.py     # FastAPI dashboard server
src/nyanya_agent/memory_worker.py     # background long-term memory candidate worker
src/nyanya_agent/discord_bridge.py    # Discord bridge
src/nyanya_agent/telegram_bridge.py   # Telegram bridge
```

## npm Install

For normal use, install the CLI with npm, then run `setup` before `doctor`.

```bash
npm install -g @hcscat-dev/nyanya-agent
nyanya setup --all
nyanya doctor
```

`npm install` installs only the Node/TypeScript CLI. `nyanya setup` creates the Python virtual environment and installs Python dependencies such as `discord.py`, `fastapi`, and `uvicorn`. In an interactive terminal it also offers LLM provider and Discord/Telegram setup. For automation, use `nyanya setup --all --non-interactive`.

On macOS, `--all` configures the dashboard, Discord bridge, and memory worker LaunchAgents. If no Discord token exists, only the Discord service is skipped. `postinstall` is intentionally not used because Python may be absent and install-time runtime side effects are difficult to recover.

Package code and mutable user state are separated:

| OS | Default `NYANYA_HOME` |
|---|---|
| macOS | `~/Library/Application Support/NyaNya Agent` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/nyanya-agent` |
| Windows | `%LOCALAPPDATA%\NyaNya Agent` |

The `.env`, `.venv`, SQLite database, logs, and sessions stay under `NYANYA_HOME`, so npm updates do not replace them. Existing source checkouts with a local `.env` keep legacy source-local state for compatibility.

Configuration and state commands:

```bash
nyanya config
nyanya config show
nyanya config validate
nyanya auth
nyanya paths
nyanya state backup
```

Discord and Telegram tokens are optional; their bridges remain disabled until configured. Slack is not included yet.

Service control:

```bash
nyanya service start
nyanya service status
nyanya service stop
nyanya service uninstall
nyanya update
```

`nyanya service stop` stops the NyaNya-managed Discord bridge, dashboard, and memory worker services together. For isolated install tests, set `NYANYA_SERVICE_LABEL_PREFIX` so the test commands control only test services.

Update with `npm update -g @hcscat-dev/nyanya-agent`, then run `nyanya setup --non-interactive`. To uninstall, run `nyanya service uninstall` before `npm uninstall -g @hcscat-dev/nyanya-agent`. Removing the npm package does not purge `NYANYA_HOME`.

If a `0.1.x` install stored a real `.env` or database inside the npm package directory, back it up before updating to `0.2.0`. Releases from `0.2.0` onward provide `nyanya state backup` and `nyanya state migrate`. Existing source-checkout deployments continue using their legacy state directory automatically.

## Source Install

Clone and install the package:

```bash
git clone https://github.com/hcscat/nyanya-agent.git
cd nyanya-agent
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[bots,dashboard]"
cp .env.example .env
```

For development and tests:

```bash
python -m pip install -e ".[bots,dashboard,dev]"
```

Edit `.env` and configure only the values you need. Do not commit `.env`.

## Minimal Configuration

Important environment variables:

```text
NYANYA_PROVIDER=gemini_cli
NYANYA_GEMINI_CLI=gemini
NYANYA_WORKSPACE_ROOTS=/absolute/workspace/path
NYANYA_TRUSTED_WORKSPACE_ROOTS=/absolute/trusted/path
NYANYA_SYSTEM_PROMPT_PATH=prompts/system.md
NYANYA_AGENT_MEMORY_PATH=prompts/agent_memory.md
NYANYA_DISCORD_BOT_TOKEN=
NYANYA_DISCORD_PREFIX=!nyanya
NYANYA_DISCORD_RESPOND_IN_ALLOWED_CHANNELS=false
NYANYA_DISCORD_ALLOWED_CHANNEL_IDS=
NYANYA_DISCORD_ALLOWED_USER_IDS=
NYANYA_DISCORD_FILE_SHARE_CHANNEL_IDS=
NYANYA_DISCORD_FILE_SHARE_CHANNEL_NAMES=
NYANYA_CODEX_ENABLED=false
NYANYA_CODEX_WRITE_ENABLED=false
NYANYA_CODEX_PROFILE=nyanya-readonly
NYANYA_CODEX_WRITE_PROFILE=nyanya-approved-write
NYANYA_ANTIGRAVITY_SANDBOX=true
NYANYA_DASHBOARD_RECORDING_ENABLED=true
NYANYA_DASHBOARD_HOST=127.0.0.1
NYANYA_DASHBOARD_PORT=8765
NYANYA_DASHBOARD_DB_PATH=data/nyanya_dashboard.db
NYANYA_DASHBOARD_CONTROL_TOKEN_FILE=data/dashboard_control.token
NYANYA_MEMORY_RETRIEVAL_ENABLED=true
NYANYA_MEMORY_WORKER_INTERVAL_SECONDS=1800
NYANYA_MEMORY_WORKER_LLM_REFINEMENT=false
```

Set `NYANYA_HOME` in the shell or service environment because it is needed before `.env` can be located. Relative mutable paths resolve from `NYANYA_HOME`; package assets such as the system prompt resolve from the code root.

Keep workspace roots narrow. NyaNya Agent is a router and policy layer, not a sandbox.

Workspace tiers:

- `NYANYA_WORKSPACE_ROOTS` defines the paths the bridge may access.
- `NYANYA_TRUSTED_WORKSPACE_ROOTS` defines the safer subset where routine work is expected.
- Work inside allowed roots but outside trusted roots uses stricter risk handling.

## Run From Terminal

Check backend configuration:

```bash
./scripts/check_backend.sh
```

Start an interactive CLI session:

```bash
./scripts/run_nyanya.sh
```

Run a one-shot prompt:

```bash
./scripts/run_nyanya.sh --prompt "Summarize the current runtime configuration."
```

## Discord Bridge

Start the Discord bridge manually:

```bash
./scripts/run_discord_bridge.sh
```

By default, the bridge responds to explicit prefix or mention calls:

```text
!nyanya status
@nyanya status
```

Set `NYANYA_DISCORD_RESPOND_IN_ALLOWED_CHANNELS=true` only if every message in the allowed channels should be treated as an agent request.

Useful Discord commands:

| Command | Purpose |
|---|---|
| `!nyanya status` | Show bridge runtime status. |
| `!nyanya config` | Show non-secret runtime configuration. |
| `!nyanya reset` | Reset legacy conversation context; normal operations do not consume it yet. |
| `!nyanya save` | Save legacy context when enabled; not external Codex session persistence. |
| `!nyanya resources` | Show local system resource information. |
| `!nyanya tasks` | Show the current user's pending, running, and queued tasks. |
| `!nyanya tasks all` | Show all users' tasks. Admin only. |
| `!nyanya upload <file_path>` | Upload a local workspace file. Outside a configured file-share channel, the file is sent to `NYANYA_DISCORD_FILE_SHARE_CHANNEL_IDS`. |
| `!nyanya upload-cancel <id>` | Cancel a pending document-transfer confirmation; it cannot undo an SDK send that has started. |
| `!nyanya upload-reject <id>` | Reject a pending document-transfer confirmation. |
| `!nyanya upload-approve <id> <sha256>` | Confirm one inspected file and destination as the original requester in the original channel, before its 300-second expiry. |
| `!nyanya gemini <prompt>` | Assess with Flash and execute with the Flash profile. |
| `!nyanya codex <prompt>` | Assess with Flash and execute with the Luna/Codex profile. |
| `!nyanya codex-work <prompt>` | Use Luna/Codex to propose changes; existing-file apply needs exact plan approval. |
| `!nyanya cancel` | Cancel the current user's queued/running task. |

Long-running task visibility:

- intake returns a task ID and planned stages, and a watcher attempts to send the saved result;
- use `tasks`, `why <task-id>`, `recovery`, and `result <task-id>` to inspect work;
- intermediate heartbeat delivery and acknowledgment-before-result ordering are not
  guaranteed by the normal operation path; legacy progress/delay settings do not control it;
- durable delivery retry after restart remains follow-up work.

Important work policy:

- work stays within the registered workspace and uses a bounded disposable snapshot;
- new UTF-8 files may be created exclusively in task directories;
- existing-file edits/deletes require `plan`, optional `plan-file`, then exact
  `approve <plan-id> <plan-hash>`; approval words alone grant no authority;
- arbitrary shell, installs, deployment, permission changes and directory moves
  are not supported operations in the normal file-plan path;
- external text remains untrusted; snapshot filtering and CLI sandbox options
  are not a complete secret detector or host security boundary.

File upload behavior:

1. Resolve the explicitly requested file inside the requester's registered workspace. POSIX no-follow checks cover each path component; only single-link regular files are accepted. Hidden/authentication/session/key paths remain blocked. Ordinary `reports`, `data` and `private` folder names alone do not block an explicit upload; automatic model-context exclusions remain unchanged.
2. Select the configured file-share destination, or the current channel when it is already a file-share channel or no destination is configured. A failed configured-destination lookup holds the upload rather than falling back to an ordinary channel.
3. Require a valid SDK guild file-size limit and destination identity. The effective limit is the smaller of that limit and the app's 8 MiB cap (8,388,608 bytes). Missing/invalid SDK metadata, including a DM without guild metadata, holds the upload.
4. Freeze the bounded original bytes and inspect them locally using Python's standard library. Supported text extensions accept strict UTF-8, BOM-marked UTF-16 or strict CP949. Text-only DOCX/XLSX/PPTX packages require bounded extraction of every XML part and package metadata. No model, OCR, parser download or network extraction is used.
5. Hold PDFs, images/scans, legacy Office files, ordinary archives, encrypted files, executables and unsupported/incompletely extracted content. Office media/images, external relationships and unknown binary parts are also held. Renaming a binary file to a text extension does not authorize it.
6. Detected authentication material is blocked and cannot be overridden by confirmation. Personal-information patterns cover email, Korean mobile phone, resident ID, payment card, labeled bank account/passport/name/address, and local home paths. Reports show kinds and counts, never the matched values. No detected pattern is not a guarantee that a document has no personal data.
7. If patterns are found, hold the transfer and show the approval ID, exact SHA-256, destination, expiry and counts. The original requester must use `upload-approve <id> <sha256>` in the original channel, or reject/cancel it. Generic file-plan `approve` does not approve an upload. At most 16 pending upload confirmations are retained per owner; each confirmation expires after 300 seconds and can authorize only one send attempt.
8. Immediately before sending, recheck the actor, conversation/channel, registered workspace, relative path, file identity, frozen-byte hash and destination guild/channel. A changed file/destination, wrong hash, rejection, cancellation before sending, expiry or reused approval does not authorize another transfer. The sender receives the exact inspected bytes.
9. A send that has started can have an uncertain outcome on cancellation or failure. Do not automatically retry or describe cancellation as proof of non-delivery; inspect the destination first. Upload confirmations reuse the private approval/audit ledger under a separate action, while dashboard recording controls the ordinary request record.

See [security and reliability](docs/security_and_reliability.md#upload-file-boundary) for extraction bounds, pattern limitations and confirmation scope. This upload path transfers files; it does not add PDF/image understanding to the model context.

## Telegram Bridge

Start the Telegram bridge manually:

```bash
./scripts/run_telegram_bridge.sh
```

Configure the Telegram token and allowed chat/user values in `.env` before enabling it.

## Dashboard

Start the dashboard manually:

```bash
./scripts/run_dashboard.sh
```

Default local URL:

```text
http://127.0.0.1:8765
```

The dashboard is split into five screens:

| Screen | Purpose | Main contents |
|---|---|---|
| Main | Current operational state | Total requests, today's requests, running queue, failures, phase confirmations. |
| Agent Office | Execution control-plane observation | Hosts, agents, tasks, executions, approvals, 2D state zones, and authenticated five-second polling. |
| Projects | Project and phase operation | Project creation, goal entry, phase cards, phase checks. |
| Memory | Long-term memory review | Pending/approved memory candidates, memory graph, technology graph. |
| Stats | Historical analysis | Usage trend, request ledger, audit log. |

### Execution ledger and control API

Version `0.3.0` preserves the legacy `agent_requests` contract and adds versioned migrations for:

- `hosts`, `agent_profiles`, `agent_tasks`, and `executions`;
- `execution_projects` and project-scoped `codex_sessions`;
- `runtime_sessions` and append-only `execution_events`;
- `approvals`, `artifacts`, and fenced `writer_leases`.

Normal terminal and Discord requests use `operation_service.py` and a dedicated
worker with stored OperationSpec data. Legacy upload callbacks still use
`task_service.py`. The dashboard is primarily for monitoring and authenticated management.

All `/v1/` data and control APIs, including loopback reads, require `NYANYA_DASHBOARD_CONTROL_TOKEN` or an owner-only token file. Exact Host/Origin checks also apply. Tokens stay out of URLs, HTML, logs and Git; the static shell and health endpoint remain accessible without exposing operational records.

```text
GET  /v1/hosts
GET  /v1/agents
GET  /v1/tasks
GET  /v1/execution-projects
GET  /v1/execution-projects/{id}/codex-sessions
GET  /v1/executions
GET  /v1/approvals
GET  /v1/events
GET  /v1/events/stream
POST /v1/operations
POST /v1/operations/control
POST /v1/approvals/{approval_id}/decision
POST /v1/executions/{execution_id}/cancel
POST /v1/recovery/reconcile
```

File-by-file reviewed apply is implemented for supported POSIX UTF-8 regular files.
Approval binds the owner, immutable plan hash and expiry; file preimages and worker
ownership are rechecked at apply time. Interrupted effects require reconciliation.
`POST /v1/tasks` creates a draft, while `/v1/operations` submits executable work.
See the [P0 contract](docs/p0_execution_20260912.md) for limits and commands.

Execution adapters cover managed subprocesses, tmux, Codex, and Antigravity.
Orca is not in the current default adapter registry or product direction.

Create and restore an online SQLite backup with:

```bash
./scripts/backup_state.sh
NYANYA_RESTORE_CONFIRM=YES ./scripts/restore_state.sh data/backups/<stamp>/nyanya_dashboard.db
```

Stop all NyaNya services before a restore. See [Execution control plane](docs/execution_control_plane.md) for the schema, state model, recovery process, and security boundaries.

The dashboard uses SQLite by default:

```text
data/nyanya_dashboard.db
```

Do not commit the dashboard database, WAL/SHM files, request logs, or generated exports containing private usage data.

## Project and Phase Tracking

Creating a dashboard project calls:

```text
POST /v1/projects
```

The store then:

1. creates a project row,
2. sets the project status to `active`,
3. sets health to `green`,
4. sets the current phase to `planning`,
5. creates four phases: `planning`, `design`, `implementation`, `test`,
6. marks `planning` as `running`,
7. marks the other phases as `waiting`,
8. writes an audit log entry.

Phase checks call:

```text
POST /v1/projects/{project_id}/phases/{phase_key}/check
```

If a phase has a `next_action`, the check result becomes `needs_confirmation` and a Discord confirmation message candidate is produced. If no next action exists, the check result is `ok`.

## Long-Term Memory

The compatibility memory subsystem has two layers. Normal Discord operations do
not yet inject these memories or previous conversation turns. The terminal REPL
embeds a bounded in-process history; this is not durable session continuation.

| Layer | Purpose | Storage |
|---|---|---|
| Baseline memory | Compact operating facts loaded into the system prompt. | `prompts/agent_memory.md` |
| Dynamic memory | Request-derived candidates that can be reviewed and approved. | SQLite `memory_items` |

Dynamic memory flow:

1. Requests with legacy connector envelopes enter the request read model.
2. The memory worker scans completed envelopes; terminal/dashboard/Telegram
   operations without envelopes are not included in this extraction source.
3. Rule-based extraction creates `pending` memory candidates.
4. Sensitive content is redacted or skipped.
5. Optional LLM refinement can be enabled for important candidates.
6. The dashboard can approve or reject candidates.
7. Compatibility retrieval helpers use approved, non-sensitive, owner-scoped
   memories. Connecting them to normal operations remains follow-up work.

Run the worker once:

```bash
./scripts/nyanya_ctl.sh memory-worker-once
```

Manage the background worker:

```bash
./scripts/nyanya_ctl.sh memory-worker-start
./scripts/nyanya_ctl.sh memory-worker-status
./scripts/nyanya_ctl.sh memory-worker-restart
```

## macOS Service Management

NyaNya includes a manager for macOS LaunchAgents.

Install and start services:

```bash
./scripts/nyanya_ctl.sh install
./scripts/nyanya_ctl.sh dashboard-install
./scripts/nyanya_ctl.sh memory-worker-install
./scripts/nyanya_ctl.sh start-all
```

Restart services:

```bash
./scripts/nyanya_ctl.sh restart-all
```

Check service status:

```bash
./scripts/nyanya_ctl.sh status-all
```

Health and smoke checks:

```bash
./scripts/nyanya_ctl.sh health
./scripts/nyanya_ctl.sh dashboard-health
./scripts/nyanya_ctl.sh deep-health
./scripts/nyanya_ctl.sh smoke
```

Codex policy:

- The Discord bridge is the runtime entry point for messenger requests.
- The dashboard is a separate local observability process.
- The memory worker is a separate low-cost maintenance process.
- Codex remains a separate recovery and delegation channel.
- `start-all`, `restart-all`, `health`, and `repair` do not embed or manage Codex as part of the agent process.
- Use `codex-status`, `codex-start`, `codex-install`, and `codex-uninstall` for Codex app lifecycle checks.

## NPM Wrapper

The project is Python-based, but it includes an npm wrapper for easier sharing:

```bash
npm install -g @hcscat-dev/nyanya-agent
nyanya setup --all
nyanya doctor
```

The npm package ships a TypeScript-authored CLI compiled to JavaScript. It does not replace Python; `nyanya setup` prepares the Python runtime and dependencies.

The current install/distribution model is documented in
[Installation and distribution](docs/installation_and_distribution.md). The
Python runtime and TypeScript CLI remain separate layers.

## Security Model

NyaNya Agent is not a sandbox. It is a routing, policy, and operations layer.

Core guardrails:

- allowed workspace roots,
- trusted workspace roots,
- protected delete paths,
- per-user task queue,
- plan-first approval for higher-risk work,
- SQLite request/audit ledger,
- approved-only, owner-scoped compatibility memory retrieval,
- local `.env` secrets,
- optional Codex sandbox settings.

Never publish:

- `.env` or real environment values,
- Discord or Telegram bot tokens,
- OAuth tokens, API keys, browser cookies, credential caches,
- real Discord guild/channel/user IDs,
- `config/user_workspaces.json`,
- `data/`, `logs/`, `downloads/`, `sessions/`, `run/`,
- private prompts, private transcripts, private attachments,
- generated dashboard databases or exports with real request data.

## External Dashboard Access

The safe default is local-only:

```text
NYANYA_DASHBOARD_HOST=127.0.0.1
NYANYA_DASHBOARD_PORT=8765
```

External access and server/database/hosting setup are deferred as of 2026-09-21.
The following choices are reference material for a later authorized task:

1. Keep it local-only when possible.
2. Use Tailscale Serve for private device access.
3. Use Cloudflare Tunnel plus Access for a controlled public hostname.
4. Raw router port forwarding is not an approved deployment mode.

Do not expose the FastAPI dashboard directly to the public internet without authentication.

## Tests

Run unit tests:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q tests
```

Run focused dashboard lint:

```bash
.venv/bin/ruff check src/nyanya_agent tests
```

Check dashboard JavaScript syntax:

```bash
node --check src/nyanya_agent/dashboard_static/app.js
```

Compile Python sources:

```bash
PYTHONPATH=src .venv/bin/python -m py_compile \
  src/nyanya_agent/core.py \
  src/nyanya_agent/bridge_policy.py \
  src/nyanya_agent/bridge_runtime.py \
  src/nyanya_agent/bridge_store.py \
  src/nyanya_agent/dashboard_store.py \
  src/nyanya_agent/memory_worker.py \
  src/nyanya_agent/manager.py \
  src/nyanya_agent/telegram_bridge.py
```

## Documentation

- [Documentation map](docs/README.md)
- [Architecture and roadmap](docs/architecture_and_roadmap.md)
- [Execution control plane](docs/execution_control_plane.md)
- [Canonical operating policy](prompts/policy.md)
- [Installation and distribution](docs/installation_and_distribution.md)
- [Operations guide](docs/operations_guide.md)
- [External dashboard access guide](docs/external_dashboard_access.md)
- [User acceptance tests](docs/user_acceptance_tests_ko.md)
- [Copyright review](docs/copyright_review.md)
- [Public and private source policy](docs/source_publication_policy.md)

## License

MIT
