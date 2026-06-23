# Agent dev-login — temporary computer-use access (2026-06-03)

**Status:** Built + tested on branch `auth/agent-dev-login`. Net-new
route `GET /auth/dev-login`; disabled by default (404s unless
`ANTIEK_DEV_LOGIN_TOKEN` is set). Additive to the magic-link auth
module — no change to the four existing auth paths.

## Why

Coding/computer-use agents (Codex computer-use, Hermes default
computer-use) need to load `antiek.ai` and exercise the live UI for
product development + verification. The existing auth paths don't fit a
browser-driving agent:

- **Magic-link** needs an email round-trip the agent can't complete (it
  doesn't read the operator inbox).
- **`Authorization: Bearer $ANTIEK_OPERATOR_TOKEN`** works for scripted
  API/CLI callers, but a computer-use agent driving a real browser can't
  attach a request header to a normal page load.

A computer-use agent only knows how to *visit a URL and click*. This
route fills that gap: the agent navigates to one URL and is logged in.

## What it does

`GET /auth/dev-login?token=<T>&next=/`

- 404s unless **both** `ANTIEK_DEV_LOGIN_TOKEN` and `ANTIEK_AUTH_SECRET`
  are set — invisible (not merely forbidden) on any box that hasn't
  opted in.
- Constant-time-compares `token` against `ANTIEK_DEV_LOGIN_TOKEN`. Wrong
  or missing token → the same 404, so a probe gets no oracle.
- On match: mints the standard `ANTIEK_SESSION` cookie under the operator
  identity (so the existing middleware cookie path accepts it unchanged —
  single-operator invariant, the same assumption the magic-link path
  makes), then 302-redirects to the frontend (`ANTIEK_PUBLIC_BASE_URL` /
  `ANTIEK_FRONTEND_BASE_URL`, open-redirect-guarded `next`).
- Cookie TTL is **7 days** (shorter than the 30-day magic-link session) —
  a dev grant ages out on its own.

Implementation: `interfaces/research/api/auth.py` (route +
`_dev_login_token()` helper + constants); the path is added to
`_OPERATOR_AUTH_OPEN_PATHS` in `interfaces/research/api/app.py` so a
logged-out browser can reach the bootstrap, exactly like `/auth/callback`.
Tests: `tests/test_magic_link_auth.py` (disabled-404, wrong-token-404,
missing-token-404, requires-auth-secret, happy-path-authorizes-middleware,
open-redirect-guard).

## Scope + the reconsider-if line

This grants **full operator access**. It is a development / verification
convenience, **not** the scoped read-only public API. Treat the token
like a password.

- **Enable:** set `ANTIEK_DEV_LOGIN_TOKEN=<random>` in
  `/etc/antiek/secrets.env`, `systemctl restart antiek`.
- **Revoke:** unset the var (or rotate its value) and restart — no
  redeploy required. Rotating `ANTIEK_AUTH_SECRET` additionally kills
  every outstanding session.
- **Hygiene:** rotate the token after a verification session; a
  token-in-URL can land in server logs / referrers.

**Reconsider / retire when** the scoped public API + CLI (with per-key
auth, rate limits, and fee metering) lands — that supersedes this
stopgap. At that point delete the route and the env var. This decision
deliberately does *not* widen the auth surface beyond a single,
env-gated, revocable token, and does *not* touch the DuckDB single-writer
invariant or any §9 gating.
