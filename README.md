# NyaNya Agent

NyaNya Agent is a lightweight Python-first local agent wrapper with optional Discord, Telegram, and local dashboard components.

It is designed for a small personal or team workspace:

- run a configured LLM backend from the terminal,
- receive requests from Discord or Telegram,
- route complex file/code work to Codex CLI when enabled,
- record Discord-requested work in a local SQLite dashboard,
- keep secrets in local `.env`,
- restrict file work to configured workspace roots.

Repository:

```text
https://github.com/hcscat/nyanya-agent.git
```

## Status

This repository is an independent lightweight project. It does not vendor or copy another agent project's source tree.

The current implementation is intentionally small:

```text
src/nyanya_agent/core.py              # CLI and backend providers
src/nyanya_agent/bridge_common.py     # compatibility exports for bridge helpers
src/nyanya_agent/bridge_constants.py  # command names and routing keyword tables
src/nyanya_agent/bridge_policy.py     # workspace, command, and safety policy helpers
src/nyanya_agent/bridge_runtime.py    # Codex delegation and runtime helpers
src/nyanya_agent/bridge_store.py      # conversation store and per-user task queue
src/nyanya_agent/dashboard_store.py   # SQLite dashboard/event store
src/nyanya_agent/dashboard_api.py     # FastAPI dashboard server
src/nyanya_agent/discord_bridge.py    # Discord bridge
src/nyanya_agent/telegram_bridge.py   # Telegram bridge
```

## Install From Git

```bash
git clone https://github.com/hcscat/nyanya-agent.git
cd nyanya-agent
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[bots,dashboard]"
cp .env.example .env
```

Edit `.env` and configure only the values you need.

## Run

Terminal check:

```bash
./scripts/check_backend.sh
```

Interactive CLI:

```bash
./scripts/run_nyanya.sh
```

One-shot prompt:

```bash
./scripts/run_nyanya.sh --prompt "현재 설정을 한 문장으로 요약해줘."
```

Discord bridge:

```bash
./scripts/run_discord_bridge.sh
```

Dashboard:

```bash
./scripts/run_dashboard.sh
```

macOS service manager:

```bash
./scripts/nyanya_ctl.sh preflight
./scripts/nyanya_ctl.sh auth
./scripts/nyanya_ctl.sh check
./scripts/nyanya_ctl.sh health
./scripts/nyanya_ctl.sh deep-health
./scripts/nyanya_ctl.sh smoke
./scripts/nyanya_ctl.sh restart
./scripts/nyanya_ctl.sh restart-all
./scripts/nyanya_ctl.sh status
./scripts/nyanya_ctl.sh status-all
```

The Discord bridge is the runtime entry point for NyaNya Agent. The dashboard is a separate local observability process that reads the same SQLite ledger. Codex remains a separate recovery and delegation channel: NyaNya may call Codex CLI for delegated work, but `start-all`, `restart-all`, `health`, and `repair` do not embed or manage Codex as part of the agent process. Use `codex-status`, `codex-start`, `codex-install`, and `codex-uninstall` for Codex app lifecycle checks.

Local dashboard URL:

```text
http://127.0.0.1:8765
```

## Configuration

Runtime configuration is loaded from `.env`.

Important variables:

```text
NYANYA_PROVIDER=gemini_cli
NYANYA_GEMINI_CLI=gemini
NYANYA_WORKSPACE_ROOTS=/absolute/workspace/path
NYANYA_SYSTEM_PROMPT_PATH=prompts/system.md
NYANYA_DISCORD_BOT_TOKEN=
NYANYA_DISCORD_PREFIX=!nyanya
NYANYA_DISCORD_RESPOND_IN_ALLOWED_CHANNELS=false
NYANYA_DISCORD_ALLOWED_CHANNEL_IDS=
NYANYA_CODEX_ENABLED=false
NYANYA_CODEX_WRITE_ENABLED=false
NYANYA_DASHBOARD_HOST=127.0.0.1
NYANYA_DASHBOARD_PORT=8765
NYANYA_DASHBOARD_DB_PATH=data/nyanya_dashboard.db
```

Do not commit `.env`. Use `.env.example` as the public template.

By default, the Discord bridge responds to explicit prefix or mention calls. Set `NYANYA_DISCORD_RESPOND_IN_ALLOWED_CHANNELS=true` only if every message in the allowed channels should be treated as an agent request.

## NPM Wrapper

The project is Python-based, but it includes an npm wrapper for easier sharing:

```bash
npm install -g @hcscat/nyanya-agent
nyanya-agent --help
```

The npm package does not replace Python. It launches `python3` with the bundled `src/` package on `PYTHONPATH`.

This works well for distribution when the target machine already has Python 3.11+ installed. For a fully self-contained desktop-style installer, use PyInstaller, Briefcase, uv standalone scripts, or a platform-specific installer instead.

## Security Model

NyaNya Agent is not a sandbox by itself. It is a router and policy layer.

Core guardrails:

- allowed workspace roots,
- protected delete paths,
- per-user task queue,
- SQLite audit/request ledger,
- local `.env` secrets,
- optional Codex sandbox settings.

Keep workspace roots narrow. Do not run public bots with broad filesystem access.

## Documentation

- [Copyright review](docs/copyright_review.md)
- [Public and private source policy](docs/source_publication_policy.md)
- [Discord bot rename guide](docs/discord_bot_rename_guide.md)
- [Operations guide](docs/operations_guide.md)
- [External dashboard access guide](docs/external_dashboard_access.md)
- [Why many agents use TypeScript](docs/typescript_agent_ecosystem.html)
- [CLI session agent development cycle](docs/cli_session_agent_development_cycle.html)
