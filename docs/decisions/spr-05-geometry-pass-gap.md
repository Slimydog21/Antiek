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
(layout-map.ts:71) → `createLayoutMap` (layout-map.ts:95) via the UNSCOPED
`buildLayoutMap`, and stores the result in state. `EMPTY_LAYOUT_MAP` is **no
longer the mounted map** — it is only the first-paint default (before the first
measure), exactly the honest "nothing laid out yet" state. The header
`renderHeaderQualityCue` pass and the minimap second pass both now run against
this live map.

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

**M3 recompute strategy (recorded per the milestone — corrected in round 2 to
the honest model).** Round 1 mounted a `window` scroll/resize listener feeding a
viewport-scoped map. A verifier-critic returned DO-NOT-MERGE on M3: that machinery
was **misdirected and inert** on this surface. Round 2 corrected it. The honest
model:

- **The base geometry is ROOT-RELATIVE ⇒ SCROLL-INVARIANT.** `measureClaimGeometry`
  normalises every rect by `box.top - rootBox.top` (readingGeometryPass.ts), so
  scrolling the reading column moves the article and its claim spans by the same
  delta and leaves every root-relative rect unchanged. **Scrolling never changes
  the map.** Recompute-on-scroll is therefore unnecessary for correctness — and on
  this surface it never even fired: `MasterMdViewer` is mounted inside an inner
  `overflow-y-auto` scroller (`index.tsx`), and `scroll` events do not bubble to
  `window` from an inner overflow container, so round 1's `window` scroll listener
  was dead. Round 2 **drops the scroll listener entirely.**
- **The recompute trigger is a `ResizeObserver` on the article element.** The only
  events that move root-relative geometry are LAYOUT-SIZE changes — viewport
  resize, web-font load, async content reflow (a streamed synthesis still
  settling). A `ResizeObserver` observing the `articleRef` fires on exactly those,
  uniformly, untied to `window`. It is disconnected in the effect cleanup. The
  initial synchronous `useLayoutEffect` measure (pre-paint, avoids a flash) is
  kept, and `synthesis` stays an effect dependency (new claims ⇒ re-measure). A
  vitest drives this real trigger: it stubs `ResizeObserver` to capture the
  callback, proves the observer is bound to the article, fires the callback, and
  asserts a fresh measurement pass ran (`MasterMdViewer.test.tsx`).
- **Debounce justification is now for the OBSERVER BURST, not scroll.**
  `GEOMETRY_RECOMPUTE_DEBOUNCE_MS = 100ms` (≈6 frames at 60fps — below the
  ~100–200ms "instant" perception threshold so a settle never feels laggy) coalesces
  the rapid BURST of resize callbacks a drag-resize or a streaming reflow emits into
  ONE trailing-edge rebuild. (It is NOT a scroll-frame cap — there is no scroll
  listener.) A surface constant justified inline; tuning it never touches the physics.
- **Viewport-scoping is deliberately NOT mounted on this surface.** Round 1 mounted
  `createViewportScopedLayoutMap`; round 2 mounts the **unscoped** `buildLayoutMap`.
  Scoping would prune NOTHING here: the transform pipeline is empty (SPR-05's
  collapse is unbound this sprint, so there is no per-frame fold cost to cap) AND
  the base geometry is scroll-invariant (the visible band never narrows the resolved
  set). `buildViewportScopedLayoutMap` / `buildViewportBand` / `VIEWPORT_OVERSCAN_PX`
  remain **exported and tested** in `readingGeometryPass.ts` as the **RESERVED PATH**
  for when (a) the reading column becomes its OWN scroll container AND (b) a
  non-empty transform pipeline (SPR-05 collapse) makes per-frame fold cost real — at
  which point the surface switches to the scoped map fed by the real container. Their
  doc comments state this plainly; they are a documented future seam, not dead code.

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
- **The reading column becomes its own scroll container AND a live transform
  pipeline (SPR-05 collapse) is bound** → switch the surface mount from the
  unscoped `buildLayoutMap` to the RESERVED scoped path
  (`buildViewportScopedLayoutMap` fed by `buildViewportBand` off the real
  container). Only then does viewport-scoping prune anything (a non-empty fold has
  per-frame cost to cap) — until BOTH hold, mounting the scoped map would be inert
  machinery. The seam is kept exported + tested for exactly this.
- The debounce number feels laggy on the real surface (a drag-resize or streaming
  reflow settles too slowly, or a single resize feels delayed) → re-tune
  `GEOMETRY_RECOMPUTE_DEBOUNCE_MS` (a surface constant; physics untouched). Note it
  caps the FREQUENCY of the ResizeObserver-BURST recompute, not scroll — there is
  no scroll listener (the map is scroll-invariant).
- A geometry-DEPENDENT change is observed NOT to recompute (a widget stale after a
  layout-size change) → confirm the `ResizeObserver` on the article still fires for
  that change; if the relevant reflow does not resize the article (e.g. an
  ancestor-only change), extend the observed set or add an `IntersectionObserver`,
  but do NOT re-add a scroll listener (it would be dead/misdirected — see the M3
  section).
- The `VIEWPORT_OVERSCAN_PX = 300` overscan shows pop-in once the scoped path is
  mounted → re-tune it (a surface constant on the reserved scoped path; load-bearing
  only after the scoped map is mounted; physics untouched).
