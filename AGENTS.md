# NyaNya Agent — Contributor and Review Guide

This is reviewed public repository guidance. Keep personal instructions, credentials and operating evidence outside this file. Read [README.md](README.md), the [docs index](docs/README.md) and [SECURITY.md](SECURITY.md) before relevant work. Linked documents supply context when read; a link does not automatically load them.

## Working boundaries

- Confirm the repository, branch, PR base/head and `git status --short --branch` before editing. Preserve existing changes and review the actual implementation and callers, not only a diff or an older report.
- This repository contains published source. Python owns the runtime, connectors, SQLite and dashboard; TypeScript owns the npm CLI and installation wrappers. Source changes, successful tests and pushes do not establish operating deployment or live connector acceptance.
- Use independent development dependencies and synthetic state. Before application imports in probe subprocesses, set temporary working directory, code/state roots, environment file and database path. Do not use an operating environment, credentials, DB or service labels for tests. Real model calls, service restarts and external writes require task authorization.
- Reuse existing functions and libraries. Keep fixes small; propose substantial architecture or feature expansion separately. Describe intended scope and verification for substantial changes. Stay on the selected model/reasoning setting unless the user requests a change; delegate only when requested.

## Code Review Rules

### 1. Preserve authenticated, usable installation paths

All dashboard `/v1/` reads and mutations require a control token, an allowed Host and exact validation of any supplied Origin, including loopback requests. Non-browser clients may omit Origin; they still need authentication. Review CLI setup, both alternate installers and development launchers when changing authentication or state paths. Safe path: create missing credentials privately before service startup, preserve existing credentials and verify an authenticated request succeeds while unauthorized requests fail. Health/static success is not proof that operational data can load; do not solve setup failures by weakening authentication.

### 2. Preserve execution identity and effect authorization

Tasks, attempts, claims and approvals are distinct identities. Existing-file effects need an exact authenticated plan approval and current preimage/claim checks at application time. Review retries, concurrency, cancellation and startup recovery for stale results, duplicate effects or lost evidence. Safe path: use existing transactional admission and ownership checks; hold uncertain effects for inspection. Prior dialogue, a PID, model output or a successful execution cannot substitute for approval or confirmed connector delivery.

### 3. Preserve private-data and workspace boundaries

Trace changed ingress, context, subprocess, upload and packaging paths through their consumers. Caller allowlists do not authorize unregistered workspaces or unrelated credentials. Safe path: keep model-visible inputs bounded and screened, treat model/document content as data, recheck file handles and scope before effects, and inspect actual outgoing trees and archives. The only public instruction-file exception is this reviewed repository-root `AGENTS.md` in Git; nested/override instructions remain local, and all AGENTS files stay excluded from runtime packages and source installs.

Prioritize concrete correctness, compatibility and security failures. A finding should identify its trigger, reachable path, consequence and a precise changed location; explain contrary evidence and uncertainty. Check adjacent unchanged callers and fresh-install/upgrade paths when needed. Do not invent findings or treat a passing narrow test as a security certification. Mechanical formatting belongs in CI. Use [SECURITY.md](SECURITY.md) for security-specific assumptions and report criteria; these three rules are additional checks, not the entire review scope.

## Validation and evidence

Prepare development dependencies using the [installation guide](docs/installation_and_distribution.md#development-install). The bounded launcher supports:

```bash
python3 scripts/dev.py test
python3 scripts/dev.py lint
python3 scripts/dev.py typecheck
python3 scripts/dev.py build
node --check src/nyanya_agent/dashboard_static/app.js
bash packaging/release/verify_release.sh
```

On systems exposing Python as `python`, use that executable. Run focused regressions for changed contracts and the full applicable release gates before publication. Report exact revision, commands, outcomes, skipped checks and limitations; distinguish source tests, installed health and live model/connector evidence. Never weaken a gate or silently ignore an advisory to obtain a green check.

## Documentation and publication

- Keep canonical public docs in English and each paragraph/list item on one physical line; preserve intentional Markdown structure. Update the relevant guide, docs index and development status with changed contracts. Keep machine-specific records and translations in the private operating workspace.
- Keep slash-free `AGENTS.md` / `AGENTS.override.md` ignore patterns for local copies. This root file was explicitly authorized for this GitHub publication; further publication of changed instructions still requires file-specific authorization. Do not copy private instructions into it. Git tracking does not authorize npm packaging, provider transfer or sharing other instruction files. See the [publication policy](docs/source_publication_policy.md).
- Stage exact reviewed paths. Preserve existing Git history and verified noreply Author/Committer identities. When Codex materially contributes, add exactly one `Co-authored-by: Codex <codex@openai.com>` trailer; use the existing opt-in hook only if verified, otherwise an explicit commit trailer. Record actual operator/Codex roles in an authorized PR update and keep final human review pending unless confirmed. Do not infer commit/push/merge/deployment authorization from this guide.

## Official guidance

The review section follows OpenAI's [GitHub review rules](https://learn.chatgpt.com/docs/third-party/github#customize-what-codex-reviews) and [concise, scoped rule guidance](https://developers.openai.com/blog/custom-code-review-rules-for-codex). Build commands belong here; the threat model belongs in `SECURITY.md`. These files guide review and do not activate paid scans, change account settings, enforce OS isolation or replace tests, branch protection and human approval.
