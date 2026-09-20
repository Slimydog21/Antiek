# Manual sponsor footer → attribution ledger dogfood

**Decision:** `docs/decisions/applovin-website-mvp-attribution-ledger-2026-09-17.md` §3.2  
**Dual structure:** DuckDB `ad_fill_decisions` = payable truth; Lemon `AdBorder` = creative projection only. Revenue stays **\$0 / unpriced** until Rank 0.1 pricing + legal — no fake revenue.

## Env (Mini)

**UI mount (Vite — already on Mini dogfood):**
```
VITE_MANUAL_SPONSOR_FOOTER=1
```

**Server creative + ledger (platform/.env — restart uvicorn):**
```
ANTIEK_MANUAL_SPONSOR_ENABLED=1
ANTIEK_MANUAL_SPONSOR_NAME=Example Research Partner
ANTIEK_MANUAL_SPONSOR_LANDING_URL=https://example.com/
# optional; defaults to /mark-32.png
ANTIEK_MANUAL_SPONSOR_CREATIVE_URL=/mark-32.png
```

Incomplete server env → house fill still persisted (honest zero-buyer).

## Smoke

1. Open a completed MASTER.md / synthesis with the Vite flag on.
2. Footer shows house or sponsor creative (`data-testid=manual-sponsor-footer`).
3. `data-fill-served=1` and `data-fill-decision-id` set when API reachable.
4. DuckDB:
```sql
SELECT window_id, revenue_usd_cents, price_status, fills_json
FROM ad_fill_decisions
WHERE window_id LIKE win:research:manual-sponsor:%
ORDER BY decided_at DESC LIMIT 5;
```
Expect `revenue_usd_cents=0`, `price_status=unpriced`, and when sponsor env complete `bidding_policy":"manual_sponsor"` inside `fills_json`.

## Explicit non-goals

- No AppLovin / MAX / pixel / Adjust.
- No disbursement (`disbursable` stays false elsewhere).
- No invented cents on the client.
