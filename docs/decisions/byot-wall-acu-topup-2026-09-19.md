# Decision: BYOT wall-time ACU top-up on investigation complete

**Date:** 2026-09-19 (Asia/Riyadh)
**Status:** accepted
**Cite:** byot-capacity-slider-2026-09-18; #3139 / #3140 ACU meter soft/hard;
byot-soft-warn-ui-2026-09-19 (#3184).

## Context

Start metering charges **1 ACU per investigation start** so soft-warn / hard-refuse
are decidable before work begins. Long investigations still consume Antiek-hosted
CPU (orchestrator, DuckDB, retrieval, event log) after start; Settings `used`
stayed flat for multi-hour runs. Residual after #3184: wall-time top-up.

## Decision

1. **Heuristic (not dollars):** on terminal finish (complete, fail, halt-after-start,
   cancel), add `min(floor(wall_seconds / 300), 12)` ACU.
   - Quantum = **300s** (5 minutes). Under one quantum → **+0** (start charge covers).
   - Cap = **12 ACU** per investigation so a stuck run cannot drain the monthly budget.
   - Wall clock = start-ledger `recorded_at` → finish `now` (UTC), or explicit
     `wall_seconds` in tests.
2. **Ledger:** start row remains PK `investigation_id`. Top-up row uses synthetic
   PK `{investigation_id}#wall_topup`, reason `investigation_wall_topup`.
   Idempotent on completion replay.
3. **Owner:** same as start row (`owner_user_id`); runners call
   `maybe_commit_investigation_wall_topup` from `_finish` when `st.started`.
4. **Enforcement:** top-up does **not** hard-refuse mid-run. It increments
   `used_compute_units` so the **next** start sees soft-warn / hard-refuse truth.
5. **Non-goals:** no Stripe, no USD prices, no fake billing copy.

## Consequences

BYOT / ACU meter grades rise: Settings used ACU can increase after a completed
long investigation. Short dogfood spins still show +1 only.

## Forensic leave-off (pre-ship)

Meter grade ~88 with start-only heuristic; wall top-up was the documented residual.
