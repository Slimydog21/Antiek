// ─────────────────────────────────────────────────────────────────────────
// The reading-surface GEOMETRY-MEASUREMENT PASS (Living-Roadmap SPR-02 — closes
// the D13 gap, docs/decisions/spr-05-geometry-pass-gap.md).
//
// ── THE PR-4 BOUNDARY LIVES HERE (and ONLY here) ───────────────────────────
//
// This module is the ONE place in the whole reading stack that calls
// `getBoundingClientRect`. The Physics of Reading separates WHERE things are (a
// layout map) from WHAT they do (semantic, pixel-agnostic augmentations — PR-4:
// "augmentations anchor on SEMANTICS, never pixels"). The CI guard
// (`tools/lint/reading_physics_check.py`) FORBIDS `getBoundingClientRect`/
// `offsetTop`/… anywhere under `reading-physics/augmentations/` or
// `reading-physics/facets/`. It does NOT scan this surface module — because the
// SURFACE legitimately owns the DOM and is the only layer allowed to measure it.
//
// A future maintainer MUST NOT move this measurement into an augmentation or a
// facet: doing so re-introduces the exact pixel-coupling PR-4 exists to forbid
// (an augmentation that measured its own pixels would break the moment the
// document folds/zooms/reflows, and SPR-05's transform pipeline could never move
// it for free). The augmentation reads `ctx.layout.resolve(anchor)` — a semantic
// query — and this pass is what gives that query a real answer. Keep the seam:
// pixels in, here; semantic anchors out, everywhere else.
//
// ── HOW geometry enters without the physics measuring it (the layout-map seam) ─
//
//   DOM nodes carrying a semantic marker  (a `[data-claim-id]` claim span)
//        │  getBoundingClientRect (HERE, once per measured node)
//        ▼
//   anchorKey(anchor) → Rect   (a plain Map, the surface's BaseGeometry input)
//        │  baseGeometryFromMap
//        ▼
//   BaseGeometry            (layout-map.ts:71 — the designed constructor, NOT a
//        │                   parallel re-implementation)
//        ▼
//   createLayoutMap(base, transforms)  OR
//   createViewportScopedLayoutMap(base, viewport, transforms)   (layout-map.ts:95 / :177)
//        ▼
//   LayoutMap.resolve(anchor) → Rect | null   ← every augmentation/widget queries this
//
// PR-2 (no side store): the returned map is a pure function of the current DOM
// measurement. It is rebuilt every pass (the surface re-runs the effect on
// scroll/resize); losing it loses nothing.
// ─────────────────────────────────────────────────────────────────────────

import {
  baseGeometryFromMap,
  createLayoutMap,
  createViewportScopedLayoutMap,
} from "../../reading-physics/layout-map";
import type { ViewportBand } from "../../reading-physics/layout-map";
import { anchorKey } from "../../reading-physics/facets/decorations";
import type { Anchor, ClaimId, LayoutMap, Rect } from "../../reading-physics/types";

/**
 * The DOM-marker attribute the surface stamps on a claim span
 * (`data-claim-id={String(claim.index)}` — MasterMdViewer's ClaimBlock). It is
 * the SEMANTIC handle (a synthesis-scoped positional claim index, PR-4), not a
 * pixel — so measuring the node it sits on is the legitimate surface read, and
 * the resulting rect is keyed by the SAME `anchorKey` an augmentation queries.
 */
export const CLAIM_ID_ATTR = "data-claim-id";

/**
 * Measure every laid-out CLAIM anchor under `root` into an `anchorKey → Rect`
 * map, in the coordinate space of `root` (so rects are RELATIVE to the reading
 * column's top-left, stable under page scroll — the surface, not the augmentation,
 * owns this normalisation). This is the ONLY `getBoundingClientRect` caller in the
 * reading stack (the PR-4 seam).
 *
 * Failure modes handled HERE (not waved to the caller — rigor #3):
 *   - ZERO-HEIGHT anchor (not yet laid out — first paint before layout, an empty
 *     span): a 0×0 rect is NOT a real position. We DROP it (omit the key), so the
 *     layout-map resolves it to `null` — exactly the "not currently laid out"
 *     contract a widget already tolerates (it renders nothing) rather than pinning
 *     a widget at the document origin. A real anchor gains a non-zero rect on the
 *     next pass once layout settles.
 *   - OFF-SCREEN anchor (laid out, real rect, but outside the viewport): KEPT with
 *     its real rect — off-screen is a viewport-SCOPE concern, handled by
 *     `createViewportScopedLayoutMap` downstream (M3), NOT by dropping it at
 *     measure time. (Dropping it here would defeat the minimap, which wants the
 *     whole document's geometry.)
 *   - REFLOW-DURING-MEASURE (a streamed synthesis still mutating the DOM): the
 *     measurement is a SNAPSHOT of the DOM at the instant the effect runs
 *     (useLayoutEffect, synchronously after the React commit, before paint — so it
 *     reads the just-committed tree, never a half-applied frame). A later mutation
 *     triggers a re-render → the effect re-runs → a fresh snapshot. We never read
 *     mid-mutation because the read is pinned to the commit boundary.
 */
export function measureClaimGeometry(root: HTMLElement): Map<string, Rect> {
  const rects = new Map<string, Rect>();
  const rootBox = root.getBoundingClientRect();
  const nodes = root.querySelectorAll<HTMLElement>(`[${CLAIM_ID_ATTR}]`);
  for (const node of nodes) {
    const claimId = node.getAttribute(CLAIM_ID_ATTR);
    if (!claimId) continue;
    const box = node.getBoundingClientRect();
    // ZERO-HEIGHT/ZERO-WIDTH → not laid out yet; omit so resolve() returns null.
    if (box.height <= 0 || box.width <= 0) continue;
    const anchor: Anchor = { kind: "claim", claimId: claimId as ClaimId };
    rects.set(anchorKey(anchor), {
      // Normalise into the reading column's own coordinate space (subtract the
      // root's origin) so the map is stable under page scroll and matches the
      // pre-transform space `ViewportBand` is expressed in (M3).
      top: box.top - rootBox.top,
      left: box.left - rootBox.left,
      width: box.width,
      height: box.height,
    });
  }
  return rects;
}

/**
 * The surface's full geometry pass: measure → `baseGeometryFromMap` →
 * `createLayoutMap`. Returns the LIVE layout-map the surface mounts into every
 * render context, replacing `EMPTY_LAYOUT_MAP`.
 *
 * `transforms` is the (currently empty) SPR-05 spatial-transform pipeline —
 * threaded through so a collapse pipeline (`collapsePipelineFor(state)`) folds in
 * with no change to this signature when collapse goes live. Empty ⇒ the map
 * resolves base geometry verbatim (the no-transform identity).
 */
export function buildLayoutMap(
  root: HTMLElement,
  transforms: Parameters<typeof createLayoutMap>[1] = [],
): LayoutMap {
  const rects = measureClaimGeometry(root);
  return createLayoutMap(baseGeometryFromMap(rects), transforms);
}

/**
 * The VIEWPORT-SCOPED geometry pass (M3 — the no-O(n)-jank discipline). Same
 * measure step, but the surface also supplies the visible band (derived from the
 * scroll container) so off-screen anchors short-circuit to `null` before the
 * transform pipeline folds — capping per-frame work to the on-screen anchors.
 *
 * The band is in the SAME pre-transform coordinate space `measureClaimGeometry`
 * produces (root-relative), so the cheap base-rect membership test is apples-to-
 * apples. `buildViewportBand` below derives it from the scroll container.
 */
export function buildViewportScopedLayoutMap(
  root: HTMLElement,
  viewport: ViewportBand,
  transforms: Parameters<typeof createViewportScopedLayoutMap>[2] = [],
): LayoutMap {
  const rects = measureClaimGeometry(root);
  return createViewportScopedLayoutMap(
    baseGeometryFromMap(rects),
    viewport,
    transforms,
  );
}

/**
 * Vertical OVERSCAN (px) padded above and below the visible band so an anchor
 * scrolling INTO view resolves a frame early (no pop-in at the viewport edge).
 *
 * WHY 300 (the no-magic-number rule — defensibility): it is ~1.5× a typical
 * laptop viewport's worth of reading-column content above and below the fold
 * (a claim block + its rationale + citations is ~150–200px; 300px keeps roughly
 * the next/previous block warm). Small enough that per-frame work stays bounded
 * to the on-screen + just-off-screen anchors (the M3 point), large enough that a
 * normal scroll velocity never out-runs the recompute and shows an unresolved
 * gutter. It is a SURFACE constant (the band is the surface's measurement), so
 * tuning it never touches the physics. Not derived from a measurement on the real
 * surface yet (the D13 doc's "the live number is the one that matters") — a
 * deliberate, documented starting point, re-measure if pop-in is observed.
 */
export const VIEWPORT_OVERSCAN_PX = 300;

/**
 * Derive the pre-transform visible band from a scroll container + the reading
 * `root`, padded by `VIEWPORT_OVERSCAN_PX`. Expressed in `root`-relative
 * coordinates (the space `measureClaimGeometry` uses) so it feeds
 * `createViewportScopedLayoutMap` directly. The SURFACE owns this read (it owns
 * the scroll container); the physics never measures the viewport itself (PR-4).
 */
export function buildViewportBand(
  root: HTMLElement,
  scrollContainer: HTMLElement,
): ViewportBand {
  const rootBox = root.getBoundingClientRect();
  const containerBox = scrollContainer.getBoundingClientRect();
  // The container's visible band, translated into root-relative space.
  const topPx = containerBox.top - rootBox.top - VIEWPORT_OVERSCAN_PX;
  const bottomPx = containerBox.bottom - rootBox.top + VIEWPORT_OVERSCAN_PX;
  return { topPx, bottomPx };
}
