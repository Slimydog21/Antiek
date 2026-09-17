# Anti-Ek Mac Mini dogfood (shared DuckDB + isolated events)

## Why

The personal library lives in `~/.antiek/research_graph.duckdb` (~GB-scale
event history can hang a fresh worktree if events are shared). Boot the API
with:

- **Shared DuckDB** — `ANTIEK_DUCKDB_PATH=$HOME/.antiek/research_graph.duckdb`
  so Library / books / uploads persist across worktrees.
- **Isolated events** — `ANTIEK_RESEARCH_EVENTS_DIR=<worktree>/.antiek-home/research_events_isolated`
  plus `ANTIEK_DISABLE_EVENT_PROJECTOR_RECOVERY=1` so a 2GB event log does not
  block boot.

## Start

```bash
./scripts/start-shared-duckdb-mac-mini.sh
```

Script defaults target the `anti-ek-use-main-*` worktree and
`/Users/slimydog/Antiek/platform/.env` (never commit that file). Vite on
`:5173` is reused if already listening; API on `:8000` is restarted carefully.

Local HTTP also needs (already set by the start script / `.env` for Mini dogfood):

- `ANTIEK_COOKIE_INSECURE=1` — browsers drop `Secure` cookies on `http://`
- `ANTIEK_FRONTEND_BASE_URL=http://127.0.0.1:5173` — post-login redirect to Vite

## Owner session (gated / personal_reading)

`GET /books/{id}/owner-full-text` requires a **real** auth method
(`antiek_session_cookie`, bearer, or Cloudflare). Local
`unauthenticated_local` is intentionally **excluded** — that is the
§9.0 fail-closed rule, not a bug.

To dogfood as owner **without** weakening prod gates:

1. In `platform/.env` (local Mini only; never commit):
   - `ANTIEK_AUTH_SECRET` — already required for signed cookies
   - `ANTIEK_OPERATOR_EMAIL` — single operator (turns enforcement on;
     empty allowlist keeps the middleware in `unauthenticated_local`)
   - `ANTIEK_DEV_LOGIN_TOKEN` — enables `GET /auth/dev-login` (404 when unset)
   - `ANTIEK_OPERATOR_TOKEN` — optional Bearer for curl smoke
2. Restart via `./scripts/start-shared-duckdb-mac-mini.sh`
3. Mint a session (token never printed):

```bash
# Browser (preferred for UI dogfood)
./scripts/mac-mini-owner-dev-login.sh /

# Or curl cookie jar for API smoke
ANTIEK_OWNER_LOGIN_MODE=curl ./scripts/mac-mini-owner-dev-login.sh /
# → /tmp/antiek-owner.cookies ; curl -b that jar …
```

4. Confirm: `curl -b /tmp/antiek-owner.cookies http://127.0.0.1:8000/auth/me`
   shows `"auth_method":"antiek_session_cookie"`.
5. Owner full text: `curl -b … /books/{gated_id}/owner-full-text` → 200.
6. Anonymous / no cookie: same path → `403 owner_read_required`; public
   `GET /books/{id}/full-text` still returns gated snippet only (policy
   unchanged).

Revoke: unset `ANTIEK_DEV_LOGIN_TOKEN` (or rotate it) and restart. See
`docs/decisions/agent-dev-login.md`.

**Do not** re-label gated books as `public_domain` to bypass this.

## Owned upload → BookReader vertical slice

1. Open `http://127.0.0.1:5173/sources` (with owner session cookie set).
2. Upload a file you authored; choose **I authored this (notes / drafts)**
   (`user_owned`) and confirm.
3. **Open in reader** → `/read/:id` (BookReader). Uploads register a
   `book_assets` row so `GET /books/{id}` resolves.
4. Highlight a passage → **Research this** → spin-research → `/inv/:id`
   notebook with citations (or an honest empty/gap state).

`personal_reading` uploads also bind into BookReader metadata; full text
is owner-only until a session exists. Prefer `user_owned` for the polished
anonymous-capable path; use owner session for gated / personal_reading.

## Curl smoke (user_owned)

```bash
# source platform/.env first (do not print secrets)
curl -sS -F "file=@note.html;type=text/html" \
  -F "acquisition_attestation=user_owned" \
  -F "title=Dogfood Note" \
  -H "Authorization: Bearer $ANTIEK_OPERATOR_TOKEN" \
  http://127.0.0.1:8000/sources/upload
# → document_id
curl -sS -H "Authorization: Bearer $ANTIEK_OPERATOR_TOKEN" \
  "http://127.0.0.1:8000/books/$DOC_ID"
curl -sS -H "Authorization: Bearer $ANTIEK_OPERATOR_TOKEN" \
  "http://127.0.0.1:8000/books/$DOC_ID/full-text"
curl -sS -X POST -H "Authorization: Bearer $ANTIEK_OPERATOR_TOKEN" \
  -H "content-type: application/json" \
  "http://127.0.0.1:8000/books/$DOC_ID/spin-research" \
  -d '{"page_index":0}'
```

## Highlight → Research this → notebook (API chain)

With owner cookie or Bearer:

1. Upload `user_owned` HTML/txt → note `document_id`.
2. `POST /books/{id}/spin-research` with selected text / page seed.
3. Follow redirect / response to investigation id → `GET /investigations/{id}`
   (or UI `/inv/:id`) and confirm citations block or honest gap.

Vite proxies `/books`, `/sources`, `/investigations`, `/auth`, etc. to
`:8000` so the SPA does not parse HTML as JSON.
