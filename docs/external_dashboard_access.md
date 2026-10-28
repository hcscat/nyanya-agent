# External Dashboard Access

Current source guide: 2026-10-12. Approved private-network HTTPS proxy access is supported with exact Host/Origin allowlists and application authentication. Public dashboard hosting, public tunnels and additional server/database infrastructure remain deferred. Actual instance addresses/settings and live checks belong in private operations notes; this guide does not authorize network changes.

## Security boundary

The dashboard should remain bound to loopback:

```text
NYANYA_DASHBOARD_HOST=127.0.0.1
NYANYA_DASHBOARD_PORT=8765
```

This prevents direct access from the LAN or public internet. Remote access should arrive through a private network or an authenticated reverse proxy.

The dashboard control token protects all `/v1/` reads and mutating APIs, including loopback connections. Host/Origin checks also apply. Keep the network access layer: a proxy login does not replace application authorization. Health and static assets remain readable but provide no access to operational records. The browser sends the token in headers and polls events every five seconds.

## Recommended choices

| Need | Recommended method | Client requirement |
|---|---|---|
| Same Mac | Local URL | None |
| Personal desktop or mobile devices | Tailscale Serve | Tailscale login on each device |
| Browser access without a VPN client | Cloudflare Tunnel plus Access | Authorized identity login |
| Trusted local network only | SSH port forwarding | SSH client and key |
| Public anonymous access | Not supported | Not applicable |

Raw router port forwarding to the dashboard is not an approved deployment mode.

## Local access

```bash
./scripts/nyanya_ctl.sh dashboard-health
open http://127.0.0.1:8765
```

## Unlocking and empty views

The static page opens without a control token, but its operational data requests require authentication and return `401` until the page is unlocked. Empty cards and the connection/authentication warning therefore do not establish that the server database is empty or that records were lost.

Use the dashboard unlock button and enter the dashboard control token, which is separate from the Discord bot token. On the host, the application first uses `NYANYA_DASHBOARD_CONTROL_TOKEN`; otherwise it reads `NYANYA_DASHBOARD_CONTROL_TOKEN_FILE` or the state directory's `data/dashboard_control.token`. Retrieve the value locally and keep it out of shared documentation, messages, URLs and logs.

Normal `nyanya setup` and both alternate installers create a private token file when no explicit token or existing file is present, preserving existing credentials on reruns. If an older installation returns `503` because no token was configured, rerun `nyanya setup --non-interactive` on the host, then unlock locally. Missing/unsafe token storage fails closed; setup does not overwrite an invalid existing file. Repair its contents/permissions locally before retrying. See [token provisioning](installation_and_distribution.md#dashboard-token-provisioning).

The token exists only in the current page's memory. A new device, tab or page reload requires unlocking again. Unauthenticated data APIs returning `401` is expected; valid authenticated reads should return `200`. If views remain empty after unlocking, inspect failed `/v1/` responses in the browser Network panel without sharing authorization headers.

## Tailscale Serve

Tailscale Serve publishes the loopback dashboard to devices and users allowed by the same tailnet. It is distinct from Funnel, which exposes a service to the public internet.

On the dashboard host:

```bash
tailscale status
tailscale serve --bg http://127.0.0.1:8765
tailscale serve status
```

Read the HTTPS hostname from `tailscale serve status`. If the dashboard replies `Invalid dashboard Host`, the request reached the application but its exact hostname is absent from the allowlist. Merge that hostname into the existing local environment values:

```text
NYANYA_DASHBOARD_ALLOWED_HOSTS=<hostname-from-serve-status>
NYANYA_DASHBOARD_CORS_ORIGINS=https://<hostname-from-serve-status>
```

The host entry has no scheme, port, path or wildcard. The Origin entry includes its exact HTTPS scheme/host/port when applicable, with no path. Multiple entries are comma-separated; preserve existing approved entries. Do not publish filled-in values or use a wildcard to bypass validation. Keep `NYANYA_DASHBOARD_HOST=127.0.0.1` and port `8765`.

After an authorized settings change, restart only the dashboard and check the configured proxy URL:

```bash
./scripts/nyanya_ctl.sh dashboard-restart
./scripts/nyanya_ctl.sh dashboard-health
```

Do not put the control token in a URL or persistent browser storage. Unlock the page with the existing token. The shell/health may return 200 without a token; operational APIs must return 401 without authentication, invalid Host 400, and disallowed Origin 403.

Keep Funnel disabled:

```bash
tailscale funnel status
```

On each client device:

1. Install Tailscale from the official distribution channel.
2. Sign in to the intended tailnet.
3. Confirm the device is approved when device approval is enabled.
4. Open the HTTPS URL shown by `tailscale serve status`.

Apply tailnet grants or access-control rules so only the operator's intended devices and identities can reach HTTPS port 443 on the dashboard host. Do not store the real tailnet DNS name, device IP, auth key, or policy identity in Git.

Tailscale Serve adds identity headers and strips spoofed incoming copies. If an application later consumes those headers, it must continue listening only on loopback so LAN clients cannot bypass Serve and forge identity information.

## SSH port forwarding

For temporary access from a device that already has SSH key access:

```bash
ssh -N -L 8765:127.0.0.1:8765 <dashboard-host>
```

Then open:

```text
http://127.0.0.1:8765
```

This does not require changing the dashboard bind address. Restrict SSH to key-based access and do not publish hostnames, usernames, or key locations in tracked documentation.

## Cloudflare Tunnel and Access

Use this only when clients should connect through a normal browser without a Tailscale client.

Required controls:

1. Create an outbound Cloudflare Tunnel to `http://127.0.0.1:8765`.
2. Map a dedicated hostname to that tunnel.
3. Create a Cloudflare Access self-hosted application for the hostname.
4. Add an allow policy for the intended identity and test denial from another identity before relying on it.
5. Keep the local dashboard on loopback and do not open an inbound router port.

A tunnel hostname without Cloudflare Access is not sufficient. The hostname can be internet-reachable even though the origin has no public IP.

## Same-LAN access

Binding to `0.0.0.0` expands network reach to devices that can reach the port; it does not remove token or Host/Origin checks. It increases the attack surface and is not the recommended default.

If a short LAN-only test is unavoidable:

1. use a trusted isolated LAN;
2. bind to a specific LAN address when possible;
3. restrict the macOS firewall;
4. stop the test and restore `127.0.0.1` immediately afterward.

Prefer SSH port forwarding for temporary LAN access.

## Verification

On the host:

```bash
lsof -nP -iTCP:8765 -sTCP:LISTEN
curl -fsS http://127.0.0.1:8765/health
tailscale status
tailscale serve status
```

Expected:

- the dashboard listens only on `127.0.0.1:8765`;
- `/health` returns `status=ok`;
- the intended private or authenticated proxy is active;
- Tailscale Funnel and raw router forwarding are disabled;
- an unauthorized network identity cannot reach the service;
- without the application token, operational APIs return 401 even when the page shell is reachable;
- allowed HTTPS Host/Origin succeeds; unknown Host/Origin is rejected.

## Operator actions

NyaNya or Codex can inspect local health, update local service configuration, and verify the proxy. The operator must personally approve account login, device approval, VPN extensions, identity policies, and any security-sensitive network permission.

## Official references

- Tailscale Serve: https://tailscale.com/docs/features/tailscale-serve
- Tailscale Serve CLI: https://tailscale.com/docs/reference/tailscale-cli/serve
- Tailscale Funnel: https://tailscale.com/kb/1223/funnel
- Cloudflare private applications: https://developers.cloudflare.com/cloudflare-one/setup/secure-private-apps/
- Cloudflare Tunnel: https://developers.cloudflare.com/tunnel/
- Cloudflare Access applications: https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/
