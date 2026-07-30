# nyanya-agent Operations Guide

This guide covers the local service command used to manage nyanya-agent, its Discord bridge, and its local dashboard.

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

The Discord bridge is the runtime entry point for NyaNya Agent. There is no separate always-on "agent server" process in the current architecture. The bridge receives messenger events and invokes the local agent core, conversation store, policy layer, dashboard ledger, and Codex delegation helpers as needed.

The dashboard is a separate local observability process. It serves `http://127.0.0.1:8765` by default and reads/writes `data/nyanya_dashboard.db`.

## Codex Separation Policy

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
