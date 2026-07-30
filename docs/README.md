# Documentation

NyaNya Agent keeps only durable Markdown documentation in this directory.
HTML reports are generated only when explicitly requested and are ignored by Git.

## Document map

| Area | Document | Purpose |
|---|---|---|
| Idea and architecture | [Architecture and roadmap](architecture_and_roadmap.md) | Product boundary, component ownership, completed capabilities, and deferred work |
| Detailed design | [Execution control plane](execution_control_plane.md) | Task, execution, approval, adapter, event, and recovery contracts |
| Development and deployment | [Installation and distribution](installation_and_distribution.md) | npm/Python installation model, packaging, update, and release rules |
| Operations | [Operations guide](operations_guide.md) | Service lifecycle, health checks, backend checks, and recovery commands |
| Remote access | [External dashboard access](external_dashboard_access.md) | Local, LAN, private-network, and authenticated tunnel options |
| Security | [Public and private source policy](source_publication_policy.md) | Publication boundaries and secret handling |
| Origin review | [Copyright review](copyright_review.md) | Source-origin and project-identity review |
| Acceptance tests | [User acceptance tests](user_acceptance_tests_ko.md) | Five operator-visible core scenarios |

## Local-only documents

The following files are operational or machine-specific and must stay untracked:

- `private/`
- `nyanya_remote_access_security_build_plan_20260723.md`
- generated `*.html` reports

Do not add local paths, account identifiers, IP addresses, credentials, pairing
URLs, channel IDs, or live runtime records to tracked documentation.
