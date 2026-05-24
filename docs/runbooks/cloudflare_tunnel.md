# Runbook · Cloudflare Tunnel

**Owner:** infrastructure
**Last verified:** 2026-05-24

## Symptom

- `https://api.antiek.ai` returns Cloudflare error codes: 502 Bad
  Gateway, 526 Invalid SSL certificate, 530 Origin DNS error.
- Frontend at `https://antiek.ai` shows network errors intermittently
  when calling the API.
- `cf-tunnel-error` lines in journalctl.

## Likely cause

The Antiek API runs on a Hetzner CCX23 and is exposed via Cloudflare
Tunnel (`cloudflared`). The tunnel runs as a systemd unit on the
Hetzner host. Most outages:

1. **`cloudflared` service crashed or stopped.** Cloudflare side sees
   "no tunnel," returns 530 / 503.
2. **Underlying `antiek.service` (FastAPI) stopped.** Tunnel is alive
   but origin returns nothing → Cloudflare 502.
3. **Origin cert expired.** Cloudflare strict-SSL mode requires a
   valid origin cert; expiry → 526.
4. **Cloudflare network issue (rare).** Confirm via
   <https://www.cloudflarestatus.com>.

## Quick diagnostics

```bash
# Cloudflare's side:
curl -s -o /dev/null -w "%{http_code}\n" https://api.antiek.ai/health

# Origin's side (from the Hetzner host):
systemctl status cloudflared
systemctl status antiek
journalctl -u cloudflared -n 50 --no-pager
journalctl -u antiek -n 50 --no-pager

# Direct origin check (bypass Cloudflare):
curl -sk https://localhost:8000/health  # on the Hetzner host
```

## Root-cause path

The tunnel is two services: `cloudflared` (Cloudflare side) and
`antiek.service` (origin). The first hop in any 5xx is identifying
which side is down.

- HTTP 502 (Bad Gateway): cloudflared is up; antiek-service is down
  or non-responsive on the configured port.
- HTTP 530 (Origin DNS error): cloudflared can't resolve / reach its
  configured origin. Usually means `cloudflared` itself crashed.
- HTTP 526 (Invalid SSL cert): origin's TLS cert expired or doesn't
  match. The runbook for cert renewal is in
  `infrastructure/runbooks/origin-tls.md` (if it exists; if not, the
  fix is `certbot renew` on the Hetzner host).

## Mitigation

```bash
# Bring everything back up (idempotent).
systemctl restart antiek
systemctl restart cloudflared

# Watch for stability.
journalctl -u cloudflared -f
```

If repeat outages: check Hetzner host's CPU/memory; OOM is the most
common cause of antiek-service restart loops.

## Reference

- Origin runbook: `infrastructure/runbooks/agentmail-setup.md` (mentions
  the tunnel)
- Magic-link auth: `infrastructure/runbooks/magic-link-auth.md`
- Cloudflare status: <https://www.cloudflarestatus.com>
- cloudflared docs: <https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/>
- Memory: CLAUDE.md "What's running on prod" section

## Worked example

```
$ curl -s -o /dev/null -w "%{http_code}\n" https://api.antiek.ai/health
502

$ ssh hetzner systemctl status antiek
   Active: failed (Result: exit-code) since 2026-05-24 02:00:00 UTC; 5h ago

$ ssh hetzner journalctl -u antiek -n 20
... OSError: [Errno 12] Cannot allocate memory ...
```

Trace:

1. Cloudflare returns 502 → origin side is down.
2. systemd shows antiek service failed.
3. Logs show OOM during a long-running ingest.
4. Mitigation: `systemctl restart antiek`. Long-term: tune
   uvicorn's `--workers 1` (per CLAUDE.md invariant #1) and add
   memory pressure handling to the ingest path.
