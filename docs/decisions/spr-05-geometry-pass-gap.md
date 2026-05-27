# SPR-05 — the surface geometry-measurement pass is not yet built (collapse + minimap ship dormant)

**Date:** 2026-05-27
**Branch:** `physics/spr-05` (worktree `antiek-physics-spr05`)
**Source spec:** `docs/philosophy/physics-of-reading.md` (the canon) + SPR-05 sprint
**Status:** ~~SPR-05 capability complete + tested; **dormant** — mounted nowhere live.~~
**CLOSED (PARTIAL) 2026-05-27** by the Living-Roadmap SPR-02 geometry pass
(branch `caffen/lr-spr02`). The surface now measures DOM geometry and mounts a
**live layout-map** in place of `EMPTY_LAYOUT_MAP`. The seam is closed; what is
GENUINELY live vs. still-dormant-and-why is enumerated in the "What actually
shipped" section below — read it before assuming "all live."
**Owner:** Read-surface instance (whoever builds the cross-cutting surface
integration) + operator (sequencing the integration sprint).

## What was decided

SPR-05 ships the spatial-transform facet (`facets/spatial-transform.ts`), the
collapse controller (`augmentations/collapse.ts`), and the minimap (`minimap.tsx`)
**complete and proved** — but **deliberately NOT wired into the live reading
surface this sprint.** The capability is dormant-but-on-the-real-engine: it runs
on the actual layout-map seam (`createLayoutMap` / `createViewportScopedLayoutMap`),
not a prototype, and turns on the moment the surface feeds it real geometry.

This doc files the gap prominently so a future reader does not mistake the
dormancy for completeness (or for a regression).

## The gap, precisely

> **HISTORICAL (gap CLOSED 2026-05-27).** This section describes the state
> BEFORE the Living-Roadmap SPR-02 geometry pass; it is kept for the why-deferred
> record. The current state is in "What actually shipped" below. (Note: the
> "lines ~581/591/593" reference below was stale even when written — the actual
> `EMPTY_LAYOUT_MAP` mounts had drifted to the `renderHeaderQualityCue` pass at
> ~717/727/729 by the time SPR-02 picked this up; SPR-02 grepped ALL consumers
> rather than trusting the line numbers.)

The reading surface
(`apps/reading/src/modes/ResearchWorkstation/MasterMdViewer.tsx`) feeds
**`EMPTY_LAYOUT_MAP`** into every render context — it imports it at the top and
passes it at lines ~581/591/593. `EMPTY_LAYOUT_MAP.resolve` returns `null` for
every anchor, i.e. the surface measures **no DOM geometry**. Consequences:

- `createLayoutMap(base, pipeline)` has no real `BaseGeometry` to fold a collapse
  pipeline over, so a collapse has nothing to transform.
- The minimap's `projectDecorationsToMinimap` re-projects positions that are all
  `null`, so it paints nothing.
- The collapse `⌘/Ctrl+scroll` gesture is unbound (no surface handler mutates the
  ephemeral `CollapseState`).

The single missing piece is a **surface geometry-measurement pass**: a
`useLayoutEffect` that calls `getBoundingClientRect()` per laid-out anchor,
assembles an `anchorKey → Rect` map, and hands it to `baseGeometryFromMap` →
`createLayoutMap` so the layout-map resolves **real** geometry. Per PR-4/PR-5 this
pass is the **one** place `getBoundingClientRect` is allowed to be called — inside
the surface, never in an augmentation; the reading-physics CI guard
(`tools/lint/reading_physics_check.py`) forbids `getBoundingClientRect` anywhere
under `augmentations/`/`facets/`.

## Why this is cross-cutting (not SPR-05's milestone)

SPR-05's milestone is the **reading-physics-`/`-scoped** capability: the transform
math, the widgets-follow-the-transform proof, the minimap-shares-the-facet proof,
and the viewport-scoping perf mitigation — all proved against **in-memory
`BaseGeometry` fixtures** in `spatial-transform.test.ts` (so the facet engine is
verified without a DOM).

Building the live DOM-geometry pass is a **separate surface integration** that
touches `MasterMdViewer`'s render lifecycle (a `useLayoutEffect` measure-on-paint),
its scroll handling (the viewport band that feeds `createViewportScopedLayoutMap`
re-derives each scroll), and its gesture handling (binding `⌘/Ctrl+scroll`). That
work spans the surface, not the reading-physics module, so it is correctly out of
SPR-05's scope. The dormant-on-real-engine posture is the honest middle: the
capability is not faked behind a stub, it simply awaits the one integration.

## The exact next step (one cross-cutting integration)

1. **Build the geometry-measurement pass** in `MasterMdViewer.tsx`: in a
   `useLayoutEffect`, `getBoundingClientRect()` per laid-out anchor → an
   `anchorKey → Rect` map → `baseGeometryFromMap` → `createLayoutMap`. Replace the
   `EMPTY_LAYOUT_MAP` render contexts (lines ~581/591/593) with this real map.
2. **Bind the collapse gesture**: a `⌘/Ctrl+scroll` handler mutates the ephemeral
   `CollapseState` (immutable, never persisted — the PR-2 escape) and feeds
   `collapsePipelineFor(state)` into `createLayoutMap` / (for long docs)
   `createViewportScopedLayoutMap` with the scroll-derived viewport band.
3. **Mount the minimap** as a second pass: `minimapLayoutFrom(mainLayout, …)` →
   `projectDecorationsToMinimap(resolved, …)` → `renderMinimap(...)`.

This single integration unblocks collapse, the minimap, **and** the not-yet-live
`AccrualView` / `ChaseThread` gutter widgets simultaneously — they all wait on the
same real `BaseGeometry`. (Only `QualityCue` is live today, because it pins to the
header and renders without geometry.)

## What actually shipped (Living-Roadmap SPR-02, 2026-05-27)

The cross-cutting surface integration the "exact next step" called for is built.
Honest accounting of what is GENUINELY live vs. still dormant (no rounding up):

**The seam is closed (M1).** A new surface module
`apps/reading/src/modes/ResearchWorkstation/readingGeometryPass.ts` holds the
ONE `getBoundingClientRect` caller in the whole reading stack (the PR-4 boundary
— it lives in the surface, never under `reading-physics/`; the CI guard does not
scan it and must never need to). `MasterMdViewer.tsx` runs it in a
`useLayoutEffect` (synchronous, post-commit / pre-paint): it measures every
laid-out `[data-claim-id]` claim span → `anchorKey → Rect` → `baseGeometryFromMap`
(layout-map.ts:71) → `createViewportScopedLayoutMap` (layout-map.ts:177), and
stores the result in state. `EMPTY_LAYOUT_MAP` is **no longer the mounted map** —
it is only the first-paint default (before the first measure), exactly the honest
"nothing laid out yet" state. The header `renderHeaderQualityCue` pass and the
minimap second pass both now run against this live map.

**What is GENUINELY live now:**
- The **layout-map itself** resolves real, non-null rects for claim anchors from
  the measured DOM (proved by `readingGeometryPass.test.ts`'s known-anchor →
  non-null-rect test against a populated DOM).
- The **minimap** is MOUNTED as a second pass in `MasterMdViewer` (the
  `.reading-minimap` container renders; proved by the surface test). It projects
  the same `ResolvedDecoration[]` the main column resolves through a
  minimap-scaled layout-map derived from the live map. Its marks light up the
  moment there are CLAIM-anchored decorations in the main view.
- The **collapse** controller resolves claim anchors through the live map: its
  `fingerprintPlan` correctly places a measured claim inside / outside a collapsed
  band (proved against the live map). The geometry it needs is real.
- **QualityCue** (header widget) — already live pre-this-sprint; now runs against
  the live map (byte-equivalent, it is geometry-independent).

**What is still DORMANT, and exactly why (rigor #1 — do not round up):**
- **Marginalia** anchors to `passage` anchors (chunk-relative offsets) and, for
  withheld targets, `chunk` anchors. The surface today stamps DOM markers for
  **claims only** (`data-claim-id`); it stamps no `data-chunk-id` /
  `data-passage-*` markers. So the geometry pass measures NO passage/chunk anchor,
  and a marginalia note's `passage` anchor resolves to `null` through the live map
  → the note renders nothing. The marginalia FACET PATH is proved live (an
  anchored widget resolves a non-null rect when handed a measured anchor — the
  test re-pins to a claim anchor to prove this), but a marginalia note pinned to a
  real passage **cannot light up until the surface stamps passage/chunk DOM
  markers and the measure pass reads them.** That is the next wedge, deliberately
  out of THIS sprint's scope (M2 is wiring-only; adding new DOM markers + extending
  the measure query is net-new surface work). Distinguish: "I saw marginalia's
  facet render against a real rect in a test" (TRUE) vs. "a marginalia note
  consumed a rect the live map returned for its passage anchor" (NOT yet — no
  passage geometry is measured).
- The **collapse ⌘/Ctrl+scroll gesture is NOT bound.** This sprint lit up the
  geometry collapse CONSUMES; it did not add the surface gesture handler that
  mutates `CollapseState` and folds `collapsePipelineFor(state)` into the map. The
  3rd `transforms` argument is threaded through `buildViewportScopedLayoutMap` so a
  later sprint binds the gesture with no change to the measure pass — but with no
  handler, no collapse pipeline is ever folded, so collapse is "geometry-ready,
  gesture-dormant."
- The **AccrualView / ChaseThread gutter widgets** are not mounted in
  `MasterMdViewer` (they were never mounted here; SPR-04 built them). They share
  the same anchored-widgets facet that is now proved live against the live map, so
  mounting them is wiring — but it is not done in this sprint (out of scope: M2 is
  minimap/collapse/marginalia wiring).

**M3 recompute strategy (recorded per the milestone):** the pass is
**viewport-scoped** (`createViewportScopedLayoutMap` — off-screen anchors
short-circuit to `null` before the transform pipeline folds, capping per-frame
work to on-screen anchors) AND **debounced** on scroll/resize at
`GEOMETRY_RECOMPUTE_DEBOUNCE_MS = 100ms` (≈6 frames — below the ~100–200ms
"instant" perception threshold so the gutter never feels laggy, coarse enough that
a continuous scroll coalesces ~6 frames of events into ONE rebuild). Overscan is
`VIEWPORT_OVERSCAN_PX = 300` (≈1.5 viewport-heights of reading-column content, so a
block scrolling into view resolves a frame early). Both numbers are SURFACE
constants justified inline at their declaration (the no-magic-number rule); tuning
them never touches the physics. Debounce caps the FREQUENCY of recompute; scope
caps the WORK per recompute — the two together are the "deliberately, not
measure-everything-every-frame" the milestone asks for. The numbers are a
documented starting point, not measured on the real surface yet (the live number
is the one that matters — re-measure if pop-in or jank is observed).

**Measurement failure modes (rigor #3) — how each is handled:**
- **Zero-height anchor** (not yet laid out — first paint before layout, or an
  empty span): a 0×0 rect is dropped at measure time → resolves `null` → the
  widget renders nothing (the layout-map "not laid out" contract), NOT pinned at
  the document origin. A real anchor gains a rect on the next pass once layout
  settles.
- **Off-screen anchor** (laid out, real rect, outside the viewport): KEPT with its
  real rect at measure time; viewport membership is decided downstream by
  `createViewportScopedLayoutMap`, not by dropping at measure (dropping here would
  break the minimap, which wants the whole document's geometry).
- **Reflow-during-measure** (a streamed synthesis still mutating the DOM): the
  measurement is a snapshot pinned to the React commit boundary (`useLayoutEffect`
  runs synchronously after commit, before paint, reading the just-committed tree).
  A later mutation re-renders → the effect re-runs → a fresh snapshot. Never read
  mid-frame.

## Reconsider if

- ~~The surface geometry-measurement pass is built (this gap closes) → mark this doc
  superseded and record the wiring commit + which widgets went live.~~ DONE
  2026-05-27 (see "What actually shipped" — closing commit on branch
  `caffen/lr-spr02`, orchestrator-committed on green).
- **Marginalia needs to light up against real passages** → stamp `data-chunk-id` /
  `data-passage-*` DOM markers on the rendered chunk/passage spans and extend
  `measureClaimGeometry` (rename it) to measure them too. This is the named
  next wedge; the layout-map + augmentation are ready, only the surface markers +
  measure query are missing.
- A different surface than `MasterMdViewer` becomes the canonical reading column →
  the geometry pass + its feed-points move with it; update `readingGeometryPass.ts`
  + the mount.
- The viewport-scoped path proves insufficient at real document sizes once live →
  re-measure on the real surface and revisit the M5 perf decision (the unscoped
  number was always machine-dependent; the live number is the one that matters).
- The debounce/overscan numbers feel laggy or show pop-in on the real surface →
  re-tune `GEOMETRY_RECOMPUTE_DEBOUNCE_MS` / `VIEWPORT_OVERSCAN_PX` (surface
  constants; physics untouched), OR switch the recompute trigger to a
  `ResizeObserver`/`IntersectionObserver` (steelmanned in the SPR-02 handoff — the
  synchronous pre-paint `useLayoutEffect` read was kept as the load-bearing M1
  path; the observer is the alternative if the listener-debounce proves coarse).
