# npm Release Resumption Guide

Status: documented only; no publishing workflow or npm account setting was changed.

Last reviewed: 2026-08-26

## Purpose

This document preserves the proposed npm release migration so it can be resumed
later without relying on a long-lived token. It is intentionally separate from
the normal CI workflow and from source-version changes.

The current package is `@hcscat-dev/nyanya-agent` at source version `0.3.0`.
At the time of this review, npm also reported `0.3.0` as the latest public
version. The repository has CI in `.github/workflows/ci.yml`, but it has no npm
publish workflow.

## Why this work is needed

npm announced that granular access tokens that bypass 2FA will lose direct
publishing capability around January 2027. Such tokens will be limited to
reading private packages and staging a publish. npm recommends moving automated
publishing to trusted publishing with OpenID Connect (OIDC), or using staged
publishing with human 2FA approval.

This banner is a registry-wide policy warning. It does not mean this package is
currently compromised, and it does not require deleting or recreating the GitHub
repository.

Official references:

- [npm token restriction announcement](https://github.blog/changelog/2026-07-08-npm-install-time-security-and-gat-bypass2fa-deprecation/)
- [Trusted publishing for npm packages](https://docs.npmjs.com/trusted-publishers/)
- [Staged publishing for npm packages](https://docs.npmjs.com/staged-publishing/)
- [npm package publishing and 2FA settings](https://docs.npmjs.com/requiring-2fa-for-package-publishing-and-settings-modification/)

## Recommended durable release model

Use all three controls together:

1. GitHub Actions authenticates to npm through OIDC trusted publishing.
2. The trusted publisher is limited to `npm stage publish`.
3. A maintainer reviews and approves the staged artifact with npm account 2FA.

In this model, OIDC answers **which CI workflow may submit the package**.
Staged publishing answers **whether that submitted package may become public
without a human review**. They are complementary, not competing alternatives.

The proposed flow is:

```text
release tag
  -> GitHub-hosted Actions runner
  -> install, build, test, release/privacy verification
  -> npm stage publish through short-lived OIDC identity
  -> inspect staged tarball and metadata
  -> maintainer approves with 2FA
  -> npm version becomes public
```

This is the maximum-security posture currently recommended in npm's trusted
publishing documentation when combined with the package setting **Require
two-factor authentication and disallow tokens**.

## Prerequisites to recheck when work resumes

Do not copy the 2026 version numbers blindly. Recheck npm's current requirements
and the repository state first.

- The package already exists on npm. Staged publishing cannot create a brand-new
  package.
- The maintainer's npm account has working 2FA and recovery access.
- The GitHub repository URL in `package.json` exactly matches the publishing
  repository.
- The workflow runs on a GitHub-hosted runner. npm did not support self-hosted
  runners for trusted publishing at the time of this review.
- The npm CLI and Node versions meet the current trusted/staged publishing
  minimums. On 2026-08-26, npm documented Node `22.14.0` or later, npm `11.5.1`
  or later for trusted publishing, and npm `11.15.0` or later for staged
  publishing.
- Package, Python, lockfile, and release metadata versions are synchronized.
- `main` and `origin/main` point to the reviewed release source.

## Proposed repository change

Create `.github/workflows/publish.yml` only when publishing work resumes. The
npm trusted publisher registration must use the exact filename `publish.yml`,
not its full path.

The following is a design template, not an installed workflow:

```yaml
name: Stage npm package

on:
  push:
    tags:
      - "v*"

permissions:
  contents: read
  id-token: write

jobs:
  stage:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-node@v6
        with:
          node-version: "24"
          registry-url: "https://registry.npmjs.org"
          package-manager-cache: false
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - run: npm ci
      - run: python -m pip install -e ".[bots,dashboard,dev,security]"
      - run: npm run build
      - run: npm run check
      - env:
          PYTHONPATH: src
        run: python -m pytest -q
      - run: python -m pip_audit --local
      - run: python -m bandit -r src/nyanya_agent -lll
      - run: packaging/release/verify_release.sh
      - run: npm stage publish --access public
```

Before adopting this template, compare action and runtime versions with the
current CI workflow and official npm examples. Release jobs should use a fresh
install and should not restore a package-manager cache.

## npm account configuration sequence

The order matters. Do not disable token publishing before proving OIDC works.

1. Add and review `publish.yml` without creating a release tag.
2. In the npm package settings, add a GitHub Actions trusted publisher with the
   exact GitHub owner, repository, and workflow filename.
3. Select only `npm stage publish` as the allowed action.
4. Use a deliberately prepared next version to run the first staged release.
5. Download and inspect the staged tarball, provenance, file allowlist, version,
   repository URL, and executable modes.
6. Approve that stage with 2FA and verify the public package.
7. Only after the full path succeeds, set Publishing access to **Require
   two-factor authentication and disallow tokens**.
8. Revoke obsolete automation tokens. Retain a read-only token only if private
   dependency installation truly needs it.

npm does not validate all trusted-publisher fields when they are saved. A typo
in the repository or workflow name may only be discovered during publication.

## Release checklist

### Source and version

- Confirm the working tree and staged file list.
- Confirm the release commit is on `origin/main`.
- Synchronize `package.json`, `package-lock.json`, and Python package version.
- Review all commits since the last public version.

### Verification

Run the repository's release gate:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
.venv/bin/ruff check src/nyanya_agent tests
npm run typecheck --if-present
node --check src/nyanya_agent/dashboard_static/app.js
./packaging/release/verify_release.sh
npm pack --dry-run
```

Manually inspect the packed file list for personal paths, account names,
identifiers, credentials, private topology, runtime data, and unintended local
documents. Automated token-pattern scanning is necessary but not sufficient.

### Staged artifact review

- Confirm package name, version, access level, repository URL, license, and bins.
- Download the stage with `npm stage download <stage-id>` and inspect that exact
  tarball.
- Confirm the stage came from the intended GitHub workflow and commit.
- Confirm the package contains no `.env`, local configuration, logs, data,
  downloads, sessions, or private documentation.
- Confirm install and a representative command in a clean temporary directory.
- Approve only after all checks pass.

### Post-release

- Compare `npm view @hcscat-dev/nyanya-agent version` with the intended version.
- Confirm the provenance information is present when the repository and package
  meet npm's public provenance conditions.
- Install from the public registry into a clean temporary environment.
- Record the release commit, workflow run, stage approval, verification results,
  and any rollback note.

## Failure and rollback guidance

- If OIDC authentication fails, verify `id-token: write`, the exact trusted
  publisher owner/repository/workflow fields, GitHub-hosted runner use, and the
  repository URL in `package.json`.
- If verification fails, do not approve the stage. Correct the source and create
  a new version; do not overwrite an existing npm version.
- If the wrong artifact is staged, leave it unapproved and follow npm's current
  stage cancellation/expiry procedure.
- If the public release is bad, prefer a corrected patch release and deprecate
  the affected version when appropriate. Unpublishing is governed by npm policy
  and should not be the normal rollback mechanism.
- Keep the existing manual 2FA publication path until the first OIDC staged
  release is proven end to end.

## Work deliberately not performed

- No `publish.yml` was created.
- No npm trusted publisher was registered.
- No GitHub secret, environment, or protection rule was changed.
- No npm publishing-access setting or token was changed.
- No package was staged, published, deprecated, or removed.
