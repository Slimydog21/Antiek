# SPR-08 — the reader's review-state is not yet resolved from the substrate (review-due ships dormant behind a default-off toggle)

**Date:** 2026-05-27
**Branch:** `physics/spr-08` (worktree `antiek-physics-spr08`)
**Source spec:** `docs/philosophy/physics-of-reading.md` (the canon) + SPR-08 sprint
(the capstone — agent-authorability / PR-8 + `AUTHORING_KIT.md`)
**Status:** review-due (the first AGENT-authored augmentation) is capability
complete, composes + passes the same un-relaxed gates, and is MOUNTED live in
`MasterMdViewer.tsx` through the real decorations facet pass — behind a
**default-OFF toggle** (`REVIEW_DUE_ENABLED`). The cue is **dormant**: it depends
on a per-reader **review-state** (which claims are *due to review*) that the
surface does not yet resolve from the substrate.
**Owner:** Read-surface instance (whoever builds the surface spaced-repetition
schedule resolution) + operator (sequencing the integration + flipping the toggle).

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
("Due today" / "Overdue"). Diligence found that **no review-state signal exists
yet** — there is no resolved spaced-repetition schedule the surface can hand to
the factory. The augmentation never invents one (PR-2/PR-6: it READS a
substrate-resolved verdict, never fabricates or recomputes it).

The decision (anti-purgatory, PR-7 — ship it wired, not in a drawer): mount
review-due NOW through the real facet pass, behind a **default-off** toggle, and
pass an **empty `dueClaims`**. Flipping the toggle on therefore shows the HONEST
no-data state — nothing lights up — rather than fabricated review state. When the
surface later resolves a real schedule and hands it in, the cue lights up with no
augmentation change (dormant-correct).

This doc files the net-new signal prominently so it is tracked where closure
gates live (`docs/decisions/`), mirroring the SPR-06 `source.read` deferral — the
review-state resolution is the one deferred piece most at risk of "never lighting
up."

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
- **review-state**: there is **no resolved spaced-repetition schedule** the
  surface can pass in. Until the surface resolves which claims are due (from the
  reader's review history in the substrate) and hands a populated `dueClaims`,
  the due set is empty and the cue never appears. The augmentation is
  **dormant-correct**: it renders the moment the resolved `dueClaims` carries an
  entry. This is test-pinned by the toggle-ON liveness test
  (`MasterMdViewer.test.tsx` — "review-due liveness"): driving the pure seam
  `reviewDueDecorationsFor()` with a populated `dueClaims` (`[{claimId: "1",
  dueLabel: "Due today"}]`) lands the `review-due` class + cue title on the due
  claim span and on NO other claim span — proving the wiring is genuinely live,
  not the resolver. The resolver itself is the deferred piece: even with the
  toggle ON today, the surface still hands an EMPTY `dueClaims`, which is the
  honest no-data state, NOT a bug.

## Why this is separate from the SPR-05 geometry-pass gap (NOT subsumed)

The SPR-05 gap (`spr-05-geometry-pass-gap.md`) is a **read-time geometry
measurement pass** — one `useLayoutEffect` that lights up every layout-dependent
widget (collapse, minimap, AccrualView, ChaseThread) at once.

review-due needs NONE of that. It is a plain decoration: claim-anchored, no
gutter lane, no rect, no widget. Its mount is already genuinely live through the
decorations pass — flipping `REVIEW_DUE_ENABLED` on renders it immediately. What
it waits on is not geometry but **data**: a surface-resolved review schedule.
That is a substrate-resolution integration (assemble the due set from the
reader's review history), distinct from a geometry pass. Recorded here so the two
deferrals are not conflated.

## The exact next step

1. **Resolve:** in the reading surface, assemble the per-reader review schedule
   for the synthesis — which claims are due, and an optional substrate-resolved
   cue label per due claim — by reading the reader's review history from the
   substrate (the spaced-repetition state). No side store; read-only.
2. **Hand in:** pass the populated `ReviewDueClaimView[]` to
   `makeReviewDueAugmentation(...)` in `composedReviewDueByClaim()` (replace the
   empty `dueClaims` placeholder).
3. **Flip:** set `REVIEW_DUE_ENABLED = true` (or promote it to a real
   feature/user setting) once the resolver ships. review-due already maps the
   resolved view → the `review-due` class; no augmentation change needed.

> Resolving the review schedule itself depends on a review-history signal in the
> substrate (when a reader reviews a claim, that gesture must be recorded — likely
> a typed event through the one shipped funnel `postTypedEvent` → `/events/typed`
> → `runtime/db_lock`, single-writer, PR-6, exactly like SPR-06's `source.read`).
> If that signal does not yet exist, emitting it is a prerequisite of step 1.

## Reconsider if

- The surface resolves + hands in a real `dueClaims` and the toggle is flipped on
  (this gap closes) → mark superseded and record the wiring commit.
- A review-history / spaced-repetition signal turns out to already exist under
  another event name → point the resolver at it instead of emitting a new one
  (avoid a duplicate signal).
- Spaced-repetition review-tracking raises a privacy/telemetry concern at the
  single-operator stage → keep the toggle off (the augmentation stays dormant;
  nothing else regresses since default-off is byte-equivalent), and record that
  call here.
