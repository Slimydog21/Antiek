# SPR-08 — review-state is now resolved from typed substrate events

**Date:** 2026-05-27
**Updated:** 2026-06-30
**Branch:** `physics/spr-08` (worktree `antiek-physics-spr08`)
**Source spec:** `docs/philosophy/physics-of-reading.md` (the canon) + SPR-08 sprint
(the capstone — agent-authorability / PR-8 + `AUTHORING_KIT.md`)
**Status:** **RESOLVER + V1 GESTURE + POLICY TOGGLE CLOSED.** review-due remains
the first AGENT-authored augmentation and still composes through the same
un-relaxed gates, but the deferred substrate signal/resolver is now wired:
`claim.reviewed` typed events record per-claim review verdicts, `reviewState.ts`
resolves the latest event per claim into `ReviewDueClaimView[]`, and
`ResearchWorkstation` hands that due set to `MasterMdViewer` through the
persisted **Review cues** operator toggle. Due claims expose Again/Good/Easy
controls that emit deterministic v1 scheduler metadata. No history still means
honest no-data: no claim lights up until a `claim.reviewed` event makes it due.
**Owner:** read-surface maintainer for future tuning; operator only if changing
the default policy or ratifying the canon.

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
mounted review-due through the real facet pass behind a default-off viewer prop
and passed an empty `dueClaims`. The 2026-06-30 follow-ups keep the same
no-fabrication rule but replace the placeholder with a real resolver,
Again/Good/Easy review gesture, and completed-research **Review cues** policy
toggle. With no `claim.reviewed` history, the resolved due set is still empty;
with due history and the operator policy on, the cue lights up without changing
the augmentation.

This doc files the net-new signal prominently so it is tracked where closure
gates live (`docs/decisions/`), mirroring the SPR-06 `source.read` deferral. The
2026-06-30 update records the closure of the resolver, gesture, scheduler, and
policy-toggle pieces that were most at risk of "never lighting up."

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
- **review-state + gesture + policy toggle**: **closed on 2026-06-30.** The schema now includes
  `ClaimReviewedPayload` (`action_type = "claim.reviewed"`), generated TS types
  include the payload, and `reviewState.ts` resolves persisted review events into
  due claims. The resolver is latest-event-wins by `emitted_at`, ignores malformed
  payloads, and never fabricates first-review schedules. The completed research
  surface gates due cues and the review handler behind the persisted Review cues
  toggle. Tests pin the event schema, typed emitter, no-body payload shape,
  latest-event-wins behavior, malformed/no-data behavior, mounted
  `MasterMdViewer` rendering from substrate-resolved `dueClaims`, and the
  policy-off wiring that passes no due claims or review handler.

## Why this is separate from the SPR-05 geometry-pass gap (NOT subsumed)

The SPR-05 gap (`spr-05-geometry-pass-gap.md`) is a **read-time geometry
measurement pass** — one `useLayoutEffect` that lights up every layout-dependent
widget (collapse, minimap, AccrualView, ChaseThread) at once.

review-due needs NONE of that. It is a plain decoration: claim-anchored, no
gutter lane, no rect, no widget. Its mount is already genuinely live through the
decorations pass; completed research now flips that pass through the Review cues
operator policy and supplies a substrate-resolved due set. What it waited on was
not geometry but **data**: a surface-resolved review schedule. That substrate
integration now exists for `claim.reviewed` history. It remains distinct from the
geometry pass; recorded here so future scheduler/UI work is not conflated with
geometry.

## Closed follow-up: reader gesture + v1 scheduler

On 2026-06-30 the read surface added the missing reader-facing review action:
due claims render compact **Again / Good / Easy** controls only when
`ResearchWorkstation` has resolved a persisted `claim.reviewed` history into a
due cue. Selecting a rating emits another `claim.reviewed` typed event through
the existing single-writer funnel and hides the claim locally after a confirmed
emit.

The v1 scheduler policy is deterministic and deliberately small:

- `again` -> 30 minutes, ease `1.3`, label `Due again soon`
- `good` -> 1 day, ease `2.5`, label `Due tomorrow`
- `easy` -> 7 days, ease `3.0`, label `Due in a week`

These are hardcoded v1 constants in `scheduleClaimReview(...)` in
`apps/reading/src/modes/ResearchWorkstation/reviewState.ts`; tune them there
until the operator asks for a user-visible scheduler policy.

This closes the prior gesture/scheduler substrate gap without inventing first
review schedules for claims with no history. No history still produces the
honest empty due set.

## Closed follow-up: operator policy toggle

On 2026-06-30 the completed-investigation surface added an explicit persisted
operator toggle, **Review cues**, scoped to `ResearchWorkstation`. The reusable
`MasterMdViewer` still defaults review-due off for every caller, but completed
research answers now gate the substrate-resolved due set, decoration pass, and
Again/Good/Easy review handler behind this operator preference. The preference
defaults on to preserve the shipped completed-research behavior and stores only
an explicit local `off` value in `localStorage`; no substrate event is emitted
for this UI policy.

This closes the review-due policy-toggle residual for D13. Broader reading
surfaces can opt in later by calling the same viewer props, but there is no
hidden global review state and no fabricated due state.

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
  single-operator stage → turn the operator toggle off (the augmentation stays
  dormant for completed research answers; the reusable viewer remains
  default-off), then revisit whether the default should change.
