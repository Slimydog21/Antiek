# Cloudflare Access Setup — operator auth at the edge (H4.5)

**One-time operator action.** Replaces the build-time
`VITE_OPERATOR_TOKEN` approach (which leaked the token via the JS
bundle) with proper user authentication at the Cloudflare edge.

After this, `app.antiek.ai` and `api.antiek.ai` both require an
authenticated operator session before any request reaches the
substrate. The substrate validates the
`Cf-Access-Authenticated-User-Email` header that Cloudflare injects.

Machine callers (probes, smoke runs, CI scripts) keep using
`Authorization: Bearer $ANTIEK_OPERATOR_TOKEN` directly — they
bypass Cloudflare Access via the bearer path.

---

## Why this design

Three properties we want:

1. **Operator-identity-bound, not shared-secret-bound** — when a
   second user joins (Sprint 19+), the same machinery extends to
   per-user policies. A shared bearer doesn't scale.
2. **No secret in the web bundle** — the JS at `antiek.ai` is
   publicly downloadable; embedding a token there is performative
   auth.
3. **Stays functional for ops scripts** — probes need to hit the
   substrate without a browser session.

The two-path middleware (substrate-side, see
`interfaces/research/api/app.py`) accepts either:

- `Cf-Access-Authenticated-User-Email` matching `ANTIEK_OPERATOR_EMAIL` (browser path)
- `Authorization: Bearer <token>` matching `ANTIEK_OPERATOR_TOKEN` (machine path)

When both env vars are set, either path suffices. When neither is
set, enforcement is disabled (the current dev / test posture).

---

## Steps

### 1. Create the Access application

- Open https://dash.cloudflare.com → pick the `antiek.ai` zone
- Left sidebar: **Zero Trust** → **Access** → **Applications** →
  **Add an application**
- Type: **Self-hosted**
- Application name: **Antiek**
- Session duration: **24 hours** (operator preference; shorten later if needed)

### 2. Application domains

Add all three so the cookie / JWT covers cross-origin fetches
from app to api:

| Subdomain | Domain | Path |
|---|---|---|
| (empty) | `antiek.ai` | `/` |
| `app` | `antiek.ai` | `/` |
| `api` | `antiek.ai` | `/` |

Cloudflare's Access cookie is set on the apex domain
(`.antiek.ai`) so it's sent to all three.

### 3. Identity provider

For single-operator setup, **One-time PIN** sent to your email is
the lowest-friction option:

- **Settings** → **Authentication** → **Login methods** → enable
  "One-time PIN"
- Back in the application: **Identity providers** → tick
  **One-time PIN**

Sprint 19+ when there are more users: swap to Google / Microsoft
SSO. Same machinery; different IdP.

### 4. Access policy

- **Policies** tab → **Add a policy**
- Policy name: `operator-only`
- Action: **Allow**
- **Include**: **Emails** → enter `ftn208@nyu.edu` (or whichever
  email you authenticate with)
- Save

### 5. Substrate env vars

On the Hetzner VM, append to `/etc/antiek/secrets.env`:

```
ANTIEK_OPERATOR_EMAIL=ftn208@nyu.edu
```

(Leave `ANTIEK_OPERATOR_TOKEN` set too — that's the machine path
for probes and CI. Both env vars together = both paths active.)

Restart:

```
sudo systemctl restart antiek
```

### 6. Cloudflare Pages env cleanup (optional but recommended)

The Pages project no longer needs `VITE_OPERATOR_TOKEN`. Remove
it to avoid leaving an unused secret around:

- Pages → **antiek** project → **Settings** → **Environment Variables**
- **Production** tab → delete `VITE_OPERATOR_TOKEN`
- Trigger a rebuild (Deployments tab → Retry latest deployment)
  to pick up the new code that doesn't read it.

### 7. Verify

- Browse to `https://antiek.ai` in an incognito window.
- Cloudflare Access prompts for your email. Enter `ftn208@nyu.edu`,
  receive the PIN, paste it in.
- Page loads. Open devtools → Network tab → any `/api.antiek.ai`
  request should have:
  - `cookie: CF_Authorization=...`
  - response is 200 (not 401)
- `curl https://api.antiek.ai/health` from anywhere — should
  return 200 (`/health` is always open).
- `curl https://api.antiek.ai/investigations` — should return 401
  (no auth from a non-browser non-bearer caller).
- `curl -H "Authorization: Bearer $ANTIEK_OPERATOR_TOKEN" https://api.antiek.ai/investigations` —
  should return 200 (bearer path).

---

## Failure modes + fixes

**`/api.antiek.ai` still 401s from browser after Access setup**:
The cross-origin cookie isn't being sent. Two checks:
- The web app's fetch uses `credentials: "include"` (it does, in
  `apps/reading/src/lib/api.ts:apiFetch`). If forked, verify.
- All three subdomains are in the SAME Access application
  (step 2). Separate applications = separate JWTs = no cookie
  sharing.

**Probe scripts (smoke, health) suddenly 401**:
Their `ANTIEK_OPERATOR_TOKEN` env isn't reaching the bearer
header. Check `tools/ops/smoke_investigation.sh` and
`tools/ops/health_probe.sh`: they read the env var directly.
Sourcing your shell's env or passing it explicitly fixes it.

**`Cf-Access-Authenticated-User-Email` header could be spoofed**
(security-critical):
By default the substrate trusts this header on any request. A
direct caller to the Hetzner IP (bypassing Cloudflare) could
inject it. Mitigations:
- **(immediate)** rely on the bearer path as the real gate; treat
  the email path as defense-in-depth.
- **(H4.6 follow-on, not yet shipped)** restrict Caddy on Hetzner
  to accept traffic only from Cloudflare's published edge IPs.
  See https://www.cloudflare.com/ips/ for the current list.
- **(stronger, deferred)** validate the
  `Cf-Access-Jwt-Assertion` header via Cloudflare's JWKS. Requires
  PyJWT + JWKS-fetch caching; not warranted at single-operator
  scale today.

---

## Rotation

The operator email is the credential. Rotation = update the email
in step 4 (Access policy) AND step 5 (substrate env). The bearer
token rotation continues to be the quarterly-manual flow.
