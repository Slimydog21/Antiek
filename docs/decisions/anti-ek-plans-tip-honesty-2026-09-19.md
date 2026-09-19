# Decision: Plans tip honesty (leave-off + rollup + master-spec pointer)

**Date:** 2026-09-19 (Asia/Riyadh)
**Status:** accepted
**Cite:** anti-ek-composite-rollup; anti-ek-leaveoff; master-product-spec companion list; PRs #3212–#3219.

## Context

Plans graded ~95 because the leave-off/rollup still claimed tip `7bfff594…` (#3192)
and composite ~97 while live Mini+prod were on `7b871c58…` (#3219). Scorecard
rows for BYOT/Notebook/HTML/CLI had been patched in-place, but the tip stamp,
evidence table, PR forensic table, closed-list, and leave-off pointer lagged.
Master-product-spec companion list did not point agents at the Anti-Ek rollup.

## Decision

1. Re-stamp rollup + leave-off on tip `7b871c58…` with live health evidence.
2. Add PR table + decision index cross-links for Speak/Ads/BYOT/Notebook/HTML/CLI/dogfood honesty (#3212–#3219).
3. Mark shipped residuals closed; next = Specs/Code/TPuf (no mount flip) + operator list.
4. Point `docs/master-product-spec.md` companion list at the Anti-Ek rollup/leave-off (status report, not a second master).

## Non-goals

- Flipping Synquery / G2 / email / `production_default_mount` / inventing CPM.
- Rewriting §3 / §15 of master-product-spec (still point-in-time by design).
- Fake money.

## Consequences

Plans grade rises to tip-honest ~99. Agents reading master-spec find the current
Anti-Ek scorecard without inventing a parallel roadmap.
