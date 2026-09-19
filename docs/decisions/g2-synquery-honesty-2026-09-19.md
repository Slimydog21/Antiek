# Decision — G2 counsel + Synquery honesty (no invented partnership / paid-today)

**Date:** 2026-09-19 (Asia/Riyadh)
**Status:** accepted
**Cite:** `speak-residual-100-2026-09-18.md`; `spr-10-ai-graded-payout.md`;
`afa-escrow-double-credit.md`; master-product-spec §11.6;
`substrate/speak/gate_status.py`; `tools/synquery` feature flag.

## Context

Speak already denies public publishing + disbursement by default (G2/G3) and
accrues escrow only (`money_model=accrue_escrow_now_disburse_after_legal_review`).
Synquery client exists behind `ANTIEK_SYNQUERY_ENABLED` (default off). Trust
Center published Ads honesty but not Speak/G2/Synquery, so visitors could miss
that counsel + expert-network partnership are **gated**, not live deals.

## Decision

1. **`g2_synquery_honesty()`** — single envelope: `g2_counsel_gated`,
   `synquery_gated` / `synquery_partnership`, `paid_today=false`,
   `money_model`, `g2_requires`, `synquery_requires`, decision refs.
2. **Surfaces** — Trust Center `speak_economics`; unauth
   `GET /speak/opportunities` honesty; Speak PublicLane Synquery gate line;
   `speakVocab.GATE_PHRASES.synquery` (no user-agency verbs, no env-flag leak).
3. **Non-flips** — does not set `ANTIEK_SPEAK_PUBLIC_PUBLISHING`, does not set
   `ANTIEK_STRIPE_PROVIDER=real`, does not invent a Synquery partnership or
   booking UI as connected, does not flip `production_default_mount`.

## Non-goals

- Closing G2 counsel or G3 opt-in (operator/legal)
- Enabling Synquery credits / live booking
- Disbursement / Stripe Connect payouts
- Email re-ping outreach

## Success

Product surfaces show G2 counsel + Synquery as gated; accrue-now /
disburse-after-legal remains the only money model; no “paid today” copy.
