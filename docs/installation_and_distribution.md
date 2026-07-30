# Installation and Distribution

## Supported installation model

NyaNya Agent uses a TypeScript CLI and a Python runtime:

1. npm installs the compiled CLI.
2. `nyanya setup` finds Python, creates an isolated environment, installs runtime
   dependencies, creates private state directories, and offers connector setup.
3. `nyanya doctor` validates configuration, dependencies, permissions, services,
   and local health.

```bash
npm install -g @hcscat-dev/nyanya-agent
nyanya setup --all
nyanya doctor
```

The npm install step has no service side effects. Interactive credentials and
macOS approvals belong to `nyanya setup`, not `postinstall`.

## Runtime and state separation

Published package files are immutable application code. Mutable state lives under
`NYANYA_HOME`, including:

- the managed Python environment;
- local configuration and secrets;
- SQLite state;
- logs, sessions, downloads, and run files.

Package upgrades must preserve `NYANYA_HOME`. Uninstall removes services and
package code only unless the operator separately requests state deletion.

## Configuration workflow

Initial setup may configure:

- an LLM provider through OAuth, CLI discovery, or an API key;
- Discord or Telegram credentials and allowlists;
- workspace roots and trusted roots;
- dashboard, memory worker, and macOS LaunchAgents.

Validation is part of setup and every configuration change. A diagnostic command
may expose validation results, but users should not need a separate syntax-only
step during normal operation.

Secrets must be entered locally, masked in output, written with owner-only
permissions, and excluded from package and Git contents.

## Updates and removal

```bash
npm update -g @hcscat-dev/nyanya-agent
nyanya setup --non-interactive
nyanya doctor

nyanya service uninstall
npm uninstall -g @hcscat-dev/nyanya-agent
```

Homebrew, curl, and PowerShell installers may be provided as alternate delivery
channels, but they must preserve the same state, validation, and removal contract.

## Development install

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[bots,dashboard,dev]"
npm ci
npm run build
```

## Release gate

A release must pass:

- Python tests and lint;
- TypeScript build and JavaScript syntax checks;
- dependency and security audits;
- release verification and package allowlist checks;
- source, Git-history, npm-tarball, and clean-install privacy scans;
- version synchronization and CLI smoke tests.

Run the repository release verifier before commit, push, or publication:

```bash
./packaging/release/verify_release.sh
```

Do not publish `.env`, OAuth material, local paths, account or channel
identifiers, runtime databases, logs, private prompts, or generated reports.
