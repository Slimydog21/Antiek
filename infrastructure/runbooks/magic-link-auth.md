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
# Two hosts, two variables: the app is on Pages, the callback handler is
# server-side on the API, so the emailed link must carry the API origin.
ANTIEK_PUBLIC_BASE_URL=https://antiek.ai
ANTIEK_API_BASE_URL=https://api.antiek.ai
ANTIEK_COOKIE_DOMAIN=.antiek.ai
ANTIEK_CORS_ORIGINS=https://antiek.ai,https://www.antiek.ai
# Defaults shown explicitly for operational legibility:
ANTIEK_WEBAUTHN_RP_ID=antiek.ai
ANTIEK_WEBAUTHN_ORIGINS=https://antiek.ai,https://www.antiek.ai
ANTIEK_PASSKEY_STORE=/home/antiek/.antiek/auth/passkeys.json
```

`ANTIEK_API_BASE_URL` is the line that is not decoration. `_api_base_url()`
in `interfaces/research/api/auth.py` resolves `ANTIEK_API_BASE_URL` →
`ANTIEK_PUBLIC_BASE_URL` → `https://antiek.ai`, so setting only the public
base builds every emailed link as `https://antiek.ai/auth/callback?token=…`.
That host answers `200` with the Pages SPA shell and the React router has no
`/auth/callback` route, so the token is never exchanged and the operator
lands on a blank page; `https://api.antiek.ai/auth/callback` is the host that
actually `302`s. `ANTIEK_COOKIE_DOMAIN=.antiek.ai` is what then lets the
cookie the API mints cross back to the Pages origin. Both behaviours are
pinned by `tests/test_magic_link_auth.py`
(`test_magic_link_uses_api_base_when_set`,
`test_cookie_domain_set_when_env_configured`), and
`apps/reading/playwright.config.ts` sets the same two-host pair for its
`passkey-real` project — the repo already knows the shape this block was
missing.

The `www` entry in `ANTIEK_WEBAUTHN_ORIGINS` is not padding either. WebAuthn
compares the *exact* page origin, Cloudflare Pages serves the same SPA on
`antiek.ai` and `www.antiek.ai`, and both hosts are live. The code default in
`substrate/auth/passkeys.py` `_origins()` is already
`["https://antiek.ai", "https://www.antiek.ai"]` — pinned by
`test_www_origin_in_webauthn_defaults` — so writing the apex alone *narrows*
the default and silently disables passkey registration and unlock for anyone
who landed on `www`, discovered at the moment someone cannot log in. Dropping
the line entirely is equally correct; what is wrong is writing half of it.

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

**Known false alarm — read this before you act on a red stage.** As of
2026-09-22 the `auth_request_dry_run` stage reports `"pass": false` against a
perfectly healthy production, so the probe exits `1` when nothing is wrong.
The tool still asserts exact dict equality — `parsed == {"sent": True}` at
`tools/auth_probe.py:186` — while `POST /auth/request` has returned three
required fields since commit `9731cc578` (`sent`, `attempt_id`,
`claim_secret`), and that commit is an ancestor of the deployed `build_sha`.
The line you will see is:

```
{"name": "auth_request_dry_run", "layer": "B", "pass": false, "http_code": 200,
 "detail": "expected 200 {\"sent\": true}, got http=200 body={'sent': True, 'attempt_id': '…', 'claim_secret': '…'}"}
```

Treat a lone `auth_request_dry_run` failure carrying `"http_code": 200` and a
body whose `sent` is `True` as green, and read the other four stages — those
still carry signal. Anything else in that stage (a non-200, a missing `sent`,
or a `device_code` key appearing in the body) is a real finding. The drift
went unnoticed because `tools/tests/test_auth_probe.py` covers only the
passkey stage; the durable repair belongs in the tool, not in this runbook —
relax the assertion to a superset check (`parsed.get("sent") is True and
"device_code" not in parsed`) and add a case that feeds the real three-key
body.

Composes with `tools/prod_parity/check.py` on deploy (SHA + flywheel);
run auth stages after parity when `ANTIEK_API_BASE` is set or pass
`--auth-probe`:

```bash
python tools/prod_parity/check.py --url https://api.antiek.ai --auth-probe
```

The same stale assertion reaches this command and turns into a non-zero exit:
`run_auth_probe()` calls the probe's own `run_stages()` and returns `1` on any
failing stage, and `check.py` hands that straight back as the process exit
code. SHA and provider parity can both be green and the run will still exit
`1`. Until the tool is fixed, take parity on its own — with `ANTIEK_API_BASE`
unset, since a value there auto-enables the probe — and check auth by hand
with the curl assertion below:

```bash
python tools/prod_parity/check.py --url https://api.antiek.ai
```

#### Manual curl (same stages, piecemeal)

```bash
# Request a magic link to a non-allowlisted email — should silently no-op
curl -sX POST https://api.antiek.ai/auth/request \
  -H 'Content-Type: application/json' \
  -d '{"email":"random@example.com"}'
# Expect: {"sent": true, "attempt_id": "...", "claim_secret": "..."}
# attempt_id + claim_secret are the requesting device's handles on the
# approval; the 4-digit code is never in the response, only in the email.

# Request to the allowlisted operator email — should send via Resend
curl -sX POST https://api.antiek.ai/auth/request \
  -H 'Content-Type: application/json' \
  -d '{"email":"ftn208@nyu.edu"}'
# Expect: the same three fields; check inbox for the code + link
```

Both responses are identical by design — that is the enumeration guard — so
the useful assertion is on shape, not on a literal body. This version is
field-count-independent, survives the next response-model addition, and fails
loudly if the device code ever leaks into the JSON:

```bash
curl -sX POST https://api.antiek.ai/auth/request \
  -H 'Content-Type: application/json' \
  -d '{"email":"random@example.com"}' \
  | python3 -c 'import json,sys; b=json.load(sys.stdin); assert b["sent"] is True and "device_code" not in b, b; print("ok", sorted(b))'
# ok ['attempt_id', 'claim_secret', 'sent']
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
ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID=...  # the CF service-token path; safe to drop

# KEEP ANTIEK_OPERATOR_EMAIL — the magic-link allowlist reads it.
# KEEP ANTIEK_OPERATOR_TOKEN — the machine path for probes, CI, ansible.
# Never leave all three of EMAIL / TOKEN / SERVICE_TOKEN_CLIENT_ID empty.
```

Only the service-token variable goes. `ANTIEK_OPERATOR_EMAIL` stays, and the
failure mode if it does not is silent: `_allowlist()` in
`interfaces/research/api/auth.py` documents that an empty set "means deny
magic-link sends until the operator configures the env var", so `/auth/request`
keeps answering `sent: true` forever while no mail is ever sent — nothing the
client can distinguish from success. Emptying all three operator variables is
worse again: per the warning in
`infrastructure/ansible/templates/secrets.env.j2`, the middleware then takes
its bypass branch and "serves every route to every caller with a fully-scoped
operator identity".

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
export ANTIEK_API_BASE_URL=http://localhost:8000      # else the printed link aims at prod
export ANTIEK_FRONTEND_BASE_URL=http://localhost:5173  # post-callback redirect lands on Vite
./.venv/bin/uvicorn interfaces.research.api.app:app --workers 1
```

`ANTIEK_API_BASE_URL` is the export that makes this block work at all. Without
it `_api_base_url()` falls through to its `https://antiek.ai` default and the
link your local server prints is
`https://antiek.ai/auth/callback?token=…` — a token signed with the local
secret, aimed at production, on a host that has no callback route. It can
never complete a local sign-in. With both exports the link comes out as
`http://localhost:8000/auth/callback?token=…`, which is the same pair
`apps/reading/playwright.config.ts` sets for `passkey-real`. uvicorn's default
port is 8000, matching the curl below.

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
