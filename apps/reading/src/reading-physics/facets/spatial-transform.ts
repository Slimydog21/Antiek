// ─────────────────────────────────────────────────────────────────────────
// `spatial-transform` facet (SPR-05 M1) — the canon §5.4 facet.
//
// THE TALK'S SIGNATURE READING CAPABILITY. A spatial transform is a read-side
// remap of WHERE content appears (LiquidText-style: hold a modifier + scroll to
// COLLAPSE a section, compressing it spatially). It composes with decorations
// like a FRAGMENT SHADER over a VERTEX SHADER (canon §5.4 / PR-5): the transform
// moves the VERTICES (the geometry the layout-map reports); decorations and
// widgets paint the FRAGMENTS (what appears) and follow the moved geometry
// AUTOMATICALLY because they only ever query the layout-map's FINAL rect — never
// a pre-transform pixel. No augmentation learns the document was reshaped.
//
// ── THE FROZEN §6 SHAPE (types.ts `SpatialTransform`) ──────────────────────
//
//   interface SpatialTransform {
//     readonly id: string;                                  // stable; tie-break key
//     readonly order: number;                               // pipeline position
//     apply(anchor: Anchor, rect: Rect | null): Rect | null // remap, or null to drop
//   }
//
// This module BUILDS instances of that frozen shape — it adds no new type. The
// layout-map (`createLayoutMap`, layout-map.ts) folds the sorted pipeline by
// ASCENDING `order` (ties by `id`, lexicographic) when resolving any anchor, so
// `resolve(anchor)` returns POST-transform geometry. SPR-04 built that seam
// EMPTY and reserved for SPR-05; this sprint FILLS it.
//
// ── THE COMBINE RULE (canon §5.4): an ORDERED pipeline — NOT order-independent ─
//
// Unlike decorations (range union, order-independent) and anchored-widgets
// (de-overlap, order-independent), spatial transforms compose as an EXPLICIT
// ORDERED pipeline. Order is load-bearing BY DESIGN: fold-then-zoom ≠
// zoom-then-fold. The canon makes ordering explicit and justified rather than
// pretending it commutes. The layout-map owns the sort; this module's transforms
// only carry an `order`. Two collapses compose deterministically: each maps the
// running rect, in `order` sequence (proved in the test).
//
// ── OQ2 RESOLUTION (canon §9 open question 2) — SURFACE-DECLARED ONLY ──────
//
// The canon's §9 OQ2 (owned by SPR-05) asks whether spatial transforms are
// surface-reserved or augmentation-declarable. SPR-05 RESOLVES it the safe way:
// **spatial transforms are SURFACE-DECLARED ONLY.** A `ReadingAugmentation` never
// calls `registry.declareSpatialTransform` — the SURFACE (which owns the geometry
// and the collapse view-state) constructs the pipeline and hands it to
// `createLayoutMap`. This sidesteps the cross-augmentation ordering conflict OQ2
// names entirely (two augmentations declaring conflicting transforms at the same
// `order` would have no "right" order). The frozen `declareSpatialTransform` sink
// stays in `FacetRegistry` (no canon change), but the surface is its only caller.
// SPR-08's agent reads this: a transform-class augmentation is NOT yet a thing an
// agent authors — it declares decorations/widgets, which FOLLOW transforms for
// free. See docs/decisions/ + the canon §9 OQ2 note.
//
// PR-2 (no side store): a transform is a pure VALUE (id + order + a pure `apply`).
// It holds no per-render state; the surface reconstructs the pipeline each render
// from the (ephemeral, view-only) collapse state. Losing it loses nothing.
// PR-4/PR-5: `apply` operates on an `Anchor` + a `Rect | null` — semantic
// identity + the layout-map's resolved geometry. It NEVER measures a pixel; the
// surface measured the base geometry once and the transform only remaps it.
// ─────────────────────────────────────────────────────────────────────────

import { anchorKey } from "./decorations";
import type { Anchor, Rect, SpatialTransform } from "../types";

/**
 * A half-open vertical RANGE in the reading surface's coordinate space that a
 * collapse compresses. `[topPx, bottomPx)` — content whose resolved top falls
 * inside the range is compressed; content BELOW the range shifts up by the
 * amount removed; content ABOVE is untouched.
 *
 * Expressed in the SAME pre-transform pixel space the layout-map's BaseGeometry
 * uses (the surface measured it). This is NOT an augmentation reading a pixel
 * (PR-4): the SURFACE owns the collapse range — it decided which on-screen band
 * to fold, from the section the user gestured over — and a transform is a
 * surface-declared value (OQ2). The transform's `apply` is still pure geometry
 * math over the layout-map's resolved rects; it measures nothing itself.
 */
export interface CollapseRange {
  /** The pre-transform top edge of the collapsed band (inclusive). */
  readonly topPx: number;
  /** The pre-transform bottom edge of the collapsed band (exclusive). */
  readonly bottomPx: number;
}

/** A collapse transform's parameters (the surface-declared facet contribution
 *  the manual names: `{ range, mode: "collapse", targetHeight }`). */
export interface CollapseSpec {
  /** Stable id (also the pipeline tie-break key when two transforms share an
   *  `order`). The surface mints one per collapsed section. */
  readonly id: string;
  /** Pipeline position (ascending `order` runs first; ties by `id`). The
   *  surface assigns ascending orders to collapses TOP-to-bottom so they compose
   *  predictably (a later/lower collapse sees the earlier one's shift). */
  readonly order: number;
  /** The (pre-transform) vertical band this collapse compresses. */
  readonly range: CollapseRange;
  /** The mode — `"collapse"` is the only mode SPR-05 ships (the canon's
   *  signature transform). Other variants (expand-whitespace / zoom / reflow) are
   *  left for agent-authored augmentations (SPR-08) and are explicitly OOS. The
   *  literal is on the spec so the surface (and a future variant) can branch. */
  readonly mode: "collapse";
  /** The compressed height the collapsed band occupies POST-transform (the
   *  "fingerprint band" height — small but non-zero so the band, and the
   *  decorations compressed into it, stay visible). Must be ≥ 0 and ≤ the band's
   *  original height (a collapse never makes a section taller). */
  readonly targetHeight: number;
}

/**
 * The original (pre-transform) height of a collapse band. A convenience so the
 * surface can validate `targetHeight ≤ originalHeight` and so the test can
 * reason about the amount removed.
 */
export function collapseBandHeight(range: CollapseRange): number {
  return Math.max(0, range.bottomPx - range.topPx);
}

/**
 * Build a `SpatialTransform` (the frozen §6 shape) that COLLAPSES a vertical
 * band to `targetHeight` (canon §5.4, sprint M1/M2). The returned transform's
 * `apply(anchor, rect)`:
 *
 *   - rect === null            → null (already not laid out; pass through).
 *   - rect ABOVE the band      → unchanged (top + bottom both < range.topPx).
 *   - rect INSIDE the band     → COMPRESSED into the fingerprint band. Its top is
 *                                mapped proportionally into [range.topPx,
 *                                range.topPx + targetHeight) and its height is
 *                                scaled by (targetHeight / originalHeight). A rect
 *                                that spanned the whole band lands as the whole
 *                                (short) fingerprint band; a decoration partway
 *                                down the band lands partway down the fingerprint.
 *                                This is what makes decorations COMPRESS into a
 *                                band rather than vanish (M2): the geometry moved,
 *                                the decoration follows it, the surface paints the
 *                                squeezed colors.
 *   - rect BELOW the band      → SHIFTED UP by `removed` (= originalHeight −
 *                                targetHeight), the amount the collapse removed,
 *                                so content below closes the gap (the LiquidText
 *                                "push content together").
 *   - rect STRADDLING the boundary → the part inside compresses, the part below
 *                                shifts; we map its top by the inside rule and its
 *                                bottom by the below rule, then derive height —
 *                                so a decoration straddling the fold stays
 *                                contiguous (no gap, no overlap). Rigor #3 case.
 *
 * Pure geometry math over the resolved rect — measures nothing (PR-4). A
 * `targetHeight` ≥ the band height is clamped to the band height (a no-op
 * collapse) so a mis-specified spec never makes a section TALLER. A negative
 * `targetHeight` is clamped to 0 (fully folded to a hairline; decorations inside
 * land on the hairline — still not dropped, so the fingerprint is at minimum a
 * 1px-ish colored line, never withheld content; §9.0 honesty rides on the
 * decoration carrying NO body, which is upstream of this geometry).
 */
export function makeCollapseTransform(spec: CollapseSpec): SpatialTransform {
  const { topPx, bottomPx } = spec.range;
  const originalHeight = collapseBandHeight(spec.range);
  // Clamp targetHeight into [0, originalHeight]: a collapse compresses, never
  // expands (expand-whitespace is OOS — SPR-08), and never goes negative.
  const targetHeight = Math.min(
    Math.max(0, spec.targetHeight),
    originalHeight,
  );
  const removed = originalHeight - targetHeight; // ≥ 0; the gap the collapse closes
  // The scale a point's offset INTO the band maps by (the fingerprint factor).
  // Guard the zero-height band (no-op) to avoid a divide-by-zero.
  const scale = originalHeight > 0 ? targetHeight / originalHeight : 0;

  /** Map a single pre-transform Y coordinate through the collapse. */
  function mapY(y: number): number {
    if (y <= topPx) return y; // above the band — untouched
    if (y >= bottomPx) return y - removed; // below the band — shift up
    // inside the band — compress proportionally into the fingerprint band.
    return topPx + (y - topPx) * scale;
  }

  return {
    id: spec.id,
    order: spec.order,
    apply(_anchor: Anchor, rect: Rect | null): Rect | null {
      if (rect === null) return null;
      // No-op collapse (nothing removed) → identity, so the pipeline composes
      // honestly with a degenerate collapse.
      if (removed === 0) return rect;
      const top = mapY(rect.top);
      const bottom = mapY(rect.top + rect.height);
      // Derive the post-transform height from the two mapped edges so a rect
      // STRADDLING the boundary (top inside, bottom below — or vice versa) stays
      // contiguous: its compressed part + its shifted part add up with no gap.
      const height = Math.max(0, bottom - top);
      return { top, left: rect.left, width: rect.width, height };
    },
  };
}

/**
 * Build the surface's collapse pipeline from a set of collapse specs (M1). A
 * thin convenience: maps each spec to a `SpatialTransform`. The layout-map sorts
 * the pipeline by (order, id) — this does NOT pre-sort (the layout-map owns the
 * sort, the single place ordering is load-bearing), so callers may pass specs in
 * any order. SURFACE-DECLARED ONLY (OQ2): augmentations never call this.
 *
 * Two collapses compose deterministically: the layout-map applies them in
 * ascending `order`; each sees the running rect the previous produced, so a
 * lower collapse correctly accounts for an earlier one's upward shift.
 *
 * SUPPORTED CASE = DISJOINT bands. `collapseSpecsFor` derives bands from DISTINCT
 * sections, which are normally disjoint. OVERLAPPING (non-disjoint) bands are
 * semantically UNSPECIFIED: each band's `range` is in PRE-transform coordinates,
 * so a later band that overlaps an earlier one sees STALE coordinates (the earlier
 * fold already shifted content). The composition stays SAFE — still monotonic (no
 * anchor-crossing; proved in the test) — but the exact compression of the overlap
 * is unspecified. Callers should pass disjoint bands.
 */
export function buildCollapsePipeline(
  specs: readonly CollapseSpec[],
): SpatialTransform[] {
  return specs.map(makeCollapseTransform);
}

/**
 * Whether an anchor's RESOLVED (pre-transform) rect falls INSIDE a collapse band
 * (M2). The surface uses this to decide which decorations to paint as a
 * compressed FINGERPRINT (the band) vs in full: a decoration whose anchor
 * resolves inside the band is "in the fingerprint." Pure geometry over a rect the
 * layout-map already resolved — no pixel read here. `anchorKey` is imported only
 * to keep the same stable-key vocabulary available to callers; the test uses it.
 */
export function rectInCollapseBand(rect: Rect, range: CollapseRange): boolean {
  // The rect's vertical midpoint inside the half-open band [topPx, bottomPx).
  const mid = rect.top + rect.height / 2;
  return mid >= range.topPx && mid < range.bottomPx;
}

/** Re-export `anchorKey` so a reader of the transform sees the same stable
 *  semantic key the decorations + layout-map use (single source of truth). */
export { anchorKey };
