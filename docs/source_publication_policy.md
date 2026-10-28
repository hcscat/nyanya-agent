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
| Documentation | Reviewed README, `SECURITY.md` and durable `docs` Markdown | Reusable architecture, setup and security policy can be public. Local operational evidence, private AI instructions and generated reports stay private. The sanitized root `AGENTS.md` has the specific Git exception described below. |
| Project ignore rules | `.gitignore` | A generic project-level `.gitignore` is public when it excludes common private runtime paths. Machine-only ignore rules still belong in `.git/info/exclude`. |

## Conditionally Public

| Area | Default decision | Condition |
|---|---|---|
| System prompts | Public template only | `prompts/system.md` is safe while it stays generic. A production prompt containing private policy, customer names, private paths, account IDs, or operational secrets must be private. |
| MCP integration definitions | Public interface, private credentials | Tool names, schemas, and generic client code can be public. OAuth tokens, API keys, local endpoint secrets, and account-specific server configs stay private. |
| Skills and plugins | Public when reusable | Generic `SKILL.md`, plugin manifests, and reusable adapters can be public. Personal workflow instructions, private business logic, licensed proprietary prompts, and generated session traces stay private. |
| App connector logic | Public adapter, private account state | Code that calls an app connector can be public. Connector tokens, refresh tokens, browser cookies, workspace IDs, and user-owned document IDs are private unless intentionally documented as examples. |
| LaunchAgent templates | Public script, private generated file | The manager service CLI, `scripts/nyanya_ctl.sh` and `packaging/launchd` templates can be public. Generated plist files may contain absolute local paths and should not be committed. |
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

## Commit Identity And Historical Cleanup

Use the GitHub-provided noreply address for both author and committer identity. Check the effective identities before committing; repository settings can override global settings, and another device needs its own verification. Changing the Git email setting does not remove the identity from earlier commits.

Historical cleanup requires explicit authorization, private backups and a separate rewrite clone. Inspect every branch/tag and preserve ordinary code, commit dates and parent relationships where possible. A privacy rewrite changes commit IDs and invalidates old signatures. Keep the old-to-new mapping private when it can lead back to sensitive objects. Prefer a fresh clone after cleanup; do not merge or push old clones, worktrees, backup refs or tool-only refs into the cleaned repository.

GitHub PR references, cached commits, Actions metadata/logs and release assets are separate disclosure surfaces. Audit them as well as Git objects. A clean branch scan does not prove that GitHub-only references or third-party copies are purged. Keep visibility private until outstanding removal and publication review are resolved.

Official guidance: [Removing sensitive data](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).

## Installed Dependency Boundary

Keep `node_modules/` out of Git and release assets, including nested copies. Commit `package.json` and `package-lock.json`; CI recreates dependencies with `npm ci`. The shared `.gitignore` must provide this exclusion without relying on a developer's global excludes or local `.git/info/exclude`.

Ignore rules do not remove already tracked files. The release denylist must also reject dependency files added with `git add --force`, even when their contents contain no recognizable secret. Package and source-copy checks independently reject dependency paths selected by an overbroad manifest.

A path reported by the worktree privacy scan is not evidence that it was pushed: the scan includes public untracked candidates as well as tracked files. Check the Git index, outgoing history, and package file list separately when investigating.

## Portable AGENTS Privacy Policy

All project instruction files are local-only by default. This repository's operator has explicitly approved the sanitized root `AGENTS.md` for this GitHub publication so reviewers can use its contributor and Code Review Rules sections. That is the sole Git exception: never copy private operating instructions into it or publish nested/override copies. Further publication of changed instructions still needs file-specific authorization; this approval does not authorize another file, action, runtime package or provider transfer.

The release gate permits the exact repository-root `AGENTS.md` in Git while continuing to reject nested AGENTS and all overrides. It does not establish human approval or sanitize the guide automatically. Review its complete text and outgoing history before publication. npm package checks and source installers independently exclude every AGENTS file, including the public root guide. `SECURITY.md` is ordinary public policy and is included in the distribution.

The shared ignore rules have no blanket root exception. Keep private working guidance local and publish reusable policy only after review. Preserve existing local content and keep any private preimage outside the public repository.

Project `AGENTS.md` and `AGENTS.override.md`, including nested copies, are local working instructions. They must not enter staging, commits, pushes, packages or external publishing without the operator explicitly requesting that file for that specific action. General commit, push or deployment requests are not exceptions.

Every project root `.gitignore` must contain these shared patterns:

```gitignore
AGENTS.md
AGENTS.override.md
```

Unlike a machine's global excludes or `.git/info/exclude`, a committed project `.gitignore` travels with a clone. Ignore rules do not remove already tracked files or old history and do not determine npm package contents. Check all three separately. Do not delete local instructions or rewrite history as an automatic remedy.

### Setting up another device or environment

1. Obtain the project's reviewed source and confirm its `.gitignore` has the rules above. This step requires the rules to have been committed and transferred first.
2. For Codex, open the global `AGENTS.md` in the directory specified by `CODEX_HOME`; when unset, use `.codex` under the current user's home directory. This convention does not require a machine-specific username and applies on macOS/Linux/Windows.
3. Merge the copyable policy below into that file, preserving other instructions. For another AI tool, use its documented global instruction mechanism instead.
4. Confirm the tool loads the policy and check the default root and nested rules with `git check-ignore --no-index AGENTS.md nested/AGENTS.md AGENTS.override.md nested/AGENTS.override.md`. `--no-index` also shows the matching rule for an explicitly tracked public guide; it does not untrack or protect that file. Audit staged files, outgoing history and release contents too; ignore rules cannot protect a force-added or already tracked instruction file. A clone alone does not install global AI instructions or synchronize credentials.

Copyable global policy (contains no local project contents):

```text
Keep all project AGENTS.md and AGENTS.override.md files local-only by default.
Add those exact slash-free patterns to every project's shared .gitignore.
Commit, push, package or publish them only when the user explicitly requests
that file for that specific action; general release requests are insufficient.
Keep real credentials, workspace maps, private prompts, logs, databases, backups
and operational reports local. Share only sanitized templates and reusable logic.
Preserve existing instructions and user changes. Check tracked files, outgoing
commits and package contents separately. Do not automatically rewrite history.
Reapply this policy through the AI tool's global instruction mechanism on each
new device. Do not claim remote devices are configured without verification.
```

The actual global instructions and private project instructions are not part of the distributed product. No remote installation or account synchronization is implied.

## Documentation Placement

A file being optional for installation does not make it private. Tests, safety contracts and design rationale help reviewers assess code and maintain the product. Keep the following boundaries separate:

| Material | Preferred location | Reason |
|---|---|---|
| Current installation, operations and execution contracts | Stable Markdown filenames in Git | Versioned with the matching code and available offline to developers and AI |
| Durable design decisions | Short decision records in Git, with ID/date | Preserve rationale without duplicating the whole project state each session |
| Work request, alternatives, progress and review discussion | GitHub Issue / Pull Request | Link discussion and acceptance evidence to the actual change |
| Published version summary | GitHub Release notes | Describe user-visible changes for a tagged version |
| Long-form user guide with independent editing | Optional GitHub Wiki | Convenient web editing, but code/doc version alignment needs separate discipline |
| Local paths, identities, live deployment results, raw tokens/logs | Ignored private files | GitHub Issues, PRs and Wiki are also external disclosure channels |

Common nonprivate guides use the development checkout as their editing source and are mirrored byte-identically into the operating workspace. Do not separate wording merely because one copy ships publicly. Actual settings, local identities and deployment evidence remain in operating `OPERATIONS.md` / `docs/private`; inspect content before transferring a document. Public docs use English as the canonical language. Derived `<document>.ko.md` translations stay under the operating docs only and are updated with their English counterparts.

Keep each paragraph/list item on one physical line without arbitrary width wrapping, preserving hierarchy, tables, fenced code and explicit hard breaks. Update current contracts and the docs index during related work. A concise development timeline distinguishes completed, verified and deferred features; dated evidence stays historical rather than becoming a second current-state declaration.

Keep reusable P0/core/architecture records for now; their date alone is not a privacy finding. The instance-specific `operational_rollout_20260913.md` stays local and is excluded from the package. For future work, update stable documents and use Issue/PR summaries instead of creating full dated snapshots each session. Moving existing records to GitHub is a separate external action; no migration or publication is performed by this policy change.

GitHub capabilities reviewed against official documentation: [Issues](https://docs.github.com/en/issues/tracking-your-work-with-issues/learning-about-issues/about-issues), [Pull requests](https://docs.github.com/en/pull-requests/get-started/about-pull-requests), [Wikis](https://docs.github.com/en/communities/documenting-your-project-with-wikis/about-wikis), [Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases). Git exclusion semantics: [gitignore](https://git-scm.com/docs/gitignore).
