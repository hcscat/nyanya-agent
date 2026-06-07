# NyaNya Agent

NyaNya Agent is a lightweight Python-first local agent wrapper with optional Discord and Telegram bridges.

It is designed for a small personal or team workspace:

- run a configured LLM backend from the terminal,
- receive requests from Discord or Telegram,
- route complex file/code work to Codex CLI when enabled,
- keep secrets in local `.env`,
- restrict file work to configured workspace roots.

Repository:

```text
https://github.com/hcscat/nyanya-agent.git
```

## Status

This repository is an independent lightweight project. It is not the Nous Research Hermes Agent and does not vendor or copy that project's source tree.

The current implementation is intentionally small:

```text
src/nyanya_agent/core.py              # CLI and backend providers
src/nyanya_agent/bridge_common.py     # queue, routing, workspace policy, Codex delegation
src/nyanya_agent/discord_bridge.py    # Discord bridge
src/nyanya_agent/telegram_bridge.py   # Telegram bridge
```

## Install From Git

```bash
git clone https://github.com/hcscat/nyanya-agent.git
cd nyanya-agent
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[bots]"
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

macOS LaunchAgent for Discord:

```bash
./scripts/install_discord_launch_agent.sh
./scripts/status_launch_agents.sh
```

## Configuration

Runtime configuration is loaded from `.env`.

Important variables:

```text
NYANYA_PROVIDER=gemini_cli
NYANYA_GEMINI_CLI=gemini
NYANYA_WORKSPACE_ROOTS=/absolute/workspace/path
NYANYA_DISCORD_BOT_TOKEN=
NYANYA_DISCORD_RESPOND_IN_ALLOWED_CHANNELS=false
NYANYA_DISCORD_ALLOWED_CHANNEL_IDS=
NYANYA_CODEX_ENABLED=false
NYANYA_CODEX_WRITE_ENABLED=false
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
- local `.env` secrets,
- optional Codex sandbox settings.

Keep workspace roots narrow. Do not run public bots with broad filesystem access.

## Documentation

- [Copyright review](docs/copyright_review.md)
- [Why many agents use TypeScript](docs/typescript_agent_ecosystem.html)
