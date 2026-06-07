# Discord Bot Rename Guide

Date: 2026-06-07

This guide explains how to rename the Discord bot used by nyanya-agent to a visible name such as `NyaNya`.

## Key Distinction

Discord has multiple names that look similar but behave differently.

| Name | Where it appears | Where to change it |
|---|---|---|
| Application name | Developer Portal, OAuth2 install prompts, App Directory metadata | Discord Developer Portal -> Application -> General Information |
| Bot username | The bot user name people see in servers and chats | Discord Developer Portal -> Application -> Bot -> Username |
| Server nickname | The bot's local nickname inside one Discord server | Discord server member settings, if the server has assigned a nickname |
| Command prefix | Text users type before a command, such as `!nyanya` | `.env`, `NYANYA_DISCORD_PREFIX` |
| Agent display text in code/docs | Help text, logs, system prompt, README | NyaNya Agent source/config/docs |

Official Discord support states that the application name appears in Developer Portal and OAuth2 prompts, while the bot username is what users see in servers and chats.

References:

- Discord support: https://support-dev.discord.com/hc/en-us/articles/6129090215959-How-Do-I-Change-My-Bot-s-Name
- Discord app overview: https://docs.discord.com/developers/quick-start/overview-of-apps
- Discord bot getting started guide: https://docs.discord.com/developers/quick-start/getting-started

## Rename Only the Existing Bot

Use this path when the token, client ID, permissions, and installed server membership should stay the same.

1. Open https://discord.com/developers/applications
2. Select the existing Discord application used by nyanya-agent.
3. Open `General Information`.
4. Change the application name if OAuth/install prompts should also show the new name.
5. Open `Bot`.
6. Change the bot `Username` to the desired visible bot name, for example `NyaNya`.
7. Save changes.
8. In the Discord server, check whether the bot has a server nickname. If a nickname exists, it can override the visible username in that server.
9. If needed, remove or change the server nickname using Discord server/member management permissions.

This does not require resetting the bot token. Do not reset the token unless the token is compromised.

## Update NyaNya Agent Runtime Text

The Discord username change only changes Discord's bot identity display. It does not automatically change local help text, log text, command prefix, or documentation.

Recommended local updates:

```text
config/nyanya.json
prompts/system.md
.env
README.md
docs/
```

Typical `.env` values:

```text
NYANYA_DISCORD_PREFIX=!nyanya
NYANYA_DISCORD_BOT_TOKEN=
```

If users are accustomed to the old prefix, keep the old prefix temporarily and announce a migration date. If the visible bot name changes but the prefix stays the same, the bridge code does not need changes.

## Restart Requirement

Changing the bot username in Discord Developer Portal is handled by Discord and does not require restarting the Python process just to make Discord display the new username.

Restart the bridge when local runtime settings changed:

```bash
./scripts/run_discord_bridge.sh
```

For LaunchAgent installs:

```bash
./scripts/nyanya_ctl.sh restart
./scripts/nyanya_ctl.sh status
```

## When Re-Invite Is Needed

No re-invite is needed when renaming the same existing application/bot.

Re-invite is needed only when you create a new Discord application or bot account. In that case these values change:

- application/client ID,
- bot token,
- OAuth2 install URL,
- server permissions grant.

## Recommended Rename Checklist

1. Rename application name in Developer Portal if OAuth/install prompts should change.
2. Rename bot username in Developer Portal `Bot` settings.
3. Check server nickname and update it if needed.
4. Keep the existing token unless compromised.
5. Update `.env` only if prefix or token changed.
6. Restart local bridge only if `.env`, scripts, prompts, or source text changed.
7. Send a test message by mention and by prefix.
8. Confirm file upload behavior in the file-share channel still works.

## Rollback

If the new name causes confusion:

1. Change the bot username back in Developer Portal.
2. Restore the previous server nickname if one was used.
3. Restore the previous command prefix in `.env`.
4. Restart the bridge if `.env` changed.
