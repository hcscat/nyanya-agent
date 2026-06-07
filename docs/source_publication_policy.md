# Public and Private Source Policy

Date: 2026-06-07

This document separates the NyaNya Agent codebase into material that is safe to publish and material that must remain private.

## Summary

NyaNya Agent can publish its generic agent wrapper, bridge, routing, packaging, and documentation code. It must not publish local credentials, account identifiers, private conversations, downloaded attachments, OAuth caches, generated runtime logs, or machine-specific workspace mappings.

The line is simple:

- Publish reusable logic.
- Keep instance-specific operational data private.
- Keep anything that grants access private.
- Keep anything that exposes a user's private files, messages, accounts, or machine layout private.

## Public Source

| Area | Files | Why public |
|---|---|---|
| CLI core | `src/nyanya_agent/core.py` | Contains generic provider selection, prompt dispatch, backend checks, transcript save logic, and terminal CLI behavior. It does not need real tokens or user IDs. |
| Bridge compatibility layer | `src/nyanya_agent/bridge_common.py` | Re-exports helper modules for stable imports. No private runtime data. |
| Bridge constants and routing keywords | `src/nyanya_agent/bridge_constants.py` | Contains static command names and keyword lists. These are behavior definitions, not secrets. |
| Workspace and command policy helpers | `src/nyanya_agent/bridge_policy.py` | Contains generic path-boundary checks, protected path checks, owner-key normalization, and help text. Public review improves safety. |
| Runtime delegation helpers | `src/nyanya_agent/bridge_runtime.py` | Contains generic Codex delegation, resource report, executable lookup, and routing heuristics. Safe if it only reads configuration from environment variables. |
| Conversation and queue logic | `src/nyanya_agent/bridge_store.py` | Contains in-memory task queue, cancellation, workspace assignment loading, and conversation trimming. It stores no shipped private data. |
| Discord and Telegram bridges | `src/nyanya_agent/discord_bridge.py`, `src/nyanya_agent/telegram_bridge.py` | Contain generic bot connection code. Tokens, channel IDs, user IDs, and attachment paths are runtime configuration and must stay outside source. |
| Config templates | `.env.example`, `.env.sample`, `config/nyanya.json`, `config/user_workspaces.example.json` | Show names, defaults, and structure without real credentials or private IDs. |
| Packaging | `pyproject.toml`, `package.json`, `bin/*.js`, `scripts/*.sh` | Allows installation, local execution, npm wrapper use, and LaunchAgent setup. Generated local plist files are private, but reusable scripts are public. |
| Documentation | `README.md`, `docs/*.md`, `docs/*.html` | Explains architecture, security model, setup, and decision records. Must avoid secrets and private logs. |

## Conditionally Public

| Area | Default decision | Condition |
|---|---|---|
| System prompts | Public template only | `prompts/system.md` is safe while it stays generic. A production prompt containing private policy, customer names, private paths, account IDs, or operational secrets must be private. |
| MCP integration definitions | Public interface, private credentials | Tool names, schemas, and generic client code can be public. OAuth tokens, API keys, local endpoint secrets, and account-specific server configs stay private. |
| Skills and plugins | Public when reusable | Generic `SKILL.md`, plugin manifests, and reusable adapters can be public. Personal workflow instructions, private business logic, licensed proprietary prompts, and generated session traces stay private. |
| App connector logic | Public adapter, private account state | Code that calls an app connector can be public. Connector tokens, refresh tokens, browser cookies, workspace IDs, and user-owned document IDs are private unless intentionally documented as examples. |
| LaunchAgent templates | Public script, private generated file | `scripts/install_discord_launch_agent.sh` can be public. Generated plist files may contain absolute local paths and should not be committed. |

## Private Material

Never publish these:

- `.env` and any `.env.*` containing real values.
- `NYANYA_DISCORD_BOT_TOKEN`, `NYANYA_TELEGRAM_BOT_TOKEN`, OpenAI-compatible API keys, OAuth tokens, refresh tokens, browser cookies, or credential caches.
- Real Discord user IDs, owner IDs, guild IDs, channel IDs, bot tokens, invite secrets, or Telegram chat/user IDs unless intentionally converted into non-sensitive examples.
- `config/user_workspaces.json`, because it maps real messenger users to local filesystem paths.
- `sessions/`, `logs/`, `downloads/`, `run/`, `tmp/`, and generated transcripts.
- `.gitignore`, if it contains local-only privacy patterns. Use `.git/info/exclude` for local ignore rules instead.
- Discord or Telegram attachments downloaded from private channels.
- Local model, CLI, MCP, or app connector caches under the user's home directory.
- Private prompts that reveal internal operating policy, customer data, or personal automation rules.
- Any generated HTML/report/document derived from private conversations or private files unless deliberately redacted.

## Why This Split Works

The public repo should let another developer understand and run the agent skeleton:

1. how a request enters through Discord or Telegram,
2. how the request is checked against allowed workspace roots,
3. how the agent chooses direct backend response versus Codex delegation,
4. how cancellation and queueing work,
5. how the project is installed and configured.

The private local install should hold everything that makes the skeleton act as a specific user's assistant:

1. credentials,
2. account bindings,
3. channel permissions,
4. workspace mappings,
5. private files and message history,
6. local OAuth/app state.

This lets the code be useful publicly without giving outsiders access to the user's Discord server, local Mac, Google/Antigravity account, Codex session state, or private workspace contents.

## Publication Checklist

Run these before publishing:

```bash
git status --short
python3 -m py_compile src/nyanya_agent/*.py
npm pack --dry-run
rg -n "<token, api-key, private-id, and local-path patterns>" . -g '!.git/**' -S
```

Expected result: compile and npm dry-run pass, and the sensitive search returns no real secrets or private IDs.
