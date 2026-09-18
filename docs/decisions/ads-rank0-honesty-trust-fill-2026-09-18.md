# Decision — Ads Rank 0 honesty (Trust + house→sponsor fill path)

**Date:** 2026-09-18 (Asia/Riyadh)
**Status:** SHIPPED (honesty envelope; no inventing cents)
**Reads with:** docs/decisions/applovin-website-mvp-attribution-ledger-2026-09-17.md; docs/specs/ad-v1-scalable-2026-08-12.md Rank 0–1; Speak residual-100 PR #3155

## Problem

Website Ads anatomy had house AdBorder, POST /api/ad/fills → ad_fill_decisions ($0 unpriced), and ManualSponsorFooter (#3103/#3109/#3138), but Rank 0 posture was not published on Trust Center or on the fills wire. Operators and public surfaces could not see the hard gates: no MAX-on-web, pricing/legal before non-zero revenue, Speak 70% only from settled cents.

## Decision

1. **Single honesty envelope** — substrate/ad_inventory/rank0_honesty.website_ads_honesty() is the source of truth.
2. **Dual structure** — creative UI remains projection; ledger stays $0 / unpriced until Rank 0.1 pricing + Rank 0.2 legal.
3. **Surfaces** — POST /api/ad/fills returns honesty; GET /trust-center publishes website_ads; ManualSponsorFooter stamps data-price-status + Rank 0 copy when served unpriced.
4. **No fake revenue** — smoke and client parse still require revenue_usd_cents === 0 and price_status === unpriced on Rank 0 fills.

## Non-goals (deferred)

- Rank 0.1 non-zero pricing / advertiser budgets
- Rank 1.1 server-minted frame value from settled fills (already S1-shaped; needs pricing)
- Axon / MAX / native client chain

## Success

Ads materially closer to honest Rank 0 website monetization without inventing cents.
