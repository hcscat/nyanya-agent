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

The release package includes the canonical public policy templates under
`prompts/policy*.md`. They contain generic safety and governance rules only;
secrets, user mappings, runtime databases, logs, transcripts, and private
operational reports remain state or ignored files.

Public documentation is explicitly listed in the npm manifest. The linked test
catalog and Python test sources are included so their relative links also work
inside an installed package; private documents are never included by a docs glob.
The CLI build helper is shipped alongside its TypeScript sources.

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

Workspace access requires explicit registration. Trusted roots are also explicit:
an unset or empty `NYANYA_TRUSTED_WORKSPACE_ROOTS` trusts no directories, including
the application checkout. Trust cannot authorize access outside allowed workspace
roots or bypass approval. Register only the intended task workspace before use.

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
python -m pip install --upgrade "pip>=26.2"
python -m pip install -e ".[bots,dashboard,dev]"
npm ci
npm run build
```

Prepare pip 26.2 or newer in the target environment before dependency installation
or an audit. The npm setup and alternate installers already upgrade pip; verify
the resulting version when using a mirror or restoring an older environment.
pip is installer tooling, so it is not an application dependency.

The dependency floors include aiohttp 3.14.3 and development-only httpx2 2.12.
The verified httpx2 2.12.0 metadata requires httpcore2 2.12.0, so no redundant
direct httpcore2 dependency is added. Floors do not replace an audit of the
environment actually resolved and installed.

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

CI audits all npm dependencies (including development dependencies) with
`npm audit --audit-level=low`, and installed Python dependencies with
`python -m pip_audit --local`. A registry/network failure is an incomplete audit,
not a clean result. Do not apply unrelated automatic dependency upgrades.

For a review that must preserve existing compiled CLI files, use
`./packaging/release/verify_release.sh --skip-build`. This validates the current
package manifest and public files without invoking the prepack build; the full
gate and a fresh build are still required before release. The privacy gate checks
home-relative directory defaults and workspace command examples structurally,
without maintaining a list of personal names or rejecting author branding.

Do not publish `.env`, OAuth material, local paths, account or channel
identifiers, runtime databases, logs, private prompts, or generated reports.
