# Auth failure-mode matrix

**Version:** 2026-06-02  
**Program:** ANT-AUTH-DIAG (login diagnostic precision)  
**Keystone sprint:** SPR-01  
**TypeScript union:** `apps/reading/src/lib/authDiagnosticCodes.ts`  
**Contract sources:** `apps/reading/src/lib/auth.tsx`, `interfaces/research/api/auth.py`, `interfaces/research/api/app.py`

`failure_id` values in this document are **immutable** once shipped. New modes require a matrix version bump and a union update in `authDiagnosticCodes.ts`.

---

## Layer taxonomy

| Layer | Meaning | Typical owner |
|-------|---------|---------------|
| **A** | Transport — browser/network cannot complete a well-formed HTTP exchange with the API | SPR-02 (client), local dev setup |
| **B** | Policy — HTTP succeeds; auth policy or token semantics explain the symptom | SPR-03 (callback), SPR-04 (probe), operator config |
| **OPS** | Operations — deployment, edge, cookie domain, middleware/env drift | SPR-03, SPR-04, SPR-06, operator runbooks |

---

## Impossibility lemma (enumeration guard vs transport)

**Claim:** `B-POLICY-ALLOWLIST-SILENT` **cannot** produce the Login submit symptom **"Failed to fetch"**.

**Proof sketch:**

1. **Backend** — For every syntactically valid email, `POST /auth/request` returns HTTP **200** with `{"sent": true}` whether or not the address is allowlisted. Non-allowlisted requests are a silent no-op; they never throw and never return a non-2xx status for policy denial.

```236:261:interfaces/research/api/auth.py
    async def auth_request(payload: AuthRequestPayload) -> AuthRequestResponse:
        email = payload.email.strip().lower()
        ...
        if email in allowlist:
            ...
        # Non-allowlisted: silently no-op. Constant-time-ish: the
        # branch difference is unavoidable but the response is
        # identical, which is what enumeration protection turns on.
        return AuthRequestResponse(sent=True)
```

2. **Frontend** — `requestMagicLink` only surfaces **"Failed to fetch"** (or another transport message) when `apiFetch` **throws** before a normal HTTP response is handled. A completed `fetch` with `r.ok === true` always returns `{ kind: "sent" }` and shows **"Check your email"**, not a transport error.

```101:129:apps/reading/src/lib/auth.tsx
export async function requestMagicLink(email: string, nextPath: string = "/"): Promise<AuthRequestResult> {
  try {
    const r = await apiFetch(authUrl("/auth/request"), { ... });
    if (r.ok) {
      return { kind: "sent" };
    }
    ...
  } catch (err) {
    return {
      kind: "error",
      code: "network_error",
      message: err instanceof Error ? err.message : "Network error.",
    };
  }
}
```

3. **Conclusion** — Allowlist miss is indistinguishable on the wire from allowlist hit at request time (both 200 + `sent: true`). Therefore an operator who sees **"Failed to fetch"** on Login submit must diagnose **Layer A** (or a rare non-allowlist HTTP error such as **503** email delivery), **not** allowlist silence.

**Corollary:** Do not add a `not_allowlisted` response code on `/auth/request`; that would violate the enumeration guard and still would not explain transport-level `TypeError: Failed to fetch`.

---

## Failure-mode table

| failure_id | layer | user_symptom | http_status | discriminant command | expected output | fix_owner sprint |
|------------|-------|--------------|-------------|----------------------|-----------------|------------------|
| `A-TRANSPORT-FETCH` | A | Login shows **Failed to fetch** (or `network_error`) after submit; no HTTP body parsed | *(none — fetch throws)* | `curl -sS -o /tmp/auth_req.json -w "%{http_code}\n" -X POST "${API:-https://api.antiek.ai}/auth/request" -H "Content-Type: application/json" -d '{"email":"probe@example.com"}' && cat /tmp/auth_req.json` | `200` and `{"sent":true}` while browser still fails → Layer A (VPN, extension, offline, wrong `VITE_API_BASE_URL`, DNS) | SPR-02 |
| `A-TRANSPORT-LOCAL-BACKEND` | A | Dev Login **Failed to fetch** / connection refused; Vite :5173 up | *(connection refused)* | `curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/health` then `curl -sS -X POST http://127.0.0.1:5173/auth/request -H "Content-Type: application/json" -d '{"email":"dev@test"}'` | First command not `200`, or second fails while health is down → start FastAPI on :8000; confirm `vite.config.ts` proxies `/auth` → `localhost:8000` | SPR-02 |
| `A-TRANSPORT-CORS` | A | Browser console: CORS preflight failed; Login **Failed to fetch** | *(preflight blocked)* | From devtools Network: `OPTIONS` to API origin with `Origin: https://antiek.ai` (or dev origin). Compare: `curl -sS -D- -o /dev/null -X OPTIONS "${API:-https://api.antiek.ai}/auth/request" -H "Origin: https://antiek.ai" -H "Access-Control-Request-Method: POST"` | Missing `access-control-allow-origin` or 4xx on OPTIONS while POST works from curl → fix API CORS / Pages build `VITE_API_BASE_URL` pairing | SPR-02 |
| `B-POLICY-ALLOWLIST-SILENT` | B | **Check your email** but no message arrives (allowlisted expectation) | `200` | `curl -sS -X POST "${API:-https://api.antiek.ai}/auth/request" -H "Content-Type: application/json" -d '{"email":"NOT_IN_ALLOWLIST@example.com"}'` | `{"sent":true}` — **cannot** explain UI **Failed to fetch** (see impossibility lemma). Fix: add email to `ANTIEK_OPERATOR_EMAIL` on server; re-request | SPR-04, operator |
| `B-POLICY-EMAIL-503` | B | Login error text from API; Resend/provider broken for allowlisted address | `503` | `curl -sS -w "\n%{http_code}\n" -X POST "${API:-https://api.antiek.ai}/auth/request" -H "Content-Type: application/json" -d '{"email":"ALLOWLISTED_EMAIL"}'` *(substitute real allowlisted operator email)* | Body contains `"code":"email_delivery_failed"` and HTTP `503` | Operator (Resend keys), SPR-04 |
| `B-POLICY-CALLBACK-EXPIRED` | B | Magic link click shows JSON: link expired | `400` | `curl -sS "${API:-https://api.antiek.ai}/auth/callback?token=EXPIRED_TOKEN&next=/"` *(token older than 15m or test fixture)* | `{"error":{"code":"magic_link_expired",...}}` | SPR-03 |
| `B-POLICY-CALLBACK-INVALID` | B | Magic link click shows JSON: link not valid | `400` | `curl -sS "${API:-https://api.antiek.ai}/auth/callback?token=not.valid.token&next=/"` | `{"error":{"code":"magic_link_invalid",...}}` | SPR-03 |
| `B-POLICY-CALLBACK-NOT-AUTH` | B | Valid-looking link; JSON not authorized (allowlist changed after mint) | `403` | Mint link for email then remove email from `ANTIEK_OPERATOR_EMAIL` before callback; or use test `tests/test_magic_link_auth.py` callback cases | `{"error":{"code":"not_authorized",...}}` | SPR-03, SPR-06 |
| `OPS-INGEST-502` | OPS | **Unrelated to Login submit** — API unhealthy / 502 during corpus ingest window because `antiek.service` was stopped | `502` / connection errors on `/health` | `ssh hetzner 'systemctl is-active antiek.service; curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health'` | `inactive` or non-200 health during ingest → **do not** stop `antiek.service` for ingest body (`infrastructure/runbooks/corpus-mass-ingest.md` Preflight 4) | Operator |
| `OPS-CF-403` | OPS | `curl` / probe gets **403**; browser Login may work | `403` | `curl -sS -o /dev/null -w "%{http_code}\n" -A "antiek-auth-probe/1.0" "${API:-https://api.antiek.ai}/health"` vs `curl -sS -o /dev/null -w "%{http_code}\n" -A "Mozilla/5.0" "${API:-https://api.antiek.ai}/health"` | Non-browser UA blocked at Cloudflare; browser path OK → adjust WAF / use browser-like UA in probes only | Operator |
| `OPS-COOKIE-DOMAIN` | OPS | Callback appears to succeed but `/auth/me` is 401 on Pages origin | `401` on `/auth/me` | After callback: `curl -sS -b cookies.txt -c cookies.txt "${API:-https://api.antiek.ai}/auth/callback?token=VALID&next=/" -D - -o /dev/null` then `curl -sS -b cookies.txt "${API:-https://api.antiek.ai}/auth/me"` from app origin with `credentials: include` | `Set-Cookie` without `Domain=.antiek.ai` (or wrong domain) → set `ANTIEK_COOKIE_DOMAIN` per `infrastructure/runbooks/magic-link-auth.md` | SPR-03, operator |
| `OPS-REDIRECT-API-HOST` | OPS | After magic link, browser lands on **api.antiek.ai** (JSON/404) not app | `302` | `curl -sS -D- -o /dev/null "${API:-https://api.antiek.ai}/auth/callback?token=VALID&next=/"` | `Location: https://api.antiek.ai/...` instead of `https://antiek.ai/...` → set `ANTIEK_FRONTEND_BASE_URL` or `ANTIEK_PUBLIC_BASE_URL` (`auth.py` `_frontend_base_url`) | SPR-03, operator |
| `OPS-MIDDLEWARE-COMMA` | OPS | *(fixed SPR-06)* Was: magic link + cookie OK but API 401 when env listed multiple comma-separated emails | `401` | Set `ANTIEK_OPERATOR_EMAIL=alice@x.com,bob@y.com`; sign in as `bob@y.com`; `curl -sS -b c.txt "${API:-https://api.antiek.ai}/auth/me"` | **Fixed:** `operator_allowlist_from_env()` shared by `auth.py` + `app.py` middleware (session cookie + CF Access paths). Regression: `tests/test_magic_link_auth.py::test_multi_email_allowlist_middleware_accepts_both_operators` | SPR-06 ✓ |

---

## Log signatures (quick grep)

| failure_id | Server / client signal |
|------------|------------------------|
| `A-TRANSPORT-FETCH` | Browser: `TypeError: Failed to fetch`; client `code: network_error` |
| `A-TRANSPORT-LOCAL-BACKEND` | `ECONNREFUSED 127.0.0.1:8000`; Vite proxy error on `/auth/request` |
| `A-TRANSPORT-CORS` | `Access to fetch ... blocked by CORS policy` |
| `B-POLICY-ALLOWLIST-SILENT` | `POST /auth/request` 200, no outbound email log for address |
| `B-POLICY-EMAIL-503` | `email_delivery_failed` in 503 body |
| `B-POLICY-CALLBACK-EXPIRED` | `magic_link_expired` |
| `B-POLICY-CALLBACK-INVALID` | `magic_link_invalid` |
| `B-POLICY-CALLBACK-NOT-AUTH` | `not_authorized` |
| `OPS-INGEST-502` | `systemctl` inactive `antiek.service` during ingest |
| `OPS-CF-403` | Cloudflare challenge / 403 with non-browser UA |
| `OPS-COOKIE-DOMAIN` | Cookie present on API host only; missing on Pages |
| `OPS-REDIRECT-API-HOST` | `Location` host is API not frontend |
| `OPS-MIDDLEWARE-COMMA` | *(historical)* Cookie email not in comma-split allowlist — fixed SPR-06 |

---

## False positives

| failure_id | Common misdiagnosis |
|------------|---------------------|
| `B-POLICY-ALLOWLIST-SILENT` | Blamed when UI shows **Failed to fetch** — ruled out by impossibility lemma |
| `A-TRANSPORT-FETCH` | Blamed when curl from laptop works but browser uses corporate DNS/VPN |
| `OPS-INGEST-502` | Blamed for Login when only ingest playbook stopped the service |
| `OPS-MIDDLEWARE-COMMA` | Blamed for single-email allowlist (no comma in env) |

---

## Evidence snapshots (2026-06-02)

**`B-POLICY-ALLOWLIST-SILENT`** — live probe (non-allowlisted address):

```text
$ curl -sS -o /dev/null -w "%{http_code}" -X POST "https://api.antiek.ai/auth/request" \
  -H "Content-Type: application/json" -d '{"email":"not-on-allowlist@example.com"}'
200
$ curl -sS -X POST "https://api.antiek.ai/auth/request" \
  -H "Content-Type: application/json" -d '{"email":"not-on-allowlist@example.com"}'
{"sent":true}
```

**`A-TRANSPORT-FETCH`** — client path when `fetch` throws (no HTTP status):

```text
// apps/reading/src/lib/auth.tsx L123-128 — err.message is often "Failed to fetch"
catch (err) {
  return { kind: "error", code: "network_error", message: err instanceof Error ? err.message : "Network error." };
}
```

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-02 | SPR-01 initial matrix: 13 `failure_id` rows, impossibility lemma, Layer A/B/OPS |