# nyanya-agent Operations Guide

2026-09-12 follow-up: [P0 execution contracts and verification](p0_execution_20260912.md)
supersede earlier callback-only execution, general-file write-hold and legacy mirroring
statements for normal terminal/Discord operations. Retain historical verification
and remaining delivery/session/platform limitations; source changes are not deployment.


This guide covers the local service command used to manage nyanya-agent, its
Discord bridge, and its local dashboard. NyaNya is operated as a Local Control
Plane: the SQLite execution ledger is the source of truth for task and execution
status, while the dashboard is primarily a monitoring and authenticated control
surface.

## Command

Use one management command:

```bash
./scripts/nyanya_ctl.sh status
./scripts/nyanya_ctl.sh status-all
./scripts/nyanya_ctl.sh preflight
./scripts/nyanya_ctl.sh auth
./scripts/nyanya_ctl.sh check
./scripts/nyanya_ctl.sh health
./scripts/nyanya_ctl.sh deep-health
./scripts/nyanya_ctl.sh smoke
./scripts/nyanya_ctl.sh restart
./scripts/nyanya_ctl.sh restart-all
./scripts/nyanya_ctl.sh dashboard-status
./scripts/nyanya_ctl.sh dashboard-health
```

Installed package entrypoints also expose:

```bash
nyanyactl status
nyanyactl status-all
nyanyactl preflight
nyanyactl auth
nyanyactl check
nyanyactl health
nyanyactl deep-health
nyanyactl smoke
nyanyactl restart
nyanyactl restart-all
nyanyactl dashboard-status
nyanyactl dashboard-health
```

## Service Model

The recommended macOS runtime for NyaNya Agent is LaunchAgent, not tmux.

Reason:

- LaunchAgent restarts the Discord bridge and dashboard after crashes.
- It starts automatically after login.
- Logs go to `logs/discord.launchd.*.log` and `logs/dashboard.launchd.*.log`.
- It avoids leaving manual terminal or tmux sessions as hidden operational state.

The LaunchAgent labels are:

```text
com.hcs.nyanya.discord
com.hcs.nyanya.dashboard
```

The Discord bridge is the current connector runtime for NyaNya Agent. There is
no separate always-on "agent server" process in the current architecture. The
bridge receives messenger events and submits them to the durable task service,
which writes SQLite task/execution/event state before invoking the local agent
core or Codex delegation helper. The terminal CLI uses the same task service.

The dashboard is a separate local observability process. It serves
`http://127.0.0.1:8765` by default and reads/writes `data/nyanya_dashboard.db`.
Use `/v1/execution-projects`, `/v1/execution-projects/{id}/codex-sessions`, and
`/v1/tasks?project_id={id}` for the authoritative project/session/task view.

## Codex Separation Policy

### Executable readiness

Management health checks and Discord delegation share `codex_cli.resolve_codex_cli`.
Set `NYANYA_CODEX_CLI` to a verified executable path or command. When unset,
discovery uses `codex` on the service PATH. An explicit invalid setting fails
closed instead of silently selecting another installation. Directories,
non-executable files, and broken symlinks are rejected. Avoid pinning the CLI to
a desktop app's internal bundle path when an independently installed CLI is used.

After changing this setting, restart the Discord bridge to reload its environment.
Verify the selected binary with `--version`, then verify bridge reconnection and
a read-only delegated request. A successful version check alone does not prove
authentication, model/profile compatibility, or end-to-end task completion.

OS launch failures are reported with a sanitized errno and actionable guidance,
not raw local executable/workspace paths. ENOENT means a missing executable,
working directory, or interpreter; EACCES means permission denied; EPERM means
operation not permitted; ENOEXEC means an invalid executable format. These errno
definitions come from the OS/Python standard library, not NyaNya-specific codes.
Permission errors must not trigger automatic privilege elevation.

Codex must remain separate from the NyaNya Agent service lifecycle.

Reason:

- Codex is a separate desktop/CLI recovery channel controlled independently by the user.
- It is useful when Discord, a dashboard, or the NyaNya bridge is unavailable.
- NyaNya may call Codex CLI for delegated work, but it must not embed Codex in the Discord bridge process.
- `start-all`, `restart-all`, `health`, and `repair` manage or validate the NyaNya runtime and dashboard. They do not start or repair Codex as part of the agent lifecycle.

Codex has separate management commands:

```bash
./scripts/nyanya_ctl.sh codex-status
./scripts/nyanya_ctl.sh codex-start
./scripts/nyanya_ctl.sh codex-install
./scripts/nyanya_ctl.sh codex-uninstall
```

The optional Codex LaunchAgent label is:

```text
com.hcs.codex.app
```

## Common Tasks

Check local Discord bridge prerequisites:

```bash
./scripts/nyanya_ctl.sh preflight
```

Check backend and Discord configuration:

```bash
./scripts/nyanya_ctl.sh check
```

Run only the configured backend authentication/connectivity check:

```bash
./scripts/nyanya_ctl.sh auth
```

For OAuth-backed backends, complete the browser consent flow and paste the authorization code into the terminal when the CLI asks for it.

Install and start the Discord bridge:

```bash
./scripts/nyanya_ctl.sh install
```

Start the NyaNya runtime entrypoint and dashboard:

```bash
./scripts/nyanya_ctl.sh start-all
```

Restart after changing `.env`, prompts, or source:

```bash
./scripts/nyanya_ctl.sh restart
```

Restart the NyaNya runtime entrypoint:
Restart the NyaNya runtime entrypoint and dashboard:

```bash
./scripts/nyanya_ctl.sh restart-all
```

Show service status:

```bash
./scripts/nyanya_ctl.sh status
./scripts/nyanya_ctl.sh status-all
```

Manage only the dashboard:

```bash
./scripts/nyanya_ctl.sh dashboard-install
./scripts/nyanya_ctl.sh dashboard-start
./scripts/nyanya_ctl.sh dashboard-status
./scripts/nyanya_ctl.sh dashboard-health
./scripts/nyanya_ctl.sh dashboard-restart
./scripts/nyanya_ctl.sh dashboard-stop
```

Run a runtime health check:

```bash
./scripts/nyanya_ctl.sh health
```

Run a deeper health check that also exercises the configured backend:
Run a deeper health check that also checks the dashboard HTTP endpoint and configured backend:

```bash
./scripts/nyanya_ctl.sh deep-health
```

Run a local no-message smoke check:

```bash
./scripts/nyanya_ctl.sh smoke
```

Try to repair the Discord bridge if health fails:

```bash
./scripts/nyanya_ctl.sh repair
```

Stop the service:

```bash
./scripts/nyanya_ctl.sh stop
```

Remove the service:

```bash
./scripts/nyanya_ctl.sh uninstall
```

Read or change the Discord bot username:

```bash
./scripts/nyanya_ctl.sh bot-name
./scripts/nyanya_ctl.sh bot-name NyaNya
```

The Discord application username, server nickname, and NyaNya command prefix are
separate settings. The command above changes the application username when the
bot token has permission. Change the server nickname in Discord server settings,
and configure `NYANYA_DISCORD_PREFIX` for the command prefix. Restart the bridge
after changing runtime configuration.

## Invocation Behavior

Discord handling is configured for:

- prefix requests through `!nyanya`,
- direct mention requests through `@NyaNya`,
- DM requests without a prefix.

The file-share channel remains quiet for ordinary channel chatter. Explicit prefix or mention requests are still processed.

## Dashboard Behavior

The dashboard records Discord-triggered work in SQLite:

- original request text,
- trigger and command mode,
- provider and model,
- status: received, queued, running, completed, failed, cancelled, ignored,
- start/end/duration,
- token fields when a backend exposes them,
- result summary or error summary,
- request events and audit log.

Current Gemini/Codex CLI paths do not expose stable token accounting, so token fields may be empty. This is intentional; the dashboard does not invent estimates.

The dashboard also includes project phase tracking for:

- planning,
- design,
- implementation,
- test.

Use phase `next_action` and the phase check endpoint/UI to identify work that requires Discord confirmation. The Discord bridge can also run a periodic phase checker when explicitly enabled:

```text
NYANYA_PHASE_CHECK_ENABLED=true
NYANYA_PHASE_CHECK_INTERVAL_SECONDS=21600
NYANYA_DASHBOARD_CONFIRMATION_CHANNEL_ID=<discord_channel_id>
```

The checker is disabled by default to avoid unsolicited Discord messages.

## Private Runtime Files

These files are local-only and must not be committed:

```text
.env
config/user_workspaces.json
prompts/local_system.md
logs/
data/
sessions/
downloads/
run/
```

## CORE-STAB-01 recovery behavior

See [the current stabilization handoff](core_stabilization_20260910.md) before upgrading. Schema v3 is applied on runtime initialization; preserve a verified pre-upgrade backup. No live upgrade was performed by the source change.

Discord `recovery` / `복구` lists held work; `result <task-id>` / `결과 <task-id>` retrieves the caller's persisted result. Reconnect notices are checked every 60 seconds and may wait for lease expiry. Records without a known allowed destination need local review. Notices can repeat across bridge restart; this is not a durable outbox.

Interrupted work is not replayed automatically. Review external processes and side effects before cancelling or making a replacement request. An unresolved claim can hold later owner work; do not edit SQLite to bypass it or assume a cancellation request terminated a process. Dashboard retry returns a conflict until explicit reconciliation is implemented.

The TypeScript state backup command uses SQLite online backup and rejects unsafe destinations/symlinks. Backups are per database/file, not an atomic snapshot of all state. Legacy shell backup/restore helpers use separate path selection; inspect that path and stop writers before a restore. Never restore over a running service.
