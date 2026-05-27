// ─────────────────────────────────────────────────────────────────────────
// The layout-map service (SPR-04 M2 / M3) — the canon §5.3 facet.
//
// THE HINGE OF THE WHOLE PHYSICS. The layout-map is what separates "WHAT to
// show" (the widget/decoration an augmentation declares) from "WHERE to show
// it" (the resolved pixel rect). It is the SINGLE read-time resolver every
// anchored widget queries — `resolve(anchor): Rect | null` — and it is the ONE
// seam SPR-05's spatial transform composes into. Design it as a queryable
// service, NOT as positioning baked into each widget (canon §5.3, sprint M2).
//
// WHY a service, not per-widget positioning (defensibility / the SPR-05 seam):
//   - PR-4: widgets anchor by SEMANTIC identity (chunk/claim/passage), never a
//     pixel. A pixel measured at mount is wrong the instant the document is
//     folded, zoomed, reflowed, themed, resized, or rendered a second time
//     (minimap). The price of spatial composability is the indirection: a
//     widget asks "where is my anchor NOW?" and the service answers — AFTER any
//     transform has been folded in.
//   - PR-5: because there is ONE place that knows geometry, SPR-05 can insert a
//     `SpatialTransform` pipeline HERE and every widget follows for free — none
//     of them learns the geometry moved. If each widget measured its own pixels
//     (the rejected §11.6 alternative) SPR-05 would have to edit every widget.
//   - O(facets) (canon §4): the surface composes N widgets through ONE resolver,
//     not N bespoke geometry derivations.
//
// HOW geometry enters WITHOUT the physics measuring it (PR-4 honesty): the
// SURFACE — which legitimately owns the DOM — measures the base geometry of each
// laid-out anchor and hands the layout-map a `BaseGeometry` lookup (a plain
// `anchorKey → Rect` map). The layout-map then composes the (currently empty,
// SPR-05-reserved) spatial-transform pipeline over that base and reports the
// FINAL rect. So no module under reading-physics/ ever calls
// getBoundingClientRect — the surface does, once, and feeds the result in. The
// physics stays pixel-read-free (the PR-4 grep over augmentations/ is clean).
//
// PR-2 (no side store): the layout-map holds the base geometry + transforms for
// ONE render pass and nothing more. It is reconstructed every render from the
// surface's current measurements; losing it loses nothing.
// ─────────────────────────────────────────────────────────────────────────

import { anchorKey } from "./facets/decorations";
import type {
  Anchor,
  LayoutMap,
  Rect,
  SpatialTransform,
  WidgetLane,
} from "./types";

/**
 * The base geometry the SURFACE supplies — a lookup from a semantic anchor's
 * stable key (`anchorKey`) to its measured rect in the reading surface's
 * coordinate space, BEFORE any spatial transform. An anchor absent from the
 * lookup is "not currently laid out" (off-screen / collapsed / excluded by the
 * render pass) and resolves to `null`.
 *
 * It is keyed by `anchorKey` (not by `Anchor` object identity) for the same
 * reason the decorations combine is: the key is a pure function of the anchor's
 * semantic fields, so two structurally-equal anchors resolve identically. The
 * surface builds this map by measuring each laid-out anchor's DOM node once per
 * pass — the ONE place getBoundingClientRect is legitimately called.
 */
export interface BaseGeometry {
  /** Resolve a semantic anchor's PRE-transform rect, or null if not laid out. */
  rectForKey(key: string): Rect | null;
}

/**
 * Build a `BaseGeometry` from a plain `anchorKey → Rect` record (the common
 * surface case: it measured the laid-out anchors into a map). A convenience
 * over hand-implementing the interface.
 */
export function baseGeometryFromMap(
  rects: ReadonlyMap<string, Rect>,
): BaseGeometry {
  return {
    rectForKey: (key) => rects.get(key) ?? null,
  };
}

/**
 * Create the layout-map service for ONE render pass (canon §5.3).
 *
 * @param base       the surface-measured base geometry (pre-transform).
 * @param transforms the spatial-transform pipeline (SPR-05). EMPTY this sprint —
 *                   SPR-04 builds the map so it CAN compose a transform; it does
 *                   not add one (out of scope). The pipeline is applied in
 *                   ASCENDING `order` (ties by `id`, lexicographic) — the canon
 *                   §5.4 ordered, NOT order-independent, composition. A transform
 *                   returning `null` removes the anchor from this pass (a folded
 *                   section); the layout-map then resolves that anchor to `null`.
 *
 * The returned `LayoutMap` is the frozen §6 shape (`resolve`) plus the SPR-04
 * `positionOf` convenience. `resolve` is the single point that knows geometry;
 * widgets/decorations/SPR-05 all go through it.
 */
export function createLayoutMap(
  base: BaseGeometry,
  transforms: readonly SpatialTransform[] = [],
): LayoutMap {
  // Sort the pipeline ONCE: ascending `order`, ties broken by `id`
  // (lexicographic) — the canon §5.4 deterministic ordering. This is the ONE
  // place order is load-bearing in the whole physics (fold-then-zoom ≠
  // zoom-then-fold), so it is explicit and justified, never "happens to work."
  const pipeline = [...transforms].sort((a, b) =>
    a.order !== b.order ? a.order - b.order : a.id < b.id ? -1 : a.id > b.id ? 1 : 0,
  );

  function resolve(anchor: Anchor): Rect | null {
    // 1. Base geometry from the surface (pre-transform).
    let rect = base.rectForKey(anchorKey(anchor));
    // 2. Fold the spatial-transform pipeline in order (SPR-05 seam). Empty this
    //    sprint, so `resolve` returns the base rect verbatim — the no-transform
    //    identity. A transform may move the rect or drop the anchor (null).
    for (const t of pipeline) {
      rect = t.apply(anchor, rect);
      // Once a transform removes the anchor (null), later transforms see null
      // and the canon-frozen contract lets them re-introduce it or keep it out;
      // we pass the running value through so the pipeline composes honestly.
    }
    return rect;
  }

  function positionOf(
    anchor: Anchor,
    lane: WidgetLane,
  ): { top: number; side: WidgetLane } | null {
    const rect = resolve(anchor);
    if (rect === null) return null;
    // The named, ergonomic read (sprint M2): the resolved top edge + the lane
    // the caller intends. A thin derivation over `resolve` — never a second
    // geometry path, so it sees every transform `resolve` did.
    return { top: rect.top, side: lane };
  }

  return { resolve, positionOf };
}

/**
 * The empty layout-map: every anchor resolves to `null` (nothing is laid out).
 * The honest default when the surface has measured nothing yet (first paint
 * before the geometry pass) or in a headless/test context with no DOM. A widget
 * MUST tolerate this by rendering nothing — which the de-overlap enact relies
 * on. Identical in effect to the SPR-02/03 `{ resolve: () => null }` stub, but a
 * named, shared value so callers do not re-spell it.
 */
export const EMPTY_LAYOUT_MAP: LayoutMap = {
  resolve: () => null,
  positionOf: () => null,
};
