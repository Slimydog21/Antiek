# Decision: BYOT hard-refuse UX + Settings enforcement honesty

**Date:** 2026-09-19 (Asia/Riyadh)
**Status:** accepted
**Cite:** byot-capacity-slider-2026-09-18; byot-soft-warn-ui-2026-09-19; byot-wall-acu-topup-2026-09-19; ACU meter (#3140).

## Context

Hard enforcement already returned HTTP 429 with bare
`detail: "compute_capacity_exhausted"` from `run_capacity_precheck`. Soft-warn
had toast + banner + used ACU bar (#3184). Hard refuse degraded to generic
"HTTP 429" / "Submit failed" with no Settings deep-link, and Settings showed
raw `enforce=` crumbs without explaining Off / Soft / Hard or wall-time
metering.

## Decision

1. **Structured 429 detail** via `capacity_exhausted_payload`: `code`,
   `message`, used/monthly ACU, `enforcement`, `retryable: false`. No fake
   billing; ACU numbers only from the live capacity row.
2. **Client honesty**: `parseCapacityExhaustedDetail` + `CapacityExhaustedError`;
   `startInvestigation` / `spinResearch` toast.err with `/settings` target;
   `useStartInvestigation` surfaces the toast message (not "Submit failed: HTTP 429").
3. **Settings polish**: human Enforcement copy; `would_hard_block` alert;
   metering note (1 ACU start + 300s wall quantum, capped). Panel does **not**
   flip `ANTIEK_COMPUTE_CAPACITY_ENFORCEMENT`.

## Non-goals

- Stripe / dollar prices on ACU.
- Flipping production enforcement env from the UI.
- Changing start or wall-topup heuristics.

## Consequences

BYOT daily-use grade rises: hard refuse is as visible as soft-warn, Settings
states the gate honestly, wall top-up is explained next to the used bar.
