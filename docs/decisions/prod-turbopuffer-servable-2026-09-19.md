# Decision: Prod TurboPuffer SERVABLE hybrid wired

**Date:** 2026-09-19 (Asia/Riyadh)
**Status:** accepted

## What shipped (ops)

1. `TURBOPUFFER_API_KEY` + `ANTIEK_TURBOPUFFER_SERVABLE=1` +
   `ANTIEK_TURBOPUFFER_MANIFEST_DIR=/home/antiek/.antiek/turbopuffer-shadow`
   in `/etc/antiek/secrets.env` (EnvironmentFile; values never in git).
2. Backfilled `embeddings_meta` for export-class chunks (4837 public_domain).
3. `tools.turbopuffer_shadow rebuild` → promote → `active.json` pointer.
4. Deploy extras include `turbopuffer_shadow` so the SDK survives refresh.

## Health contract

`/health`: `turbopuffer_api_key_present=true`, `turbopuffer_servable_enabled=true`,
`turbopuffer_active_pointer=true`, `turbopuffer_hybrid_ready=true`,
`turbopuffer_production_default_mount=false` (intentional).

## Non-goals

- Flipping `production_default_mount` without a separate product decision.
- Printing API key values in logs/chat/PR bodies.
