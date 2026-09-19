# Decision: BYOT soft-warn visibility + used ACU in Settings

**Date:** 2026-09-19 (Asia/Riyadh)
**Status:** accepted
**Cite:** byot-capacity-slider-2026-09-18; ACU meter soft/hard (#3140).

## Context

API already returned `capacity_warning` + `X-Antiek-Capacity-Warn` on
`POST /investigations` and `POST /books/{id}/spin-research`, and Settings
returned `used_compute_units` when metered. Daily-use UI ignored both: spin
navigated away silently; Settings still said usage was unmetered until a
meter shipped.

## Decision

1. Parse `capacity_warning` in spin + start clients; toast.warn on soft-warn;
   stash in sessionStorage for InvestigationCenter.
2. `CapacitySoftWarnBanner` on `/inv/:id` consumes the stash (dismissible).
3. Settings `ComputeCapacityPanel` shows used/monthly ACU bar when
   `used_status=known`, plus soft-over copy. No invented numbers.

## Non-goals

- Wall-time top-up on completion — shipped in byot-wall-acu-topup-2026-09-19.
- Stripe / dollar prices on ACU.
- Changing 1 ACU = investigation start heuristic.

## Consequences

BYOT/ACU daily-use grade rises with visible soft-warn on spin and honest
used ACU in Settings.
