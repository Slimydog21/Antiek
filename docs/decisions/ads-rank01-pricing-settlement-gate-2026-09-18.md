# Decision — Ads Rank 0.1 pricing settlement gate (no fake cents)

**Date:** 2026-09-18 (Asia/Riyadh)
**Status:** SHIPPED (gate + honesty; no live budgets invented)
**Cite:** docs/decisions/applovin-website-mvp-attribution-ledger-2026-09-17.md;
docs/decisions/ads-rank0-honesty-trust-fill-2026-09-18.md;
docs/specs/ad-v1-scalable-2026-08-12.md Rank 0.1 / 0.2

## Problem

`decide_fills` correctly persists `$0` / `unpriced`. Frame telemetry only
mints value from `price_status=settled`. There was **no gated write path** to
settled — and no honesty surface stating that settled requires legal + pricing
authority. Risk: a future caller could UPDATE settled cents without Rank 0.2.

## Decision

1. **`settle_fill_decision`** is the only substrate API that may set
   `price_status=settled` with `revenue_usd_cents > 0`.
2. **Gates (all required):**
   - `legal_gate_passed=True` (same invariant as `activate_advertiser`)
   - non-empty `pricing_authority_ref` (budget / billing authority id)
   - `revenue_usd_cents > 0` (refuse settling $0 as "priced")
   - not a house-only fill snapshot
3. **`decide_fills` unchanged** — always unpriced $0 (render ≠ bill).
4. **Honesty envelope** publishes `settlement_open=false`,
   `settlement_path=settle_fill_decision`, and `settlement_requires[...]`.
5. **No fake revenue** — this ship does not mint budgets or cents; it only
   denies ungated settlement and documents the gate.

## Non-goals

- Live advertiser budget ingestion / CPM→cents conversion
- MAX / Axon / native chain
- Shortening agent_work lease holds (separate)

## Success

Settled pricing is gated and honest; default path remains $0 unpriced.
