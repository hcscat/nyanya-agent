# Documentation

NyaNya Agent keeps only durable Markdown documentation in this directory.
HTML reports are generated only when explicitly requested and are ignored by Git.

## Document map

| Area | Document | Purpose |
|---|---|---|
| Current development status | [개발 현황과 남은 작업](development_status.md) | Four-batch integration, implemented/partial behavior, current verification and follow-up priorities |
| Current P0 execution | [P0 implementation (2026-09-12)](p0_execution_20260912.md) | Serializable workers, parallel routing, reviewed file apply, held recovery and ledger migration |
| Automated test guide | [Python 테스트 안내](test_catalog_ko.md) | File-by-file scenarios, inputs, assertions, execution types and coverage limits |
| Historical stabilization | [CORE-STAB-01 (2026-09-10)](core_stabilization_20260910.md) | Original source review and verification; use development status for current completion |
| Idea and architecture | [Architecture and roadmap](architecture_and_roadmap.md) | Product boundary, component ownership, completed capabilities, and deferred work |
| Architecture review | [Architecture diagnostic (2026-08-26)](architecture_diagnostic_20260826.md) | Evidence-based current-state diagnosis, target boundaries, resizing choices, and phased follow-up |
| Detailed design | [Execution control plane](execution_control_plane.md) | Task, execution, approval, adapter, event, and recovery contracts |
| Implementation | [Local Control Plane implementation](local_control_plane_implementation.md) | Accepted product direction, current durable flow, limitations, and next phases |
| Policy | [`prompts/policy.md`](../prompts/policy.md) | Universal operating, safety, connector, and privacy policy |
| Policy supplements | [`prompts/policy_technical.md`](../prompts/policy_technical.md), [`prompts/policy_governance.md`](../prompts/policy_governance.md) | Technical enforcement and governance/review rules |
| Development and deployment | [Installation and distribution](installation_and_distribution.md) | npm/Python installation, private dashboard token provisioning, packaging, update, and release rules |
| npm release handoff | [npm release resumption guide](npm_release_resumption_guide.md) | Deferred OIDC trusted publishing, staged approval, validation, and rollback procedure |
| Operations | [Operations guide](operations_guide.md) | Service lifecycle, health checks, backend checks, and recovery commands |
| Remote access | [External dashboard access](external_dashboard_access.md) | Local, LAN, private-network, and authenticated tunnel options |
| Security | [Public and private source policy](source_publication_policy.md) | Publication boundaries and secret handling |
| Origin review | [Copyright review](copyright_review.md) | Source-origin and project-identity review |
| Acceptance tests | [User acceptance tests](user_acceptance_tests_ko.md) | Original five scenarios plus reviewed file apply, held recovery and parallel requests |

## Local-only documents

The following files are operational or machine-specific and must stay untracked:

- `private/`
- `operational_rollout_20260913.md` (instance-specific deployment evidence)
- `nyanya_remote_access_security_build_plan_20260723.md`
- generated `*.html` reports

Do not add local paths, account identifiers, IP addresses, credentials, pairing
URLs, channel IDs, or live runtime records to tracked documentation.
