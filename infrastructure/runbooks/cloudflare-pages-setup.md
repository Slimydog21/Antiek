# Cloudflare Pages — `antiek.ai` (canonical)

**Status: live as of 2026-05-18.** This runbook documents the
*current* shape rather than the original Sprint 11 plan. The original
plan called for a Pages project named `antiek-ai` serving
`app.antiek.ai`. What actually shipped: a Pages project named
`antiek` initially serving `app.antiek.ai`, then migrated to serve
the bare apex `antiek.ai` as canonical.

For the historical Sprint 11 plan (now superseded), see the spec at
`docs/master-product-spec.md` and `docs/sprints/sprint11-web-app-mvp.md`.

---

## Current production wiring

- **Pages project**: `antiek` (in the operator's Cloudflare account)
- **Source**: GitHub `Slimydog21/Antiek`, production branch `main`
- **Build command**: `cd apps/reading && npm install && npm run build`
- **Build output**: `apps/reading/dist`
- **Build env**:
  - `VITE_API_BASE_URL=https://api.antiek.ai`
- **Custom domains**:
  - `antiek.ai` (canonical, 2026-05-18)
  - `app.antiek.ai` (deprecated; deletable once no reachable client
    is sending requests from it — the CORS allow-list in
    `interfaces/research/api/app.py` keeps it acceptable during the
    cut-over window)
- **DNS**: Cloudflare-managed in the `antiek.ai` zone; the apex uses
  CNAME flattening to the Pages project's edge.

## Initial setup (one-time, completed)

These steps were operator-driven via the Cloudflare dashboard. Kept
here as a reference for any future Pages project (e.g. interview UI
in Sprint 17, publisher dashboard in Sprint 18).

### 1. Create the Pages project

- https://dash.cloudflare.com → **Workers & Pages** → **Create
  application** → **Pages** tab → **Connect to Git**
- Install the Cloudflare GitHub App on your account if prompted;
  authorize access to `Slimydog21/Antiek` (only-select-repositories
  is fine).
- Click `Antiek` in the repo list → **Begin setup**.

### 2. Build configuration

| Field | Value |
|---|---|
| Project name | `antiek` |
| Production branch | `main` |
| Framework preset | None (or "Vite") |
| Build command | `cd apps/reading && npm install && npm run build` |
| Build output directory | `apps/reading/dist` |
| Root directory | (leave blank) |

### 3. Environment variables (production)

- `VITE_API_BASE_URL=https://api.antiek.ai`
- *(H4 will add `VITE_OPERATOR_TOKEN=op_...` after the auth-at-the-
  edge cut-over.)*

### 4. Custom domains

Add `antiek.ai` first. Cloudflare detects the existing DNS record
and uses CNAME flattening to serve the Pages edge at the apex.
Adding `app.antiek.ai` is optional — only useful during the cut-over
window from the old subdomain. Once nothing reachable still requests
`app.antiek.ai`, delete the custom domain from the Pages project and
remove the entry from the substrate's CORS allow-list.

## Verification

```bash
curl -sI https://antiek.ai/                    # expect 200
curl -s  https://antiek.ai/ | head -10         # expect Antiek index.html
curl -s  https://api.antiek.ai/health | jq .   # expect hermes in registered_providers
```

## Sub-pages (Sprint 17+)

Future deployments are separate Pages projects under the same zone:

- `interview.antiek.ai` → Sprint 17 informant UI (Pages or Worker)
- `publisher.antiek.ai` → Sprint 18 publisher dashboard (Pages)

Each takes the same shape: new Pages project, new custom domain,
build env wires to `api.antiek.ai`.
