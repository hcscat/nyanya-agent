# Public and Private Source Policy

Date: 2026-06-14

This document separates the NyaNya Agent codebase into material that is safe to publish and material that must remain private.

## Summary

NyaNya Agent can publish its generic agent wrapper, bridge, routing, dashboard, packaging, and documentation code. It must not publish local credentials, account identifiers, private conversations, downloaded attachments, OAuth caches, generated runtime logs, dashboard databases, or machine-specific workspace mappings.

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
| Dashboard store and API | `src/nyanya_agent/dashboard_store.py`, `src/nyanya_agent/dashboard_api.py` | Contain generic SQLite schema, request lifecycle recording, usage aggregation, project phase checks, and FastAPI routes. Public review improves correctness and safety. |
| Dashboard static UI | `src/nyanya_agent/dashboard_static/*` | Contains generic local dashboard HTML/CSS/JS. It must not include real request records, private channel IDs, or private user names. |
| Config templates | `.env.example`, `.env.sample`, `config/nyanya.json`, `config/user_workspaces.example.json` | Show names, defaults, and structure without real credentials or private IDs. |
| Packaging | `pyproject.toml`, `package.json`, `bin/*.js`, `scripts/*.sh` | Allows installation, local execution, npm wrapper use, and LaunchAgent setup. Generated local plist files are private, but reusable scripts are public. |
| Documentation | `README.md`, `docs/*.md`, `docs/*.html` | Explains architecture, security model, setup, and decision records. Must avoid secrets and private logs. |
| Project ignore rules | `.gitignore` | A generic project-level `.gitignore` is public when it excludes common private runtime paths. Machine-only ignore rules still belong in `.git/info/exclude`. |

## Conditionally Public

| Area | Default decision | Condition |
|---|---|---|
| System prompts | Public template only | `prompts/system.md` is safe while it stays generic. A production prompt containing private policy, customer names, private paths, account IDs, or operational secrets must be private. |
| MCP integration definitions | Public interface, private credentials | Tool names, schemas, and generic client code can be public. OAuth tokens, API keys, local endpoint secrets, and account-specific server configs stay private. |
| Skills and plugins | Public when reusable | Generic `SKILL.md`, plugin manifests, and reusable adapters can be public. Personal workflow instructions, private business logic, licensed proprietary prompts, and generated session traces stay private. |
| App connector logic | Public adapter, private account state | Code that calls an app connector can be public. Connector tokens, refresh tokens, browser cookies, workspace IDs, and user-owned document IDs are private unless intentionally documented as examples. |
| LaunchAgent templates | Public script, private generated file | `scripts/install_discord_launch_agent.sh` can be public. Generated plist files may contain absolute local paths and should not be committed. |
| Dashboard external access guide | Public when generalized | Security recommendations, Tailscale/Cloudflare/KT router concepts, and localhost defaults are public. Real router credentials, public IPs, DNS zones, and access policies are private. |

## Private Material

Never publish these:

- `.env` and any `.env.*` containing real values.
- `NYANYA_DISCORD_BOT_TOKEN`, `NYANYA_TELEGRAM_BOT_TOKEN`, OpenAI-compatible API keys, OAuth tokens, refresh tokens, browser cookies, or credential caches.
- Real Discord user IDs, owner IDs, guild IDs, channel IDs, bot tokens, invite secrets, or Telegram chat/user IDs unless intentionally converted into non-sensitive examples.
- `config/user_workspaces.json`, because it maps real messenger users to local filesystem paths.
- `data/nyanya_dashboard.db`, SQLite WAL/shm files, request ledgers, dashboard exports, or any DB backup derived from real Discord usage.
- `sessions/`, `logs/`, `downloads/`, `run/`, `tmp/`, and generated transcripts.
- `.gitignore`, only if it contains local-only privacy patterns. Keep generic project ignores public and put machine-specific rules in `.git/info/exclude`.
- Discord or Telegram attachments downloaded from private channels.
- Local model, CLI, MCP, or app connector caches under the user's home directory.
- Private prompts that reveal internal operating policy, customer data, or personal automation rules.
- Any generated HTML/report/document derived from private conversations or private files unless deliberately redacted.

## Keep Private As Personal Identity

Publishing every reusable mechanism is not the same as publishing the whole operating identity. These are good candidates to keep private or publish only as redacted examples:

| Material | Recommended handling | Reason |
|---|---|---|
| Production system prompt variants | Private | They can reveal personal operating style, safety boundaries, workflow preferences, and account-specific assumptions. |
| Real routing keyword tuning from private usage | Private or summarized | Fine-tuned command heuristics can encode personal workflow and private project patterns. |
| User workspace mappings | Private | They bind messenger identities to local project paths. |
| Dashboard DB and request history | Private | It contains real prompts, results, timing, failures, model choices, and usage patterns. |
| Phase check messages generated for real projects | Private unless redacted | They can reveal roadmap, priorities, and unfinished work. |
| External access deployment details | Private | Router state, DNS names, tunnel IDs, access policies, and public IPs materially affect security. |
| Portfolio screenshots with real data | Redact first | Dashboard screenshots can leak prompts, channels, model usage, or project names. |
| Local automation shortcuts that are uniquely personal | Consider private | Small helper scripts can be the user's differentiating workflow layer even when the core engine is public. |

The recommended public posture is: publish the reusable engine and architecture; keep the live operating data, prompt tuning, dashboard records, and access topology private.

## Why This Split Works

The public repo should let another developer understand and run the agent skeleton:

1. how a request enters through Discord or Telegram,
2. how the request is checked against allowed workspace roots,
3. how the agent chooses direct backend response versus Codex delegation,
4. how cancellation and queueing work,
5. how request observability and project phase checks work,
6. how the project is installed and configured.

The private local install should hold everything that makes the skeleton act as a specific user's assistant:

1. credentials,
2. account bindings,
3. channel permissions,
4. workspace mappings,
5. private files and message history,
6. dashboard request/usage history,
7. local OAuth/app state.

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

For the current dashboard-enabled repo, also verify:

```bash
git ls-files data logs downloads sessions run .env config/user_workspaces.json
git diff --cached | rg -n "<token, private-id, public-ip, local-db patterns>" || true
```

Expected result: no runtime DB, logs, downloads, sessions, run files, `.env`, or real user workspace mapping files are staged.
