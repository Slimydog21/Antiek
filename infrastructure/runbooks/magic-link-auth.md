# Email-code auth: owned login surface

**Status: live as of 2026-08-13.** Replaces Cloudflare Access at the
auth layer with an Antiek-issued session cookie. Email is the daily
path: the operator enters their address, receives a 4-digit code, and
types it into the browser — no link gymnastics, no second screen.
Passkey (WebAuthn) remains available as a secondary unlock for devices
that enrolled a credential; the server stores public credential
material only. Cloudflare Tunnel + DNS + TLS stay; only the auth
layer moves into the application.

This is the H6 cut-over. Cloudflare Access can be decommissioned at
the operator's pace — the substrate accepts both paths during the
overlap window.

For the historical Cloudflare Access setup (now superseded), see
`infrastructure/runbooks/cloudflare-access-setup.md`.

---

## Why this design

Three properties we want, beyond what Cloudflare Access gave us:

1. **Operator owns the login surface.** PostHog-style: the login
   page is in `apps/reading/src/modes/Login/` with the
   researcher's-notebook serif aesthetic per master-spec §5.5. No
   third-party login UI; no edge-injected logo.
2. **Multi-user-ready by construction.** The same code path that
   issues a cookie for the solo operator today (`user_id =
   "__operator__"`) issues a cookie for any future user with a
   real `user_id`. Sprint 22's multi-user pivot is the auth-
   provider side of the seam; the cookie + middleware shape stays.
3. **Email possession is the proof, and the code is email-only.**
   `POST /auth/request` never returns the 4-digit code in its JSON —
   the code exists only inside the delivered email, so typing it is
   genuine possession proof (5 wrong tries invalidate the attempt;
   both email surfaces are per-IP rate-limited). The two-device
   ceremony still exists (click the email link on the phone, the
   original browser opens itself), but the single-device code entry
   is the primary path. Passkey login remains a local public-key
   ceremony with no hosted-provider dependency; AgentMail is needed
   for bootstrap and recovery. Email delivery stays pluggable
   behind `ANTIEK_EMAIL_PROVIDER`.

The origin-verifiable middleware (substrate-side, see
`interfaces/research/api/app.py`) accepts ANY of:

- `ANTIEK_SESSION` cookie minted by `/auth/callback` (browser path)
- the complete `Cf-Access-Client-Id` + `Cf-Access-Client-Secret`
  service-token pair matching the server environment
- `Authorization: Bearer <token>` matching `ANTIEK_OPERATOR_TOKEN`
  (machine path; probes, CI, ansible health-checks)

`Cf-Access-Authenticated-User-Email` alone is never accepted. It is a
caller-controlled header at the origin unless an Access JWT is verified,
which this service does not currently implement.

The Antiek cookie is checked first. Once the operator signs in via the
owned flow, every subsequent request takes that path.

---

## Steps

### 1. Generate an auth secret

The secret signs both magic-link tokens and session cookies.
Rotating the secret invalidates every outstanding link + session,
which is the intentional kill switch.

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Save the output for step 3.

### 2. Provision a Resend account

Resend is the recommended sender — clean API, no SDK dep needed,
$0/mo at this volume. https://resend.com → sign up → API Keys →
Create API Key (server-side, full access). Resend will guide
through SPF + DKIM for `antiek.ai`; the magic-link emails will
land in inbox once DNS propagates (~10 min after Cloudflare DNS
updates).

If you prefer a different sender (SES, Postmark, Mailgun), see
"Switching email providers" below.

### 3. Substrate env vars on the Hetzner VM

Append to `/etc/antiek/secrets.env`:

```
ANTIEK_AUTH_SECRET=<the secret from step 1>
ANTIEK_OPERATOR_EMAIL=the@faisalnazer.com,ftn208@nyu.edu
ANTIEK_EMAIL_PROVIDER=resend
RESEND_API_KEY=<your Resend API key>
ANTIEK_PUBLIC_BASE_URL=https://antiek.ai
# Defaults shown explicitly for operational legibility:
ANTIEK_WEBAUTHN_RP_ID=antiek.ai
ANTIEK_WEBAUTHN_ORIGINS=https://antiek.ai
ANTIEK_PASSKEY_STORE=/home/antiek/.antiek/auth/passkeys.json
```

Keep `ANTIEK_OPERATOR_TOKEN` set too — that's the machine path for
probes and CI. All four paths together = full backward
compatibility during cutover.

Restart:

```
sudo systemctl restart antiek
```

### 4. Verify the API side directly

Before touching the web app, confirm the API issues + accepts a
session cookie.

#### Auth probe (staged Layer A/B check)

One command runs health → CORS preflight → `POST /auth/request`
(dry-run, non-allowlisted email by default) → public
`GET /auth/passkey/status` → `GET /auth/me` without cookie. The passkey
stage proves the route is reachable before login while credential counts stay
private. Each stage prints one JSON line (`name`, `layer`, `pass`,
`http_code`, `detail`). Exit `0` all pass, `1` any fail, `2` bad `--base-url`.

```bash
python tools/auth_probe.py --base-url https://api.antiek.ai
# Local uvicorn (Vite origin):
python tools/auth_probe.py --base-url http://127.0.0.1:8000 --origin http://localhost:5173
```

Composes with `tools/prod_parity/check.py` on deploy (SHA + flywheel);
run auth stages after parity when `ANTIEK_API_BASE` is set or pass
`--auth-probe`:

```bash
python tools/prod_parity/check.py --url https://api.antiek.ai --auth-probe
```

#### Manual curl (same stages, piecemeal)

```bash
# Request a magic link to a non-allowlisted email — should silently no-op
curl -sX POST https://api.antiek.ai/auth/request \
  -H 'Content-Type: application/json' \
  -d '{"email":"random@example.com"}'
# Expect: {"sent": true}

# Request to the allowlisted operator email — should send via Resend
curl -sX POST https://api.antiek.ai/auth/request \
  -H 'Content-Type: application/json' \
  -d '{"email":"ftn208@nyu.edu"}'
# Expect: {"sent": true}; check inbox for the link
```

Click the link from the inbox. On the first successful proof, Antiek pauses at
`/login?setup=passkey`, asks the device to save a passkey, then resumes the
original destination. Confirm the next logged-out visit offers **Unlock with
passkey** as the primary action. The passkey store lives under
`/home/antiek/.antiek/`, so the existing application-state backup includes it.

### 5. Cloudflare Pages — no changes needed

The web app builds the same way; `VITE_API_BASE_URL` is unchanged.
The Login route is part of the React bundle already; no env-var
add. Trigger a redeploy (Pages → Deployments → Retry latest) to
pick up the new auth code.

### 6. Decommission Cloudflare Access (optional, after verification)

Once you've signed in successfully via the new flow and used the
app for a day or two without issue, you can remove Cloudflare
Access entirely:

- Cloudflare dashboard → **Zero Trust** → **Access** → **Applications**
- Find the **Antiek** application → click into it → **Delete**
- The Access policy + identity providers can stay configured
  (no-op without a bound app), or delete them too. Cleaner to
  delete.
- Cloudflare Tunnel for `api.antiek.ai` stays — it's transport,
  not auth.

After deletion, you can drop the now-unused env vars:

```
# Remove from /etc/antiek/secrets.env after CF Access is deleted:
ANTIEK_OPERATOR_EMAIL=...  # still needed for the magic-link allowlist
ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID=...  # if you set this; safe to drop
```

Keep `ANTIEK_OPERATOR_EMAIL` — the magic-link allowlist reads it.

---

## Local development

The auth substrate boots without any env vars in tests and local
dev — `MockEmailProvider` prints the magic link to stdout where
the operator can copy it.

To exercise the flow locally:

```bash
export ANTIEK_AUTH_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
export ANTIEK_OPERATOR_EMAIL=the@faisalnazer.com,ftn208@nyu.edu
export ANTIEK_COOKIE_INSECURE=1  # so cookies work over http://
export ANTIEK_WEBAUTHN_RP_ID=localhost
export ANTIEK_WEBAUTHN_ORIGINS=http://localhost:5173
uvicorn interfaces.research.api.app:app --workers 1
```

In a second terminal:

```bash
curl -sX POST http://localhost:8000/auth/request \
  -H 'Content-Type: application/json' \
  -d '{"email":"ftn208@nyu.edu"}'
```

The uvicorn log will print the magic link payload. Copy + paste it
into a browser to complete sign-in.

---

## Switching email providers

`ANTIEK_EMAIL_PROVIDER=mock` (default) or `resend`. To add another
provider (SES, Postmark, Mailgun):

1. Add a class in `substrate/auth/email_provider.py` that
   implements the `EmailProvider` protocol (`name` + `send(email)`).
2. Update `get_email_provider()` to recognize the new
   `ANTIEK_EMAIL_PROVIDER` value.
3. Configure whichever env vars the new sender needs.

Each provider is a single file change; no other substrate code
knows which sender is in play.

---

## Rotation + revocation

- **Rotate the auth secret** to invalidate every outstanding link
  and session at once. Generate a new value (step 1), update
  `/etc/antiek/secrets.env`, restart. All users get bounced to
  `/login`.
- **Single-session logout** clears the cookie via
  `POST /auth/logout` (called by the React UI's sign-out button).
  Does NOT invalidate other browsers — those still hold valid
  cookies until they expire. For all-session logout, rotate the
  secret.
- **Passkey loss or replacement:** email recovery remains available from the
  collapsed recovery control on Login. After email proof, remove or archive
  `/home/antiek/.antiek/auth/passkeys.json` and register the replacement.
  Never copy a credential record between RP IDs or edit its public key.
- **TTLs**: magic-link tokens expire after 15 min;
  session cookies after 30 days. Both are checked at every
  verification; expiry can be tightened without a code change by
  passing `max_age_seconds` to the verify functions.

---

## Tests

The server flow is covered by `tests/test_magic_link_auth.py` and
`tests/test_passkey_auth.py`: one-shot challenges, public-key-only atomic
persistence, protected registration, logged-out authentication, session
issuance, middleware integration, and backward compatibility. The browser
branch and recovery states are covered by `apps/reading/e2e/login-magic-link.spec.ts`.

```
./.venv/bin/python -m pytest tests/test_magic_link_auth.py tests/test_passkey_auth.py -v
```

The browser-cryptography gate starts a real local FastAPI service plus Vite,
enrolls a credential in Chromium's virtual platform authenticator, clears the
session, and proves the next unlock succeeds without email:

```bash
cd apps/reading
npm run e2e:passkey
```

---

## Companion docs

- `infrastructure/runbooks/cloudflare-access-setup.md` — historical
  Cloudflare Access path (superseded but kept for reference during
  the cutover window)
- `infrastructure/SKILL.md` — production deployment manual
- `docs/master-product-spec.md` §5.5, §13.8 — design philosophy
  ("PostHog's design and UI philosophy IS Antiek's design
  philosophy")
