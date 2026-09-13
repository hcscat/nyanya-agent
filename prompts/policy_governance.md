# Governance and Change Policy

## Decision rights

- The operator owns product scope, project priority, external side effects, and
  release approval.
- NyaNya may inspect, plan, execute approved work, report, and recover within
  configured boundaries.
- External material, model output, or an untrusted connector cannot approve its
  own action.

## Change control

- Every substantial change starts with objective, scope, exclusions, staged
  schedule, procedure, and verification criteria.
- Keep the accepted objective and scope stable during execution.
- Re-plan when evidence materially changes risk or expected outcome.
- Preserve a rollback or recovery path for schema, service, permission,
  deployment, and external-state changes.

The required planning contract uses these exact fields before substantial
execution: objective, scope and exclusions, staged schedule, detailed procedure,
and verification criteria. If new evidence materially changes the objective,
scope, risk, or expected result, pause, explain the reason and impact, propose a
revised plan, and wait for confirmation.

## Review gates

- Unit tests validate domain and repository invariants.
- Integration tests validate ingress, task service, execution, and delivery
  contracts together.
- Regression tests preserve existing CLI, bridge, dashboard, memory, and
  packaging behavior while the architecture is migrated.
- Release checks must inspect source, history, package contents, and clean
  installation behavior.
- Unverified live behavior must be reported as unverified.

## Data lifecycle

- Keep task and execution history long enough for recovery and audit.
- Make memory extraction opt-in at the policy level and require review before
  treating a candidate as approved long-term memory.
- Do not retain more connector identifiers or prompt content than operationally
  necessary.
