# Installation and Distribution

## Supported installation model

NyaNya Agent uses a TypeScript CLI and a Python runtime:

1. npm installs the compiled CLI.
2. `nyanya setup` finds Python, creates an isolated environment, installs runtime dependencies, creates private state directories, and offers connector setup.
3. `nyanya doctor` validates configuration, dependencies, permissions, services, and local health.

```bash
npm install -g @hcscat-dev/nyanya-agent
nyanya setup --all
nyanya doctor
```

The npm install step has no service side effects. Interactive credentials and macOS approvals belong to `nyanya setup`, not `postinstall`.

## Runtime and state separation

Published package files are immutable application code. Mutable state lives under `NYANYA_HOME`, including:

- the managed Python environment;
- local configuration and secrets;
- SQLite state;
- logs, sessions, downloads, and run files.

Package upgrades must preserve `NYANYA_HOME`. Uninstall removes services and package code only unless the operator separately requests state deletion.

The release package includes the canonical public policy templates under `prompts/policy*.md`. They contain generic safety and governance rules only; secrets, user mappings, runtime databases, logs, transcripts, and private operational reports remain state or ignored files.

Public documentation is explicitly listed in the npm manifest. The linked test catalog and Python test sources are included so their relative links also work inside an installed package; private documents are never included by a docs glob. The CLI build helper is shipped alongside its TypeScript sources.

## Configuration workflow

Initial setup may configure:

- an LLM provider through OAuth, CLI discovery, or an API key;
- Discord or Telegram credentials and allowlists;
- workspace roots and trusted roots;
- dashboard, memory worker, and macOS LaunchAgents.

Validation is part of setup and every configuration change. A diagnostic command may expose validation results, but users should not need a separate syntax-only step during normal operation.

Secrets must be entered locally, masked in output, written with owner-only permissions, and excluded from package and Git contents.

Workspace access requires explicit registration. Trusted roots are also explicit: an unset or empty `NYANYA_TRUSTED_WORKSPACE_ROOTS` trusts no directories, including the application checkout. Trust cannot authorize access outside allowed workspace roots or bypass approval. Register only the intended task workspace before use.

## Updates and removal

```bash
npm update -g @hcscat-dev/nyanya-agent
nyanya setup --non-interactive
nyanya doctor

nyanya service uninstall
npm uninstall -g @hcscat-dev/nyanya-agent
```

Homebrew, curl, and PowerShell installers may be provided as alternate delivery channels, but they must preserve the same state, validation, and removal contract.

## Development install

### Separate an operational workspace from development

An existing operational workspace may keep its installed code and private state at the current root while its Git development checkout lives in a child named `github_source`. This is a local installation layout; the GitHub repository itself still starts with `src`, `cli`, `tests` and the package manifests, without an extra `github_source` wrapper directory.

```text
<operational-workspace>/
  src/nyanya_agent/       installed Python code
  dist/                  installed JavaScript CLI
  scripts/               installed runtime launchers
  .env, .venv/, data/     private operational configuration and state
  logs/, sessions/       private operational output
  backups/               private rollback material
  github_source/         development checkout; run Git here
    .git/
    src/nyanya_agent/
    cli/, tests/, docs/
    .venv/, node_modules/ independent development dependencies
    .dev-state/          ignored, isolated development runtime state
```

`src/nyanya_agent` is the Python import package, not a second installation. The outer `github_source` directory separates the development checkout from the local operational installation. Do not change the Python package layout to perform this separation.

Common documents have one editing source: the development checkout's `docs` and READMEs. Keep reviewed nonprivate copies under the installed root identical; do not create divergent operating/public guides. Actual instance settings and verification evidence remain in private `OPERATIONS.md` / `docs/private` and are never copied into the public checkout. Do not symlink the whole documentation tree across this privacy boundary. Public docs use English as the canonical language. Derived `<document>.ko.md` translations stay under the operating docs only and are updated with their English counterparts.

Installed code stays pinned to its verified deployment artifact even when common docs are refreshed. Record a documentation-only overlay separately; a source push or newer guide is not installation or permission to restart. On a future code upgrade, ship the guides matching that tested artifact.

Create development dependencies inside the checkout with the commands below. Never reuse an operational virtual environment: an editable development install can otherwise redirect the running installation to development code.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade "pip>=26.2"
python -m pip install -e ".[bots,dashboard,dev]"
npm ci
npm run build
```

Use the development launcher from the Git checkout:

```bash
python3 scripts/dev.py paths
python3 scripts/dev.py test
python3 scripts/dev.py lint
python3 scripts/dev.py typecheck
python3 scripts/dev.py build
python3 scripts/dev.py dashboard
```

The launcher clears inherited NyaNya settings, selects the checkout's independent virtual environment and `.dev-state`, and uses a loopback development dashboard port separate from the installed service. Its first dashboard start creates an owner-only `.dev-state/data/dashboard_control.token`; enter that local value in the dashboard unlock prompt. The token is not printed or stored in the browser. `paths` diagnoses paths without running the application. The foreground dashboard is optional; it is not a LaunchAgent. `terminal` is available for deliberate development requests and can call configured model CLIs; automated validation must not invoke live models.

Service/setup/manager commands are not exposed by this launcher. Do not run operational service installation or management commands from a development checkout: legacy service scripts may use production labels. The launcher is an isolation convenience, not an OS sandbox or a substitute for account/provider authorization. It preserves the user's home directory; external model CLIs may still use their own stored authentication when deliberately invoked by a development request. Direct commands outside it may inherit unrelated environment settings.

Only reviewed public code, tests, templates and documentation enter Git. Keep development state, dependencies, local instruction files and operational backups out of Git and packages. Root and nested AGENTS instruction files have no blanket Git exception; each specific file and publication action requires explicit operator authorization, and instruction files remain excluded from installed packages. Private runtime credentials must not be copied into development. Tests use synthetic data, and package/privacy checks run from the Git checkout.

For an existing workspace migration, back up Git metadata (including linked worktree indexes), uncommitted changes, configuration and a consistent SQLite snapshot. Copy public candidates with hash verification, relocate Git metadata, repair linked worktree paths and test independent dependencies before archiving development-only files from the operational root. Keep the operational code, virtual environment and service paths unchanged where possible. Moving a Git repository does not deploy new code or require replaying interrupted work.

To deploy a later change, build a reviewed artifact from a verified commit and perform a separate backed-up installation/update. Do not install over an ancestor directory that contains the development checkout; existing source installers reject overlapping source/destination trees. Do not copy the complete development tree over the operational root or replace private state with development fixtures. Source installs record `artifact-manifest.json`: version, source commit/dirty state and hashes/modes of the selected public files. Verify it before promotion with `nyanya_agent.artifact_manifest.verify_manifest`; its digest detects changes, not publisher authenticity. Preserve a compatible code artifact and SQLite backup for rollback. A dirty source flag must not be presented as a clean committed release.

Prepare pip 26.2 or newer in the target environment before dependency installation or an audit. The npm setup and alternate installers already upgrade pip; verify the resulting version when using a mirror or restoring an older environment. pip is installer tooling, so it is not an application dependency.

The dependency floors include aiohttp 3.14.3 and development-only httpx2 2.12. The verified httpx2 2.12.0 metadata requires httpcore2 2.12.0, so no redundant direct httpcore2 dependency is added. Floors do not replace an audit of the environment actually resolved and installed.

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

CI audits all npm dependencies (including development dependencies) with `npm audit --audit-level=low`, and installed Python dependencies with `python -m pip_audit --local`. A registry/network failure is an incomplete audit, not a clean result. Do not apply unrelated automatic dependency upgrades.

For a review that must preserve existing compiled CLI files, use `./packaging/release/verify_release.sh --skip-build`. This validates the current package manifest and public files without invoking the prepack build; the full gate and a fresh build are still required before release. The privacy gate checks home-relative directory defaults and workspace command examples structurally, without maintaining a list of personal names or rejecting author branding.

Do not publish `.env`, OAuth material, local paths, account or channel identifiers, runtime databases, logs, private prompts, or generated reports.
