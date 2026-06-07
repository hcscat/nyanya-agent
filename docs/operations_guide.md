# nyanya-agent Operations Guide

This guide covers the local service command used to manage nyanya-agent and its Discord bridge.

## Command

Use one management command:

```bash
./scripts/nyanya_ctl.sh status
./scripts/nyanya_ctl.sh preflight
./scripts/nyanya_ctl.sh check
./scripts/nyanya_ctl.sh restart
```

Installed package entrypoints also expose:

```bash
nyanyactl status
nyanyactl preflight
nyanyactl check
nyanyactl restart
```

## Service Model

The recommended macOS runtime is LaunchAgent, not tmux.

Reason:

- LaunchAgent restarts the Discord bridge after crashes.
- It starts automatically after login.
- Logs go to `logs/discord.launchd.out.log` and `logs/discord.launchd.err.log`.
- It avoids leaving manual terminal or tmux sessions as hidden operational state.

The LaunchAgent label is:

```text
com.hcs.nyanya.discord
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

Install and start the Discord bridge:

```bash
./scripts/nyanya_ctl.sh install
```

Restart after changing `.env`, prompts, or source:

```bash
./scripts/nyanya_ctl.sh restart
```

Show service status:

```bash
./scripts/nyanya_ctl.sh status
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

## Invocation Behavior

Discord handling is configured for:

- prefix requests through `!nyanya`,
- direct mention requests through `@NyaNya`,
- DM requests without a prefix.

The file-share channel remains quiet for ordinary channel chatter. Explicit prefix or mention requests are still processed.

## Private Runtime Files

These files are local-only and must not be committed:

```text
.env
config/user_workspaces.json
prompts/local_system.md
logs/
sessions/
downloads/
run/
```
