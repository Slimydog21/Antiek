# Speak residual-100 — G2/G3 honesty & deferred list

**Date:** 2026-09-18  
**Tip:** post-#3154 invite-landing read-path; this decision closes the Speak
lane to an **honest 100** with an intellectually defensible deferred list.  
**Cite:** `spr-10-ai-graded-payout.md`, `afa-escrow-double-credit.md`,
`speak-private-public-spine.md`, `anti-ek-speak-deepblu-remap-2026-09-18.md`,
`substrate/speak/gate_status.py`.

## Forensic — G2/G3 (2026-09-18)

| Gate | Env / flip | Code | UX |
|---|---|---|---|
| **G2+G3 public publishing** | `ANTIEK_SPEAK_PUBLIC_PUBLISHING=1` after counsel | `gate_status.public_publishing_allowed` deny-by-default; publish → 409 | PublicLane / SpeakSettings live gated copy; no flip affordance |
| **G2+G3 disbursement** | `ANTIEK_STRIPE_PROVIDER=real` | `disbursement_allowed`; `attempt_disbursement` refuses; `release_payout` → **escrow only** | “owed, not paid”; no withdraw/disburse button |
| **Accrue now** | always | `contributor.accrue_contributions` → `ip_holders.escrow` | Invitee `publicCanEarn`: accrue escrow; cash after legal review |

**Verdict:** G2/G3 are correctly gated. Closing them is **operator/legal**, not a
code invention of live money. No path fakes disbursement or “you’ll get paid now.”

## What this PR adds (honesty, not flip)

- Unauth `GET /speak/opportunities` honesty surfaces G2/G3 + money_model
  (`accrue_escrow_now_disburse_after_legal_review`) so `/speak/browse` visitors
  see the same truth without an authed economics probe.
- `publicCanEarn` copy sharpened: grades accrue to escrow; cash waits on G2/G3.
- Economics GET uses `_read` (no write flock for a status read).

## Speak = honest 100 — deferred list (not defects)

1. **G2 counsel sign-off + G3 opt-in** → operator sets `ANTIEK_SPEAK_PUBLIC_PUBLISHING=1`.
2. **Real Stripe** → operator sets `ANTIEK_STRIPE_PROVIDER=real` only after (1).
3. **Ad buyers / Applovin on Read·Research·Write** (not Speak) — revenue to fund
   the 70% split; Speak stays ad-free (remap).
4. **Write-path residual** — mutations still take the write flock; invite GET is
   fixed (#3153/#3154). Note-taker / agent_work can still slow writers.
5. **Email re-ping** — Faisal skipped; invite-path continuous ping works without mail.
6. **ML profile matching** — intentionally not; multi-signal heuristic is honest.

None of (1)–(6) are “Speak incomplete.” They are **gates, economics inputs, or
explicit non-goals**. Shipping fake live money or a disburse button would be a
regression against spr-10 / escrow / spine.

## Success criterion met

Stranger browse + invitee + operator surfaces state accrue-now / disburse-later
without promising cash today. Private no-earnings UX unchanged.


## Addendum 2026-09-19 — Trust + Synquery honesty

Shipped `docs/decisions/g2-synquery-honesty-2026-09-19.md`: Trust Center
`speak_economics` + opportunities honesty now publish `g2_counsel_gated`,
`synquery_gated`, `paid_today=false`. Still **no** counsel flip, Synquery
partnership invention, or disbursement open. Operator list (1)–(2) unchanged.

## Addendum 2026-09-19 — Specs contract catalog

Cross-surface honesty field shapes (Ads / Speak G2·Synquery / BYOT capacity /
HTML `artifact.html`) frozen in
[`docs/specs/anti-ek-honesty-api-contracts-2026-09-19.md`](../specs/anti-ek-honesty-api-contracts-2026-09-19.md)
+ `substrate.contracts.anti_ek_honesty`. Speak residual-100 deferred list
unchanged — still operator gates, not Specs invent.
