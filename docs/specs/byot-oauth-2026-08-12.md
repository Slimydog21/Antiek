# BYOT OAuth Expansion — Grok / OpenAI / Anthropic

**Date:** 2026-08-12
**Status:** Implemented (modules + tests); **NOT go-live** — operator must register OAuth apps
**Related:** [`docs/decisions/provider-consumer-oauth-boundary.md`](../decisions/provider-consumer-oauth-boundary.md)

---

## Overview

Antiek is BYOT (bring-your-own-token). The existing Grok OAuth module
(`runtime/byok/grok_oauth.py`) implements a device-code flow (RFC 8628) against
`https://auth.x.ai` using the `grok-cli` public client. This spec documents the
expansion to three provider OAuth flows and the two new modules
(`runtime/byok/openai_oauth.py`, `runtime/byok/anthropic_oauth.py`) that bring
OpenAI and Anthropic OAuth onboarding into the same BYOT architecture.

---

## What T3Code does (and what Antiek should adopt)

[T3Code](https://github.com/pingdotgg/t3code) (audited at
`52e5a75a872289040df85621d7a82ea9cba05182`) does **not** implement OAuth token
exchanges itself. It delegates authentication and provider traffic to official
Codex and Claude CLI processes:

- **Codex (OpenAI):** T3Code spawns the official `codex app-server` process
  (`@openai/codex`). Auth lives in `CODEX_HOME/auth.json`, managed entirely by
  the official Codex CLI. T3Code creates a per-instance "shadow home" with
  symlinks for isolation but leaves `auth.json` as a private real file.
- **Claude (Anthropic):** T3Code uses the `@anthropic-ai/claude-agent-sdk` and
  spawns the Claude binary. Auth is isolated via `CLAUDE_CONFIG_DIR`, leaving
  the keychain intact.

**What Antiek should adopt from T3Code:**
1. **Per-instance HOME isolation** — each user's credentials live in a separate
   directory, not a shared one. Antiek's BYOK store already achieves this via
   owner-scoped `cred_id` + SecretBox key binding (binding version 3).
2. **Official CLI credential custody** — T3Code never reads or copies `auth.json`
   itself; the official process retains credential custody. Antiek's OAuth
   modules replicate this principle: the token exchange happens once at
   onboarding, then the tokens are encrypted at rest. The refresher calls the
   provider's token endpoint directly.
3. **Origin-pinned endpoints** — T3Code only connects to provider-owned HTTPS
   endpoints. Antiek's `validate_oauth_endpoint()` enforces this per provider.

**What Antiek does differently (by design):**
Antiek implements the OAuth token exchange **in-process** (httpx) rather than
delegating to a spawned CLI process. This gives Antiek direct control over the
token lifecycle, refresh cadence, and encrypted storage — at the cost of
maintaining the OAuth client registration. T3Code avoids this cost by letting
the official CLI own it.

---

## The three OAuth flows

### 1. Grok (xAI) — Device-Code Flow (RFC 8628)

**Module:** `runtime/byok/grok_oauth.py`
**Client:** `grok-cli` public client (`b1a00492-…`)
**Status:** Pre-existing, production-ready.

| Property | Value |
|---|---|
| Flow | Device-code (RFC 8628) |
| Authorization endpoint | `https://auth.x.ai/oauth2/device/code` |
| Token endpoint | `https://auth.x.ai/oauth2/token` |
| Client ID | `b1a00492-073a-47ea-816f-4c329264a828` |
| Scopes | `openid profile email offline_access grok-cli:access api:access` |
| Origin pin | `*.x.ai` |
| Expiry | JWT `exp` claim (adaptive skew) |
| Redirect | None (device code entered in browser) |

### 2. OpenAI (ChatGPT) — PKCE Authorization-Code Flow

**Module:** `runtime/byok/openai_oauth.py`
**Client:** Codex CLI public client (`app_EMoamEEZ73f0CkXaXp7hrann`)

| Property | Value |
|---|---|
| Flow | PKCE authorization-code (RFC 7636 + RFC 6749 §4.1) |
| Authorization endpoint | `https://auth.openai.com/oauth/authorize` |
| Token endpoint | `https://auth.openai.com/oauth/token` |
| Revoke endpoint | `https://auth.openai.com/oauth/revoke` |
| Client ID | `app_EMoamEEZ73f0CkXaXp7hrann` |
| Scopes | `openid profile email offline_access api.connectors.read api.connectors.invoke` |
| Origin pin | `*.openai.com` |
| Expiry | JWT `exp` claim (adaptive skew) |
| Redirect URI | `http://localhost:<port>/auth/callback` (default port 1455, fallback 1457) |
| Token exchange | form-POST (`application/x-www-form-urlencoded`) |
| PKCE method | S256 |

**Onboarding sequence:**
1. `generate_pkce_pair()` → 64-byte verifier → base64url (no padding); challenge = base64url(SHA256(verifier)).
2. `generate_state()` → 32-byte URL-safe random CSRF nonce.
3. `build_authorize_url(redirect_uri, pkce, state)` → user opens in browser.
4. User signs in to ChatGPT; browser redirects to `http://localhost:<port>/auth/callback?code=…&state=…`.
5. `exchange_authorization_code(code, pkce, redirect_uri)` → form-POST to token endpoint.
6. `store_openai_tokens(tokens, owner_user_id)` → encrypted at rest in BYOK store.
7. `refresh_openai_token(refresh_token)` → form-POST when token nears expiry.

### 3. Anthropic (Claude) — PKCE Authorization-Code Flow (Hosted Redirect)

**Module:** `runtime/byok/anthropic_oauth.py`
**Client:** Claude Code OAuth client (`9d1c250a-e61b-44d9-88ed-5944d1962f5e`)

| Property | Value |
|---|---|
| Flow | PKCE authorization-code (RFC 7636 + RFC 6749 §4.1) |
| Authorization endpoint | `https://claude.ai/oauth/authorize` |
| Token endpoint | `https://console.anthropic.com/v1/oauth/token` |
| Client ID | `9d1c250a-e61b-44d9-88ed-5944d1962f5e` |
| Scopes | `org:create_api_key user:profile user:inference` |
| Origin pin | `*.anthropic.com` |
| Expiry | `expires_in` (opaque token, not JWT) |
| Redirect URI | `https://console.anthropic.com/oauth/code/callback` (hosted) |
| Token exchange | JSON POST (`application/json`, `User-Agent: anthropic`) |
| PKCE method | S256 |
| State | `code_verifier` (Claude Code convention — verifier doubles as CSRF nonce) |

**Key difference from OpenAI:** The redirect target is Anthropic's *hosted*
callback page, not a local loopback server. After the user signs in, Anthropic
displays the authorization code on the callback page. The user copies it back
into the Antiek CLI, which then exchanges it for tokens.

**Onboarding sequence:**
1. `generate_pkce_pair()` → 32-byte verifier → base64url (no padding); challenge = base64url(SHA256(verifier)).
2. `build_authorize_url(pkce)` → `state = pkce.code_verifier` (Claude Code convention).
3. User opens URL in browser, signs in to Anthropic, approves scopes.
4. Anthropic redirects to hosted callback page, displays the authorization code.
5. User copies code back to Antiek CLI.
6. `exchange_authorization_code(code, pkce)` → JSON POST to token endpoint.
7. `store_anthropic_tokens(tokens, owner_user_id)` → encrypted at rest in BYOK store.
8. `refresh_anthropic_token(refresh_token)` → JSON POST when token nears expiry.

---

## Security properties

All three modules share the same security model, inherited from `grok_oauth.py`:

### PKCE (RFC 7636)
OpenAI and Anthropic flows use S256 PKCE: a random `code_verifier` and its
SHA-256 hash (`code_challenge`) are sent with the authorize request. The token
exchange requires the original `code_verifier`, so a intercepted authorization
code alone is useless. Grok does not need PKCE (device-code flow inherently
binds the device code to the polling client).

### Token encryption at rest
Tokens are stored via `runtime.byok.store.store_credential()`, which uses
libsodium `SecretBox` (XSalsa20-Poly1305) with a fresh 24-byte nonce per
credential. The master key lives in a separate `0600` key file, never in the
encrypted artifact. Binding version 3 ties the SecretBox key to the credential's
identity (`account_handle`, `cred_id`, `owner_user_id`, `pipeline_kind`), so
tampering with any metadata field makes the ciphertext undecryptable.

### Owner scoping
Each credential is scoped to a single `owner_user_id`. The store's binding
version 3 ensures user A's SecretBox key cannot decrypt user B's ciphertext
(even if an attacker swaps `owner_user_id` in the artifact). The
`find_*_cred_id()` functions return only the credential for the specified user.

### No logging of secrets
Token dataclasses (`XaiTokens`, `OpenAiTokens`, `AnthropicTokens`) have
`__repr__` / `__str__` that REDACT all token material. Error messages carry
only server-provided detail, never the refresh token. The store module never
passes plaintext to any logger, `print`, or `emit_typed`.

### Origin-pin validators
`validate_oauth_endpoint()` rejects any URL that is not `https` and under the
provider's domain (`*.x.ai`, `*.openai.com`, `*.anthropic.com`). Similar-host
attacks (`openai.com.evil.com`, `auth-x.ai`) are rejected.

### Failure taxonomy
HTTP errors are classified into three BYOT UX states:
- **Tier denied** (403): terminal — suggest pasting an API key.
- **Re-login required** (400/401/`invalid_grant`): terminal — quarantine tokens, require re-onboard.
- **Transient** (429/5xx): retryable — never quarantine.

---

## Go-live checklist

> **⚠️ The operator MUST register OAuth applications before these flows can be used in production.**
> The modules currently reuse first-party CLI client registrations (Codex CLI for OpenAI,
> Claude Code for Anthropic). These are **not** Antiek's own registrations. Go-live requires
> dedicated client registrations per the ADR's revisit evidence criteria.

### OpenAI go-live

- [ ] **Register an OAuth application** at [platform.openai.com](https://platform.openai.com)
  → Settings → API → OAuth applications (or equivalent registration surface).
- [ ] **Obtain `client_id` and `client_secret`** for the Antiek application.
- [ ] **Register redirect URIs**: the production callback URL(s) that Antiek's
      onboarding server will serve (e.g. `https://antiek.example.com/oauth/openai/callback`).
- [ ] **Confirm scopes**: the scopes `openid profile email offline_access` plus any
      API-access scopes OpenAI grants to third-party clients. The current
      `api.connectors.read api.connectors.invoke` scopes are Codex-CLI-specific
      and may not be available to a third-party registration.
- [ ] **Verify refresh/revoke semantics**: confirm token rotation behavior and
      revocation endpoint access.
- [ ] **Update `OPENAI_OAUTH_CLIENT_ID`** in `runtime/byok/openai_oauth.py`
      (or via environment override) to the registered client_id.
- [ ] **Live test**: complete one full onboarding → inference → refresh → revoke
      cycle against a staging tenant.

### Anthropic go-live

- [ ] **Register an OAuth application** at [console.anthropic.com](https://console.anthropic.com)
  → Settings → OAuth (or equivalent registration surface).
- [ ] **Obtain `client_id`** (and `client_secret` if Anthropic requires a confidential
      client for production) for the Antiek application.
- [ ] **Register redirect URIs**: `https://console.anthropic.com/oauth/code/callback`
      is Anthropic's hosted callback; for a production deployment, confirm whether
      Anthropic supports a custom redirect URI or whether the hosted copy-back
      flow is the only option.
- [ ] **Confirm scopes**: `org:create_api_key user:profile user:inference` — verify
      these are the correct scopes for a third-party client.
- [ ] **Review Anthropic's credential-use policy**: Anthropic explicitly states that
      third parties may not offer Claude.ai login or route requests through
      subscription credentials. Confirm that this OAuth flow is permitted for
      your use case (see the ADR's revisit evidence criteria).
- [ ] **Update `ANTHROPIC_OAUTH_CLIENT_ID`** in `runtime/byok/anthropic_oauth.py`
      (or via environment override) to the registered client_id.
- [ ] **Live test**: complete one full onboarding → inference → refresh → revoke
      cycle against a staging tenant.

### Shared infrastructure

- [ ] **BYOK master key**: ensure `$ANTIEK_BYOK_KEY_FILE` points to a `0600` key
      file accessible only to the Antiek process user. The key is never committed.
- [ ] **HTTPS for onboarding callbacks**: OpenAI uses a loopback redirect
      (`http://localhost:<port>/auth/callback`); this is only safe for local
      CLI onboarding. For a web deployment, the callback must be HTTPS and the
      redirect URI must match what is registered.
- [ ] **Token refresh scheduler**: wire `refresh_openai_token()` /
      `refresh_anthropic_token()` into the existing artifact-locked refresher
      (the same mechanism Grok uses).
- [ ] **Quarantine on auth failure**: ensure `quarantine_openai_tokens()` /
      `quarantine_anthropic_tokens()` are called when the server returns 400/401
      (`invalid_grant`), exactly as Grok does.

---

## Module API summary

Each module exposes the same surface (mirroring `grok_oauth.py`):

| Function | Grok | OpenAI | Anthropic |
|---|---|---|---|
| `generate_pkce_pair()` | — | ✓ | ✓ |
| `generate_state()` | — | ✓ | — (verifier = state) |
| `build_authorize_url()` | — | ✓ | ✓ |
| `request_device_code()` / `exchange_authorization_code()` | ✓ | ✓ | ✓ |
| `poll_device_token()` | ✓ | — | — |
| `refresh_*_token()` | ✓ | ✓ | ✓ |
| `validate_oauth_endpoint()` | ✓ | ✓ | ✓ |
| `compute_expires_at()` | ✓ (JWT exp) | ✓ (JWT exp) | ✓ (expires_in) |
| `store_*_tokens()` | ✓ | ✓ | ✓ |
| `load_*_tokens()` | ✓ | ✓ | ✓ |
| `find_*_cred_id()` | ✓ | ✓ | ✓ |
| `delete_*_tokens()` | ✓ | ✓ | ✓ |
| `quarantine_*_tokens()` | ✓ | ✓ | ✓ |

---

## Sources

- OpenAI Codex CLI source: `https://github.com/openai/codex` (`codex-rs/login/`)
- Codex CLIENT_ID: `app_EMoamEEZ73f0CkXaXp7hrann` (from `codex-rs/login/src/auth/manager.rs:1655`)
- Codex token endpoint: `https://auth.openai.com/oauth/token` (from `codex-rs/login/src/auth/manager.rs:192`)
- Anthropic OAuth flow: `https://gist.github.com/cedws/3a24b2c7569bb610e24aa90dd217d9f2`
- Anthropic client ID: `9d1c250a-e61b-44d9-88ed-5944d1962f5e`
- Anthropic token endpoint: `https://console.anthropic.com/v1/oauth/token`
- T3Code: `https://github.com/pingdotgg/t3code` (audited at `52e5a75a872289040df85621d7a82ea9cba05182`)
- Antiek ADR: [`docs/decisions/provider-consumer-oauth-boundary.md`](../decisions/provider-consumer-oauth-boundary.md)
