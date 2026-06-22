# NyaNya Agent

NyaNya Agent is a lightweight Python-first local agent wrapper with optional Discord, Telegram, Codex delegation, and a local operations dashboard.

It is designed for a personal or small-team workspace that needs:

- a terminal LLM wrapper,
- Discord or Telegram request intake,
- controlled file and workspace access,
- optional Codex delegation for complex code/file work,
- a local SQLite-backed operations dashboard,
- macOS LaunchAgent service management,
- clear separation between public source code and private runtime data.

Korean guide: [README.KO.md](README.KO.md)

## Project Status

This repository is an independent lightweight project. It is not the official Hermes Agent and does not vendor another agent project's source tree.

The implementation is intentionally small and inspectable:

```text
src/nyanya_agent/core.py              # CLI and backend providers
src/nyanya_agent/bridge_common.py     # compatibility exports for bridge helpers
src/nyanya_agent/bridge_constants.py  # command names and routing keyword tables
src/nyanya_agent/bridge_policy.py     # workspace, command, and safety policy helpers
src/nyanya_agent/bridge_runtime.py    # Codex delegation and runtime helpers
src/nyanya_agent/bridge_store.py      # conversation store and per-user task queue
src/nyanya_agent/dashboard_store.py   # SQLite dashboard/event store
src/nyanya_agent/dashboard_api.py     # FastAPI dashboard server
src/nyanya_agent/memory_worker.py     # background long-term memory candidate worker
src/nyanya_agent/discord_bridge.py    # Discord bridge
src/nyanya_agent/telegram_bridge.py   # Telegram bridge
```

## Install

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
NYANYA_DASHBOARD_RECORDING_ENABLED=true
NYANYA_DASHBOARD_HOST=127.0.0.1
NYANYA_DASHBOARD_PORT=8765
NYANYA_DASHBOARD_DB_PATH=data/nyanya_dashboard.db
NYANYA_MEMORY_RETRIEVAL_ENABLED=true
NYANYA_MEMORY_WORKER_INTERVAL_SECONDS=1800
NYANYA_MEMORY_WORKER_LLM_REFINEMENT=false
```

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
| `!nyanya reset` | Reset the conversation context for the current user/channel. |
| `!nyanya save` | Save the current conversation session when session saving is enabled. |
| `!nyanya resources` | Show local system resource information. |
| `!nyanya tasks` | Show the current user's pending, running, and queued tasks. |
| `!nyanya tasks all` | Show all users' tasks. Admin only. |
| `!nyanya upload <file_path>` | Upload a local workspace file to the current Discord channel. |
| `!nyanya gemini <prompt>` | Send a prompt directly through the configured Google/Gemini-style backend. |
| `!nyanya codex <prompt>` | Delegate review or investigation work to Codex. |
| `!nyanya codex-work <prompt>` | Delegate file/code-changing work to Codex when write delegation is enabled. |
| `!nyanya cancel` | Cancel the current user's queued/running task. |

Long-running task visibility:

- the first reply is an operational plan and current queue state;
- worker start, routing, and backend delegation are sent as progress messages;
- `NYANYA_TASK_PROGRESS_INTERVAL_SECONDS` controls heartbeat updates while a backend or Codex task is still running;
- `NYANYA_TASK_START_DELAY_SECONDS` leaves a short delay before worker execution so the plan reply appears first in chat.

Important work policy:

- file creation, editing, deletion, moves, permission changes, system settings, network settings, installs, deploys, and other external side effects are treated as higher-risk work;
- higher-risk requests return a plan first and require explicit approval before execution;
- work outside trusted roots but still inside allowed roots uses stricter risk scoring;
- web or third-party material that appears to contain hidden prompt-like instructions is treated as untrusted and reported instead of followed.

File upload behavior:

1. Resolve the requested file path relative to the user's workspace.
2. Verify that the path is inside an allowed workspace root.
3. Verify that the target exists and is a file.
4. Upload it as a Discord attachment.
5. Record the upload request in the dashboard ledger when dashboard recording is enabled.

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

The dashboard is split into four screens:

| Screen | Purpose | Main contents |
|---|---|---|
| Main | Current operational state | Total requests, today's requests, running queue, failures, phase confirmations. |
| Projects | Project and phase operation | Project creation, goal entry, phase cards, phase checks. |
| Memory | Long-term memory review | Pending/approved memory candidates, memory graph, technology graph. |
| Stats | Historical analysis | Usage trend, request ledger, audit log. |

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

NyaNya has two memory layers:

| Layer | Purpose | Storage |
|---|---|---|
| Baseline memory | Compact operating facts loaded into the system prompt. | `prompts/agent_memory.md` |
| Dynamic memory | Request-derived candidates that can be reviewed and approved. | SQLite `memory_items` |

Dynamic memory flow:

1. Discord, Telegram, CLI, or dashboard requests are recorded in SQLite.
2. The memory worker scans terminal requests.
3. Rule-based extraction creates `pending` memory candidates.
4. Sensitive content is redacted or skipped.
5. Optional LLM refinement can be enabled for important candidates.
6. The dashboard can approve or reject candidates.
7. Only `approved` and non-sensitive memories are retrieved for future prompts.

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
npm install -g @hcscat/nyanya-agent
nyanya-agent --help
```

The npm package launches `python3` with the bundled `src/` package on `PYTHONPATH`. It does not replace Python.

## Security Model

NyaNya Agent is not a sandbox. It is a routing, policy, and operations layer.

Core guardrails:

- allowed workspace roots,
- trusted workspace roots,
- protected delete paths,
- per-user task queue,
- plan-first approval for higher-risk work,
- SQLite request/audit ledger,
- approved-only memory retrieval,
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

Recommended order for remote access:

1. Keep it local-only when possible.
2. Use Tailscale Serve for private device access.
3. Use Cloudflare Tunnel plus Access for a controlled public hostname.
4. Use raw router port forwarding only with TLS, authentication, and a reverse proxy.

Do not expose the FastAPI dashboard directly to the public internet without authentication.

## Tests

Run unit tests:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
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

- [Copyright review](docs/copyright_review.md)
- [Public and private source policy](docs/source_publication_policy.md)
- [Discord bot rename guide](docs/discord_bot_rename_guide.md)
- [Operations guide](docs/operations_guide.md)
- [External dashboard access guide](docs/external_dashboard_access.md)
- [Why many agents use TypeScript](docs/typescript_agent_ecosystem.html)
- [CLI session agent development cycle](docs/cli_session_agent_development_cycle.html)

## License

MIT
