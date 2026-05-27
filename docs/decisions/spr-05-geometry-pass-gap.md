# SPR-05 — the surface geometry-measurement pass is not yet built (collapse + minimap ship dormant)

**Date:** 2026-05-27
**Branch:** `physics/spr-05` (worktree `antiek-physics-spr05`)
**Source spec:** `docs/philosophy/physics-of-reading.md` (the canon) + SPR-05 sprint
**Status:** SPR-05 capability complete + tested; **dormant** — mounted nowhere live.
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

## Reconsider if

- The surface geometry-measurement pass is built (this gap closes) → mark this doc
  superseded and record the wiring commit + which widgets went live.
- A different surface than `MasterMdViewer` becomes the canonical reading column →
  the EMPTY_LAYOUT_MAP feed-points move with it; update the line references.
- The viewport-scoped path proves insufficient at real document sizes once live →
  re-measure on the real surface and revisit the M5 perf decision (the unscoped
  number was always machine-dependent; the live number is the one that matters).
