# SPR-08 — review-state is now resolved from typed substrate events

**Date:** 2026-05-27
**Updated:** 2026-06-30
**Branch:** `physics/spr-08` (worktree `antiek-physics-spr08`)
**Source spec:** `docs/philosophy/physics-of-reading.md` (the canon) + SPR-08 sprint
(the capstone — agent-authorability / PR-8 + `AUTHORING_KIT.md`)
**Status:** **RESOLVER CLOSED.** review-due remains the first AGENT-authored
augmentation and still composes through the same un-relaxed gates, but the
deferred substrate signal/resolver is now wired: `claim.reviewed` typed events
record per-claim review verdicts, `reviewState.ts` resolves the latest event per
claim into `ReviewDueClaimView[]`, and `ResearchWorkstation` hands that due set
to `MasterMdViewer` with review-due enabled. No history still means honest
no-data: no claim lights up until a `claim.reviewed` event makes it due.
**Owner:** Read-surface instance for the remaining review gesture/scheduler UI,
operator for any future policy toggle.

## What was decided

review-due (`augmentations/review-due.ts`) marks the claims a reader is *due to
review* (Quantum-Country-style memory consolidation). It is a plain DECORATION —
it anchors to a claim's positional id and declares a closed-vocabulary
`review-due` class on the claim's range. Because it is geometry-independent, it
composes through the SAME decorations facet apply pass the §9.0 servability /
IP-holder augmentations already run, and the mount is a GENUINELY LIVE wiring
(not blocked on a geometry pass like SPR-05's collapse).

The augmentation reads a surface-resolved `dueClaims` view: the substrate-derived
list of claims currently due, with an optional substrate-resolved cue label
("Due today" / "Overdue"). The deferred missing piece was the review-history
signal and resolver. That is now provided by a `claim.reviewed` typed event and
a surface resolver that reads persisted events, selects the latest review verdict
per claim, and marks a claim due only when `next_due_at <= now`.

The original decision (anti-purgatory, PR-7 — ship it wired, not in a drawer)
mounted review-due through the real facet pass behind a default-off toggle and
passed an empty `dueClaims`. The 2026-06-30 follow-up keeps the same no-fabrication
rule but replaces the placeholder with a real resolver. With no
`claim.reviewed` history, the resolved due set is still empty; with due history,
the cue lights up without changing the augmentation.

This doc files the net-new signal prominently so it is tracked where closure
gates live (`docs/decisions/`), mirroring the SPR-06 `source.read` deferral. The
2026-06-30 update records the closure of the resolver piece that was most at
risk of "never lighting up."

## The gap, precisely

- review-due's CODE is complete: it declares the `review-due` class + an optional
  substrate-resolved title per due claim, composes with Skim/SiteSee/marginalia
  via the §5.1 range-union rule (proved in `review-due.compose.test.ts` — both
  classes merge on one claim range, order-independent), and passes guard + tsc.
- review-due is MOUNTED in `MasterMdViewer.tsx`: `composedReviewDueByClaim()`
  runs the decorations pass over the synthesis claims, gated by
  `REVIEW_DUE_ENABLED` (default `false`); the pure seam `reviewDueDecorationsFor()`
  runs the augmentation→facet→map chain over the passed-in due set, and
  `ClaimBlock` enacts the declared class + title onto the claim span. Default-off
  ⇒ the pass runs nothing ⇒ the claim span is byte-identical to today. This is
  test-pinned directly: `MasterMdViewer.test.tsx` ("review-due default-off
  byte-equivalence") asserts NO claim span carries the `review-due` class or a
  review-due title on the shipped default, and the SPR-02 byte-equivalence test
  re-proves the whole §9.0 render unchanged transitively.
- **review-state**: **closed on 2026-06-30.** The schema now includes
  `ClaimReviewedPayload` (`action_type = "claim.reviewed"`), generated TS types
  include the payload, and `reviewState.ts` resolves persisted review events into
  due claims. The resolver is latest-event-wins by `emitted_at`, ignores malformed
  payloads, and never fabricates first-review schedules. Tests pin the event
  schema, typed emitter, no-body payload shape, latest-event-wins behavior,
  malformed/no-data behavior, and mounted `MasterMdViewer` rendering from
  substrate-resolved `dueClaims`.

## Why this is separate from the SPR-05 geometry-pass gap (NOT subsumed)

The SPR-05 gap (`spr-05-geometry-pass-gap.md`) is a **read-time geometry
measurement pass** — one `useLayoutEffect` that lights up every layout-dependent
widget (collapse, minimap, AccrualView, ChaseThread) at once.

review-due needs NONE of that. It is a plain decoration: claim-anchored, no
gutter lane, no rect, no widget. Its mount is already genuinely live through the
decorations pass — flipping `REVIEW_DUE_ENABLED` on renders it immediately. What
it waits on is not geometry but **data**: a surface-resolved review schedule.
That substrate-resolution integration now exists for `claim.reviewed` history.
It remains distinct from the geometry pass; recorded here so future scheduler/UI
work is not conflated with geometry.

## The exact next step

1. **Gesture:** add the reader-facing review action that calls
   `emitClaimReviewed(...)` after the operator settles the exact control and
   scheduling policy.
2. **Scheduler policy:** tune the rating/ease/interval semantics that populate
   `next_due_at`; the event and resolver already carry those fields without
   requiring a separate side store.
3. **Policy toggle:** decide whether review-due stays enabled in
   `ResearchWorkstation` only or becomes a user-visible setting across the
   broader reading surface.

The original prerequisite — a review-history signal through the typed event
funnel (`postTypedEvent` → `/events/typed` → `runtime/db_lock`, single-writer,
PR-6) — is now satisfied by `claim.reviewed`.

## Reconsider if

- The review gesture needs richer schedule inputs than `rating`, `ease`,
  `interval_days`, `reviewed_at`, and `next_due_at` can represent → extend
  `ClaimReviewedPayload` with a new schema version, not a parallel signal.
- A review-history / spaced-repetition signal turns out to already exist under
  another event name → point the resolver at it instead of emitting a new one
  (avoid a duplicate signal).
- Spaced-repetition review-tracking raises a privacy/telemetry concern at the
  single-operator stage → keep the toggle off (the augmentation stays dormant;
  nothing else regresses since default-off is byte-equivalent), and record that
  call here.
