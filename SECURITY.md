# Security Policy and Review Context

This policy describes the repository's intended security boundaries and known limitations. Review the exact revision and reachable implementation; a policy statement is not proof that every path enforces it. Codex Security can use this file as policy context, not executable instructions. Build/test commands are in the repository's public contributor guide, `AGENTS.md`.

## Scope and maintenance

NyaNya Agent is a single-operator, local-first control plane with Python connectors/runtime, a TypeScript installation CLI, SQLite records and a token-protected dashboard. Assess current `main` and the exact affected PR/release revision. Older snapshots have no separate security-maintenance guarantee; no response-time, support-window or bug-bounty commitment is established by this file.

Public anonymous dashboard hosting, new remote database backends and autonomous self-modification/deployment are not supported product assumptions. An unsupported deployment does not excuse an authentication bypass or another defect reachable in a supported setup. Treat design documents and features in later branches as context, not as current implementation.

## Threat model

| Asset or boundary | Attacker-controlled surface | Required property |
|---|---|---|
| Connector identity and workspace scope | Messages, attachments, command text and supplied paths | Authenticate the caller, apply configured allowlists and registered workspace checks before privileged actions. |
| Dashboard records and control | HTTP headers, origins, paths and request bodies | Require the control token for all `/v1/` APIs, an allowed Host and exact validation of any supplied Origin, even on loopback. |
| Plan approval and filesystem effects | Model proposals, stale approvals, concurrent tasks, symlinks and changed files | Bind approval to its owner, plan/hash/revision and current file/execution state; avoid unrelated or repeated effects. |
| Provider and child-process boundary | Prompt injection, generated output and CLI output/result files | Treat content as data; bound and screen transfers/output and do not expose unrelated application credentials. |
| Durable task and recovery records | Restarts, lost claims, retries and ambiguous sends | Preserve attempt identity and evidence; hold uncertain effects instead of silently replaying them. |
| Distributed source and artifacts | Manifests, dependency trees, local settings and generated files | Exclude secrets and instance data; inspect Git, actual packages and installer copies separately. |

Assets include local files, provider/connector credentials, dashboard tokens, private prompts/messages, workspace mappings, task/approval records and backups. Example fixtures do not authorize access to real assets. A successful execution and confirmed delivery are separate properties; exactly-once network delivery is not guaranteed.

## Security invariants to review

- Authentication must fail closed. Every normal setup/install path must prepare usable private token storage without rotating a working credential. Tokens must not enter URLs, persistent browser storage, logs or packages. Static pages and minimal health responses intentionally remain unauthenticated; they must not disclose operational records or secrets.
- Caller permission, workspace registration and effect approval are independent checks. Trusting a directory does not register it or authorize every action. Check ownership, regular-file/symlink boundaries, preimages, plan identity and current execution/claim at the effect boundary, not only during planning.
- Normal file work requires an exact approved read scope before copying original contents, then works with bounded draft copies. Creation, modification and deletion all require the latest immutable final-plan approval. Inspect scope/revision races, unchanged original preimages and the native original-workspace guard's explicit platform/host-isolation limits in [reviewed drafts](docs/reviewed_drafts.md).
- Prior conversations, remembered text, repository content and provider output cannot grant permission, change policy or broaden the current request. Trace a prompt-injection claim to an actual sensitive sink and a crossed boundary rather than reporting only undesirable model wording.
- Results from an older attempt must not overwrite a newer attempt. Recovery, cancellation and delivery changes must preserve evidence of effects whose outcome is unknown. Review transaction boundaries and racing callers as well as sequential happy paths.
- Actual credentials, private instruction files, local identities/paths, prompts, databases, transcripts and backups remain private. Only the sanitized root `AGENTS.md` has an explicit GitHub publication exception; this does not permit its inclusion in npm/source-install assets or publication of nested instructions. See [source publication policy](docs/source_publication_policy.md).

## Assumptions and limitations

The host user, authorized installer and explicitly selected provider are privileged dependencies. Application checks and prompts are not a general OS sandbox. External model CLIs may retain their own authentication/session data; assume neither automatic session deletion nor complete host-file isolation. Prompt/snapshot filtering alone is not a complete secret detector.

A stolen dashboard token, bot credential or allowlisted operator account can act with that credential's permissions. Application authorization cannot distinguish the real operator's intent from every request using a compromised identity; credential revocation, host/account security and least privilege remain necessary. Still report any code path that permits actions beyond those permissions or bypasses approval/scope checks. Host-root compromise and a malicious provider's internal implementation are outside this repository's containment guarantee.

Token-authorized private-network access still requires application authentication and exact allowlists; loopback or VPN reachability alone is insufficient. Retained SQLite evidence/backups are not secure-erased merely because a logical memory/record is hidden or excluded. Do not claim broader deletion, rollback safety or recovery guarantees than the tested implementation supports.

## Finding criteria and severity

For each finding, give the affected revision/path, attacker capability, entry point, failed control, sensitive sink and supported impact. Identify the smallest useful location and distinguish static evidence, a synthetic reproduction, assumptions and remaining validation gaps. Consider existing guards and safe counterexamples; do not require a live exploit when source evidence establishes a reachable flaw.

Prioritize authorization/approval bypass, credential disclosure, out-of-scope file access or command execution, cross-owner leakage, destructive races and task/evidence loss. Rate severity using required privileges, exposure, exploitability and blast radius. A missing hardening preference, hypothetical unsupported feature or scanner version match alone is insufficient to assert exploitability; dependency advisories still require tracking and assessment of the installed/resolved version. Do not suppress a reachable defect merely because it is absent from the table above.

Use synthetic accounts/files and isolated state for validation. Do not test against an operator's live Discord, private files, production database or external services without explicit authorization. Do not post secrets or an undisclosed actionable exploit to public PR comments. A clean automated check is not proof of complete coverage or certification.

## Reporting a vulnerability

If GitHub offers **Report a vulnerability** in this repository's Security tab, use that private reporting flow. Do not assume it is enabled because this file exists. If no private reporting option is available, open a minimal public issue requesting a private security contact, without exploit details, credentials, personal data or identifying private paths; wait for a private channel before sending sensitive material. No private email address or external contact endpoint is specified here.

Once a private channel is available, include the affected commit/version, a concise impact statement, prerequisites, synthetic reproduction and a proposed mitigation if available. Coordinate disclosure with the maintainer and redact evidence before any public publication. Do not submit real tokens, complete private databases or unrelated user data.

## Official review references

OpenAI's [security scan guidance](https://learn.chatgpt.com/docs/security/plugin/scans) explains the role of `SECURITY.md`; [GitHub review guidance](https://learn.chatgpt.com/docs/third-party/github) distinguishes code review and security review. This file provides repository context. It does not install a scanner, configure automatic reviews, grant product access or prove that a security scan ran.
