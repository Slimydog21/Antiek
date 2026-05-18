# Cloudflare Tunnel setup — `api.antiek.ai`

Replaces the previous grey-cloud direct-IP exposure of the
Hetzner VM. After this, `api.antiek.ai` is fully Cloudflare-proxied
(orange-cloud), TLS terminates at the edge, and the substrate's
origin port 443 is closed in UFW. Public attack surface on Hetzner
reduced to port 22 (SSH) only.

This is one-time setup; replays produce the same final state.

---

## Why this design

The previous architecture had two problems:

1. **Direct-IP exposure** — `api.antiek.ai` resolved straight to
   `167.235.202.98`. Anyone scanning Hetzner ranges could find the
   substrate's TLS listener. Caddy + uvicorn were the public
   attack surface.

2. **Cross-origin auth incompatibility** — the H4.5 design needed
   Cloudflare Access cookies to carry from `antiek.ai` (proxied)
   to `api.antiek.ai` (direct). They don't: the request bypasses
   Cloudflare entirely, the `Cf-Access-Authenticated-User-Email`
   header never gets injected, and the substrate's middleware
   has nothing to verify. The bearer path worked but kept the web
   app stuck on the broken cookie path.

Putting `api.antiek.ai` behind a tunnel fixes both. The substrate
binds only to `127.0.0.1:8001`. The tunnel originates from inside
the VM and connects outbound to Cloudflare's edge. No inbound
port is needed.

---

## One-time setup (already done 2026-05-18)

### 1. Install cloudflared on Hetzner

```bash
ssh root@<vm-ip>
mkdir -p /etc/apt/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
  | tee /etc/apt/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/etc/apt/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" \
  > /etc/apt/sources.list.d/cloudflared.list
apt-get update -qq
apt-get install -y cloudflared
```

### 2. Create the tunnel from a machine with `~/.cloudflared/cert.pem`

(Operator's laptop already has cert.pem from the `cloudflared
tunnel login` done for hermes-bridge.)

```bash
cloudflared tunnel create antiek-api
# → writes ~/.cloudflared/<UUID>.json credentials file
# → tunnel UUID 41fc328b-36ed-46c8-80b1-523db2e31eaa as of 2026-05-18
```

### 3. Copy credentials to the VM

```bash
TUNNEL_ID=41fc328b-36ed-46c8-80b1-523db2e31eaa
scp ~/.cloudflared/$TUNNEL_ID.json root@<vm-ip>:/etc/cloudflared/
ssh root@<vm-ip> chmod 600 /etc/cloudflared/$TUNNEL_ID.json
```

### 4. Write `/etc/cloudflared/config.yml` on the VM

Rendered from `infrastructure/ansible/templates/cloudflared-config.yml.j2`.
The key bit is the ingress rule pointing `api.antiek.ai` at
`http://127.0.0.1:8001` (uvicorn directly — Caddy no longer in
the path).

### 5. Register the systemd service

```bash
ssh root@<vm-ip> '
cloudflared --config /etc/cloudflared/config.yml service install
systemctl daemon-reload
systemctl enable --now cloudflared
'
```

Service starts; tunnel registers 4 connections to Cloudflare's
Frankfurt POPs (the closest set for a Hetzner Falkenstein origin).

### 6. Route the DNS

Use the explicit tunnel UUID rather than the name to avoid the
ambiguity where `cloudflared tunnel route dns <name>` may resolve
to a stale tunnel.

```bash
cloudflared tunnel route dns -f 41fc328b-36ed-46c8-80b1-523db2e31eaa api.antiek.ai
```

The `-f` flag overwrites the existing A record. Propagation is
near-instant inside Cloudflare's network (a few seconds);
external resolvers may take longer.

### 7. Stop + disable Caddy, close UFW 80/443

```bash
ssh root@<vm-ip> '
systemctl stop caddy
systemctl disable caddy
ufw delete allow 80/tcp
ufw delete allow 443/tcp
ufw delete allow 80
ufw delete allow 443
'
```

After this, only port 22 is reachable from the public internet.
The substrate (uvicorn) and tunnel agent (cloudflared) both bind
to 127.0.0.1.

### 8. Verify

```bash
# Direct-IP curl should hang then time out (port 443 closed):
curl -sk --max-time 4 https://<vm-ip>/health  # HTTP 000

# Tunneled URL should work:
curl -s https://api.antiek.ai/health
# {"status":"ok",...}

# Smoke through the tunnel:
ANTIEK_OPERATOR_TOKEN=$OP_TOKEN tools/ops/smoke_investigation.sh
# investigation.completed
```

---

## Failure modes + recovery

**`api.antiek.ai` returns 404 from Cloudflare**:
The DNS route is pointing at the wrong tunnel. Re-run step 6 with
the explicit UUID. cloudflared's "added CNAME to tunnel" log line
sometimes reports a stale tunnel ID — trust the actual destination,
verify with `curl https://api.antiek.ai/health` and check whether
the journalctl on the tunnel-running VM shows the request.

**`api.antiek.ai` times out**:
The tunnel itself is down. Check `systemctl status cloudflared` on
the VM. Most common cause: the credentials file was rotated and
the new file wasn't propagated to the VM.

**Origin returns 502 / connection refused via the tunnel**:
The substrate at `127.0.0.1:8001` isn't up. Check
`systemctl status antiek` on the VM.

**Web app at antiek.ai still 401s after Cloudflare Access setup**:
This means the Cloudflare Access cookie isn't reaching the
substrate. The most common cause now (post-tunnel-migration) is
the Access application not covering all three subdomains —
`antiek.ai`, `app.antiek.ai`, and `api.antiek.ai` must be in the
same Access application so the cookie carries cross-origin.

---

## Rollback

If something is fundamentally broken and you need to restore the
old direct-IP path immediately:

```bash
ssh root@<vm-ip> '
ufw allow 80/tcp
ufw allow 443/tcp
systemctl enable --now caddy
'

# In the Cloudflare dashboard: delete the api.antiek.ai CNAME,
# add back the A record pointing at <vm-ip>, turn off proxy
# (grey cloud) so Caddy can renew the cert.
```

Caddy's cert may need a re-issue if rollback happens after the
old cert has expired. ACME challenge runs on port 80, so opening
that is sufficient — Caddy renews automatically on next request.
