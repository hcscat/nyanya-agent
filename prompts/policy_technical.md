# Technical Safety Policy

## Workspace and process boundaries

- Resolve paths and verify them against allowed workspace roots before use.
- Never operate on the filesystem root or a path outside the allowlist.
- Do not delete, move, rename, empty, or truncate protected runtime paths such
  as `.env`, `src/`, `config/`, `prompts/`, `scripts/`, `pyproject.toml`, or
  `package.json` without a separately approved recovery plan.
- Keep execution output and mutable runtime state in private state directories.
- Do not expose the local dashboard directly to the public internet.

## Durable execution

- Create a ledger task before starting provider, CLI, subprocess, or remote-host
  work.
- Create or adopt exactly one current execution for each attempt.
- Append progress and terminal state events; do not rewrite event history.
- Use writer leases for shared write resources.
- On process loss, mark confidence and status honestly; do not infer success from
  a missing process.

## Remote-host preparation

- Tailscale may provide private transport between approved Mac mini hosts.
- Tailscale connectivity does not grant task authorization, workspace access, or
  credential synchronization.
- A future host adapter must register host identity, capabilities, heartbeat,
  execution ownership, and recovery behavior in the ledger.
- Orca is not a supported execution path for the current product direction.

## Model routing

- Model choice is a policy decision based on task complexity, risk, latency,
  resource availability, and required context.
- Prefer the smallest model that meets quality and safety requirements.
- Use stronger models for architecture, complex coding, security review, and
  ambiguous high-impact work.
- Record selected model/profile and the reason in task or execution metadata,
  without storing credentials or unnecessary prompt content.

## Current P0 execution contract (2026-09-12)

Normal terminal/Discord work uses a versioned JSON OperationSpec, SQLite claims,
and a dedicated worker. Default concurrency is two operations, bounded to four.
Flash assesses each request; a recorded Flash/Luna/Astra profile produces bounded
analysis or a concrete UTF-8 file plan. Model choice never changes permissions.
Legacy provider checks and adapters are compatibility interfaces, not bypasses.

The model receives a bounded disposable workspace snapshot. It must return
summary/changes JSON; arbitrary shell execution and browser mutations are outside
this slice. New files use exclusive creation in unique work/date task folders.
Existing file modifications and deletions require owner/plan/hash/expiry-bound
approval. Only reviewed_changes applies files, under a workspace lock with
preimage validation and an apply journal. Approval words and feedback.review
records never grant file writes. Re-read workspace registration before execution.

Interrupted work is held without automatic retry. Reconcile partial file effects
before any fresh plan; never replay an apply operation. After another task succeeds,
remind the owner of incomplete tasks. The why command reports the original request,
recorded stage/reason and attempts without inventing causes. Delivery remains
separate from execution; full connector inbox/outbox reliability and real external
conversation continuation remain follow-up work. See docs/p0_execution_20260912.md.
