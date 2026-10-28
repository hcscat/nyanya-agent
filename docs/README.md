# Documentation

This directory contains the canonical **English** reusable documentation. In a split workspace, `github_source/docs` is the editing source; reviewed nonprivate English copies under the operating root stay byte-identical. The operating root also carries derived Korean translations named `<document>.ko.md`. Update corresponding translations when the English source changes; Korean editions are local operating documentation and are not part of this public docs directory or its package manifest. Korean requests or interface labels may remain quoted as literal test/UI fixtures.

Actual settings, identifiers, raw logs and deployment evidence stay in operating `OPERATIONS.md` and `docs/private`, outside the repository. Documentation-only updates do not imply runtime upgrades.

Start with [development status](development_status.md), then read the guide needed for the task. Linked files are not automatically loaded by every AI tool. Keep one paragraph/list item per physical line without width-based wrapping; preserve hierarchy, tables, code and intentional hard breaks. Generated HTML requires an explicit request and stays local.

## Filenames and dates

Use stable names for current contracts, such as `development_status.md` and `operations_guide.md`, and update them in place. A date in a retained review filename identifies its original design/verification baseline, not the latest implementation or a release version. Detailed private deployment records may use timestamps to identify their evidence/rollback set. Keep historical links stable rather than creating a full dated copy for every session; tagged release summaries belong to separately prepared Release Notes.

## Document map

| Area | Document | Purpose |
|---|---|---|
| Current development status | [Development status and remaining work](development_status.md) | Implemented/verified/deferred behavior and timeline |
| Topic memory | [LLM Wiki](llm_wiki.md) | Memory screen areas/buttons, cited summaries, scoped recall, conflicts, review and forgetting |
| P0 execution record | [P0 implementation (2026-09-12)](p0_execution_20260912.md) | Serializable workers, routing, reviewed apply, recovery and migration |
| Automated tests | [Python test catalog](test_catalog.md) | File-by-file inputs, assertions, execution types and limits |
| Historical stabilization | [CORE-STAB-01 (2026-09-10)](core_stabilization_20260910.md) | Original source review/verification; current status takes precedence |
| Architecture | [Architecture and roadmap](architecture_and_roadmap.md) | Product boundary, ownership, completed capabilities and backlog |
| Historical architecture review | [Architecture diagnostic (2026-08-26)](architecture_diagnostic_20260826.md) | Historical diagnosis/accepted direction |
| Detailed design | [Execution control plane](execution_control_plane.md) | Tasks, attempts, approval, adapters, events and recovery |
| Implementation | [Local Control Plane implementation](local_control_plane_implementation.md) | Current flow, constraints and remaining integration |
| Policy | [`prompts/policy.md`](../prompts/policy.md) | Common operating, safety, connector and privacy policy |
| Policy supplements | [`prompts/policy_technical.md`](../prompts/policy_technical.md), [`prompts/policy_governance.md`](../prompts/policy_governance.md) | Enforcement and review rules |
| Development/distribution | [Installation and distribution](installation_and_distribution.md) | npm/Python packaging, private dashboard token provisioning, setup, development and releases |
| npm release proposal | [npm release resumption guide](npm_release_resumption_guide.md) | Deferred OIDC/staging, verification and rollback |
| Operations | [Operations guide](operations_guide.md) | Dashboard count popups, request/result previews, natural-height five-item pages, service lifecycle, recovery and gzip retention |
| Remote access | [External dashboard access](external_dashboard_access.md) | Authentication/unlock, local and private-network access |
| Security/reliability | [Hardening behavior and limits](security_and_reliability.md) | Context, auth, delivery, resource and integrity boundaries |
| Security review and reporting | [Security policy](../SECURITY.md) | Threat model, security invariants, finding criteria and responsible reporting; root `AGENTS.md` holds contributor/code-review instructions |
| Publication privacy | [Public/private source policy](source_publication_policy.md) | Publication and secret handling |
| Origin review | [Copyright review](copyright_review.md) | Historical origin/product-identity review |
| Acceptance | [User acceptance tests](user_acceptance_tests.md) | Service, files, recovery, conversation and memory scenarios |

## Local-only documents

Keep these operational or machine-specific materials untracked:

- `private/`
- `operational_rollout_20260913.md`
- `nyanya_remote_access_security_build_plan_20260723.md`
- Operating `*.ko.md` translation copies
- Generated `*.html` reports

Do not add personal paths, account identifiers, private IP addresses, credentials, pairing URLs, channel IDs or live runtime records to public documentation.
