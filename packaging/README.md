# NyaNya Agent Packaging

This directory contains install, uninstall, release-verification, Homebrew, and LaunchAgent packaging assets.

The packaging policy is:

- Keep runtime source files in the repository root, `src/`, `bin/`, `scripts/`, and `prompts/`.
- Keep installer and release assets under `packaging/`.
- Never package local runtime secrets or generated state such as `.env`, `data/`, `logs/`, `run/`, `downloads/`, `.venv/`, or `docs/private/`.
- Prefer a single user-facing `nyanya` command for setup and runtime access.
- Keep `nyanyactl` available for current compatibility until service management is folded into `nyanya service ...`.

## Layout

```text
packaging/
  install/
    install.sh
    install.ps1
    uninstall.sh
    uninstall.ps1
  homebrew/
    Formula/
      nyanya-agent.rb.template
  launchd/
    com.hcs.nyanya.agent.plist.template
    com.hcs.nyanya.dashboard.plist.template
    com.hcs.nyanya.memory-worker.plist.template
  release/
    package-allowlist.txt
    package-denylist.txt
    verify_release.sh
```

## Current Install Target

The first packaging target separates immutable code from mutable per-user state:

```text
code: ~/.local/lib/nyanya-agent
commands: ~/.local/bin/nyanya, ~/.local/bin/nyanya-agent, ~/.local/bin/nyanyactl
macOS state: ~/Library/Application Support/NyaNya Agent
Linux state: ${XDG_DATA_HOME:-~/.local/share}/nyanya-agent
Windows state: %LOCALAPPDATA%\NyaNya Agent
```

The installer does not overwrite an existing `.env`. Uninstall removes code and commands but preserves state unless the explicit purge option is used.

## Current Distribution Plan

The current distribution plan is documented in:

```text
docs/nyanya_install_distribution_final_plan_20260707.md
```

The short version:

- Keep the agent runtime, dashboard API, and messenger bridges in Python.
- Move the npm installer/CLI layer to TypeScript, compiled to JavaScript for npm `bin` entrypoints.
- Keep `npm install` lightweight; run full setup through `nyanya setup`.
- Let `nyanya setup` prepare the Python runtime, dependencies, interactive LLM/SNS configuration, dashboard, Discord bridge, memory worker, and optional LaunchAgent services.
- Keep `.env`, `.venv`, SQLite data, logs, downloads, and sessions under `NYANYA_HOME`, outside the npm package directory.
- Do not silently install system prerequisites such as Python, Node.js, or Git. Detect them and provide explicit installation guidance.
- Use an isolated Python runtime for installed deployments.
- Defer Homebrew until the npm setup and publish flow is stable.

## Future Direction

The current application still exposes `nyanyactl`. The intended packaging direction is to move service control into the main `nyanya` command while retaining compatibility wrappers during migration.
