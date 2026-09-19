# Decision — Ads paid-fill honesty scaffold (gated; no fake CPM)

**Date:** 2026-09-19 (Asia/Riyadh)
**Status:** accepted
**Cite:** #3156 Rank 0 honesty; #3163 Rank 0.1 `settle_fill_decision`;
`docs/decisions/applovin-website-mvp-attribution-ledger-2026-09-17.md`;
`docs/decisions/ads-rank0-honesty-trust-fill-2026-09-18.md`;
`docs/decisions/ads-rank01-pricing-settlement-gate-2026-09-18.md`.

## Context

Ads anatomy sat at ~94 with Rank 0 honesty + Rank 0.1 settlement gates, but
the **paid** path (lead-gen / sponsor bill) was not named on the public
envelope, and `settle_fill_decision` accepted a free-form `advertiser_id`
without proving the advertiser was **ACTIVE** under Rank 0.2. Operators could
not see `paid_fill_gated` on Trust / fills. AppLovin website MVP doctrine
remains: Antiek-served creatives only; **no MAX SDK on web**; no invented CPM.

## Decision

1. **Honesty envelope** publishes:
   - `paid_fill_gated: true`
   - `paid_fill_default: unpriced_zero` (decide_fills unchanged)
   - `paid_fill_requires: [active_advertiser_id, legal, pricing_authority,
     revenue>0, not_house_only, antiek_owned_creatives_no_max_sdk]`
   - `applovin_alignment: antiek_owned_creatives_no_max_sdk`
   - `paid_fill_decision_ref` → this document
2. **`settle_fill_decision`** additionally requires an **ACTIVE** registry
   advertiser (`activate_advertiser` + `legal_gate_passed`). Unknown or
   non-ACTIVE ids are denied. Still never invents cents — caller supplies
   `revenue_usd_cents` from a real `pricing_authority_ref`.
3. **Surfaces** — Trust Center + `POST /api/ad/fills` honesty carry the new
   fields; frontend types tolerate and (when present) require
   `paid_fill_gated === true`.
4. **Default path** remains house / unpriced $0. No live AppLovin demand,
   no MAX, no fake CPM conversion.

## Non-goals

- Ingesting live advertiser budgets or CPM→cents converters
- Flipping `turbopuffer_production_default_mount`
- Stripe / payout automation
- Native MAX / Axon pixel

## Success

Paid fill is gated and documented; public honesty shows the gate; settle
denies without ACTIVE advertiser + legal + authority; default fills stay
$0 unpriced.
