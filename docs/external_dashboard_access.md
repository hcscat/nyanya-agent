# External Dashboard Access

## Security boundary

The dashboard should remain bound to loopback:

```text
NYANYA_DASHBOARD_HOST=127.0.0.1
NYANYA_DASHBOARD_PORT=8765
```

This prevents direct access from the LAN or public internet. Remote access should
arrive through a private network or an authenticated reverse proxy.

The dashboard control token protects mutating API routes. Read-only operational
data must still be protected by the network access layer because it can reveal
tasks, execution state, artifacts, or project information.

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

## Tailscale Serve

Tailscale Serve publishes the loopback dashboard to devices and users allowed by
the same tailnet. It is distinct from Funnel, which exposes a service to the
public internet.

On the dashboard host:

```bash
tailscale status
tailscale serve --bg http://127.0.0.1:8765
tailscale serve status
```

Keep Funnel disabled:

```bash
tailscale funnel status
```

On each client device:

1. Install Tailscale from the official distribution channel.
2. Sign in to the intended tailnet.
3. Confirm the device is approved when device approval is enabled.
4. Open the HTTPS URL shown by `tailscale serve status`.

Apply tailnet grants or access-control rules so only the operator's intended
devices and identities can reach HTTPS port 443 on the dashboard host. Do not
store the real tailnet DNS name, device IP, auth key, or policy identity in Git.

Tailscale Serve adds identity headers and strips spoofed incoming copies. If an
application later consumes those headers, it must continue listening only on
loopback so LAN clients cannot bypass Serve and forge identity information.

## SSH port forwarding

For temporary access from a device that already has SSH key access:

```bash
ssh -N -L 8765:127.0.0.1:8765 <dashboard-host>
```

Then open:

```text
http://127.0.0.1:8765
```

This does not require changing the dashboard bind address. Restrict SSH to
key-based access and do not publish hostnames, usernames, or key locations in
tracked documentation.

## Cloudflare Tunnel and Access

Use this only when clients should connect through a normal browser without a
Tailscale client.

Required controls:

1. Create an outbound Cloudflare Tunnel to `http://127.0.0.1:8765`.
2. Map a dedicated hostname to that tunnel.
3. Create a Cloudflare Access self-hosted application for the hostname.
4. Add an allow policy for the intended identity and test denial from another
   identity before relying on it.
5. Keep the local dashboard on loopback and do not open an inbound router port.

A tunnel hostname without Cloudflare Access is not sufficient. The hostname can
be internet-reachable even though the origin has no public IP.

## Same-LAN access

Binding the dashboard to `0.0.0.0` exposes read-only operational data to every
device that can reach the port. This is not the default recommendation.

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
- an unauthorized client cannot open the dashboard.

## Operator actions

NyaNya or Codex can inspect local health, update local service configuration, and
verify the proxy. The operator must personally approve account login, device
approval, VPN extensions, identity policies, and any security-sensitive network
permission.

## Official references

- Tailscale Serve: https://tailscale.com/docs/features/tailscale-serve
- Tailscale Serve CLI: https://tailscale.com/docs/reference/tailscale-cli/serve
- Tailscale Funnel: https://tailscale.com/kb/1223/funnel
- Cloudflare private applications: https://developers.cloudflare.com/cloudflare-one/setup/secure-private-apps/
- Cloudflare Tunnel: https://developers.cloudflare.com/tunnel/
- Cloudflare Access applications: https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/
