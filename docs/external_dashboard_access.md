# External Dashboard Access Guide

Last checked: 2026-06-14

## Current Local State

Observed on this Mac mini:

```text
Dashboard URL: http://127.0.0.1:8765
Dashboard bind: 127.0.0.1 only
Listening process: Python on 127.0.0.1:8765
macOS firewall: enabled
LAN interface: en1
LAN IP: 172.30.1.32
Default gateway: 172.30.1.254
Tailscale CLI: not installed
cloudflared CLI: not installed
```

This is the safest default. The dashboard is reachable only from the Mac itself.

## Recommendation

Use this order:

1. Local only: keep `NYANYA_DASHBOARD_HOST=127.0.0.1`.
2. Private remote access: install Tailscale and publish the local service only to your tailnet.
3. Public-but-controlled access: use Cloudflare Tunnel with Cloudflare Access policy.
4. Raw router port forwarding: use only when there is a concrete reason and after adding authentication/TLS/reverse proxy protection.

Do not expose the FastAPI app directly to the public internet as plain HTTP.

## Option A: Local Only

Keep:

```text
NYANYA_DASHBOARD_HOST=127.0.0.1
NYANYA_DASHBOARD_PORT=8765
```

Use:

```bash
./scripts/nyanya_ctl.sh dashboard-start
open http://127.0.0.1:8765
```

No macOS firewall or KT router change is required.

## Option B: Same LAN Only

Set the dashboard host to `0.0.0.0` or the Mac's LAN IP, then restart:

```text
NYANYA_DASHBOARD_HOST=0.0.0.0
NYANYA_DASHBOARD_PORT=8765
```

```bash
./scripts/nyanya_ctl.sh dashboard-restart
```

Access from another device on the same Wi-Fi/LAN:

```text
http://172.30.1.32:8765
```

macOS firewall may prompt to allow incoming connections for Python. If it does not prompt, use System Settings -> Network -> Firewall -> Options and allow the relevant Python executable or service.

Use this only on a trusted private LAN.

## Option C: Tailscale Serve

This is the preferred remote access path.

Reason:

- The dashboard can remain bound to `127.0.0.1`.
- No KT router port forwarding is needed.
- Access is limited to devices/users in your tailnet.
- Tailscale Serve can proxy `localhost:8765` to an HTTPS tailnet URL.

After installing and logging in to Tailscale on the Mac mini and client devices:

```bash
tailscale serve localhost:8765
tailscale serve status
```

Keep dashboard settings:

```text
NYANYA_DASHBOARD_HOST=127.0.0.1
NYANYA_DASHBOARD_PORT=8765
```

Direct action status:

- I did not install Tailscale because it is not currently present on this Mac.
- I can install/configure it later if you explicitly choose this route and complete the Tailscale login/approval flow.

## Option D: Cloudflare Tunnel

Use this if you want a stable public hostname with Cloudflare Access in front.

Reason:

- No inbound router port is needed.
- `cloudflared` creates outbound connections to Cloudflare.
- Cloudflare Access can enforce login, device posture, and user policy before the request reaches the Mac mini.

Typical target:

```text
http://127.0.0.1:8765
```

Direct action status:

- `cloudflared` is not currently installed.
- This requires a Cloudflare account, a tunnel, and access policy decisions.

## Option E: KT Router Port Forwarding

This is the least preferred path for this dashboard.

Current local network suggests a KT-style gateway:

```text
Mac LAN IP: 172.30.1.32
Gateway: 172.30.1.254
```

Common KT HomeHub/GiGA WiFi guidance points to:

```text
Router page: http://172.30.1.254 or homehub.kt.com:8899
Menu path: 장치설정 -> 트래픽관리 -> 포트포워딩
Typical default account: ktuser / homehub, but this varies by model and may have been changed
```

On this Mac, quick HTTP checks to `172.30.1.254` and `172.30.1.254:8899` did not respond. The router admin page may require browser access, a different management port, or a different network path.

If you still choose port forwarding:

1. Reserve or fix the Mac mini LAN IP, currently `172.30.1.32`.
2. Set dashboard host to `0.0.0.0`.
3. Put a reverse proxy with TLS and authentication in front of FastAPI.
4. Forward an external high port to the reverse proxy, not directly to raw `8765`.
5. Restrict source IPs if the router supports it.
6. Check logs after opening the port.

Do not forward public internet traffic directly to `127.0.0.1:8765`/FastAPI. It will not work while bound to localhost, and binding it publicly without auth is not acceptable.

## What I Can Set Directly

I can directly set:

- NyaNya dashboard host/port in `.env`.
- NyaNya dashboard LaunchAgent.
- NyaNya dashboard process restart.
- Local health checks.
- Reverse proxy config if you choose one and provide the domain/access policy.
- Tailscale/cloudflared install commands after you choose that route.

I cannot safely complete without your action:

- KT router login and port forwarding, unless you authorize browser interaction and provide/enter router credentials yourself.
- Tailscale/Cloudflare account login and policy approval.
- Public DNS/domain setup unless credentials and target domain are available.

## Security Hardening Checklist

- Keep `NYANYA_DASHBOARD_HOST=127.0.0.1` unless remote access is intentionally configured.
- Prefer Tailscale Serve for personal access.
- Prefer Cloudflare Tunnel + Access for named public host access.
- Add application-level auth before any public exposure.
- Keep `.env`, `data/`, `logs/`, `downloads/`, `sessions/`, and `run/` out of git.
- Do not place Discord tokens, Google/OAuth state, cookies, or real user/channel IDs in public docs.
- Review `logs/` and `data/nyanya_dashboard.db` before sharing artifacts.

## References

- Apple macOS firewall settings: https://support.apple.com/guide/mac-help/change-firewall-settings-on-mac-mh11783/mac
- Apple firewall service/app access: https://support.apple.com/guide/mac-help/block-connections-to-your-mac-with-a-firewall-mh34041/mac
- Tailscale quickstart: https://tailscale.com/docs/how-to/quickstart
- Tailscale macOS install: https://tailscale.com/docs/install/mac
- Tailscale Serve: https://tailscale.com/docs/features/tailscale-serve
- Cloudflare Tunnel overview: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/
- Cloudflare Tunnel macOS service: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/local-management/as-a-service/macos/
- KT manual library: https://help.kt.com/serviceinfo/ManualDownloadInfo.do
- General port forwarding guide: https://www.noip.com/support/knowledgebase/general-port-forwarding-guide
