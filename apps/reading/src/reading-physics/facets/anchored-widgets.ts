// ─────────────────────────────────────────────────────────────────────────
// `anchored-widgets` facet (SPR-04 M1) — the canon §5.2 facet.
//
// An augmentation declares an `AnchoredWidget` — a stable `id`, a SEMANTIC
// `anchor` (chunk/claim/passage, never a pixel — PR-4), a `lane`, a `weight`,
// and a pure `render(rect, ctx)`. SPR-02/03 already COLLECTED these into the
// registry's "anchored-widgets" bucket (declareAnchoredWidget) but never enacted
// them. THIS sprint ENACTS them: the facet combines the declared widgets into a
// deterministic, order-independent PLACEMENT PLAN, the surface resolves each
// widget's anchor through the layout-map (§5.3), runs the de-overlap, and calls
// each `render(rect, ctx)`.
//
// This is a NEW facet on the SAME engine (defineFacet, the SPR-03 `Facet<T,R>`
// runtime), not a parallel mechanism — exactly like `decorationsFacet`.
//
// ── THE COMBINE RULE (canon §5.2): de-overlap, deterministic ───────────────
//
// The combine is a PURE function of the SET of declared widgets — independent of
// the order augmentations were enabled in (PR-3 / §4). It does NOT touch
// geometry (that is the layout-map's job, applied at enact); it produces the
// order-independent STACKING PLAN the enact then resolves against pixels:
//
//   1. Widgets in DIFFERENT lanes never collide → grouped by `lane`.
//   2. Within a lane, widgets are ordered by the §5.2 tie-break:
//        weight DESC (higher = nearer its anchor, wins the slot),
//        then id ASC (lexicographic) for equal weights — total + stable.
//      This ordering is the de-overlap PRIORITY: when two same-lane widgets'
//      resolved rects overlap vertically, the earlier one in this order takes
//      the slot nearest its anchor and the later one stacks just below.
//   3. Lanes are emitted in a fixed lane order so the plan itself is a total,
//      order-independent value (a shuffled input yields a deep-equal plan).
//
// So the resolved plan is a pure function of `(lane, weight, id)` — the
// vertical PIXEL position (the resolved rect) decides WHETHER two widgets in a
// lane actually overlap, but the ORDER in which an overlapping pair stacks is
// fixed here, independent of declaration order. That split is what makes the
// determinism test meaningful AND keeps PR-4 honest (no pixel in the combine).
//
// PR-1 (declare, don't act): augmentations only DECLARE `AnchoredWidget` values;
// this module COMBINES them. The surface owns the single enact pass that places
// + paints — nothing here touches the DOM.
// ─────────────────────────────────────────────────────────────────────────

import { defineFacet } from "../facet";
import type { Facet } from "../facet";
import { anchorKey } from "./decorations";
import type { AnchoredWidget, LayoutMap, Rect, RenderContext, WidgetLane } from "../types";

/** The fixed lane order the plan emits lanes in (so the combined value is total
 *  and order-independent). Left-to-right reading order; purely a determinism
 *  device — different lanes never collide, so this order has no UX meaning. */
const LANE_ORDER: readonly WidgetLane[] = [
  "left-gutter",
  "inline-end",
  "right-gutter",
];

/** A widget's place within its lane's stacking order (M1). `stackIndex` is its
 *  0-based rank under the §5.2 tie-break (weight desc, id asc): rank 0 takes the
 *  slot nearest its anchor; a higher rank stacks below an overlapping lower one.
 *  The widget itself is carried so the enact can resolve + render it. */
export interface PlacedWidget {
  readonly widget: AnchoredWidget;
  /** The widget's lane (denormalised from `widget.lane` for the enact's grouping). */
  readonly lane: WidgetLane;
  /** 0-based stacking rank within the lane (de-overlap priority). */
  readonly stackIndex: number;
}

/**
 * The combined placement plan for one render pass (M1). Widgets grouped by lane,
 * each lane in stacking order. A pure, order-independent function of the SET of
 * declared widgets — NO geometry (the enact resolves rects via the layout-map).
 *
 * `byLane` is a plain array of (lane, ordered widgets) entries in `LANE_ORDER`
 * so the value is a total, deep-equal-comparable structure (the determinism
 * test compares two plans with `toEqual`). A flat `all` list (in lane-then-stack
 * order) is provided for the enact's convenience.
 */
export interface ResolvedWidgetLayout {
  readonly byLane: readonly { readonly lane: WidgetLane; readonly widgets: readonly PlacedWidget[] }[];
  readonly all: readonly PlacedWidget[];
}

/** The §5.2 tie-break comparator: weight DESC, then id ASC (lexicographic).
 *  Total + stable → the sort is deterministic and order-independent. */
function byWeightThenId(a: AnchoredWidget, b: AnchoredWidget): number {
  if (a.weight !== b.weight) return b.weight - a.weight; // higher weight first
  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0; // ties: id ascending
}

/**
 * COMBINE RULE (canon §5.2): de-overlap, deterministic, ORDER-INDEPENDENT.
 *
 * Group by `lane`; within each lane order by (weight desc, id asc); emit lanes
 * in `LANE_ORDER`. The result is a pure function of the SET of widgets — a
 * shuffled `widgets` array yields a deep-equal plan.
 *
 * Edge cases (rigor #3):
 *   - empty input                  → { byLane: [], all: [] } (no-op);
 *   - widgets in different lanes   → never collide (separate lane groups);
 *   - two widgets, same lane       → ordered by weight then id (stack plan);
 *   - duplicate id in a lane       → still totally ordered (id is the final
 *     tie-break; two equal (weight,id) pairs would be an authoring error, but
 *     the sort stays stable so the output is still deterministic).
 *
 * NOTE no rect appears here: WHETHER two same-lane widgets overlap is a pixel
 * question the layout-map answers at enact; the ORDER they stack in is fixed
 * here. Keeping geometry out of the combine is what keeps the combine a pure,
 * order-independent function (PR-3) and the facet pixel-read-free (PR-4).
 */
export function combineAnchoredWidgets(
  widgets: readonly AnchoredWidget[],
): ResolvedWidgetLayout {
  const byLaneMap = new Map<WidgetLane, AnchoredWidget[]>();
  for (const w of widgets) {
    let bucket = byLaneMap.get(w.lane);
    if (!bucket) {
      bucket = [];
      byLaneMap.set(w.lane, bucket);
    }
    bucket.push(w);
  }

  const byLane: { lane: WidgetLane; widgets: PlacedWidget[] }[] = [];
  const all: PlacedWidget[] = [];
  for (const lane of LANE_ORDER) {
    const bucket = byLaneMap.get(lane);
    if (!bucket || bucket.length === 0) continue;
    const ordered = [...bucket].sort(byWeightThenId);
    const placed = ordered.map((widget, stackIndex) => ({ widget, lane, stackIndex }));
    byLane.push({ lane, widgets: placed });
    for (const p of placed) all.push(p);
  }

  return { byLane, all };
}

/**
 * The `anchored-widgets` facet as a first-class `Facet<AnchoredWidget, …>` (M1).
 *
 * `priority` is the facet's Z-ORDER. Gutter widgets sit ABOVE the base
 * decorations layer (decorationsFacet priority 0) so a badge in the gutter is
 * never hidden behind a range highlight (canon: SPR-04's gutter widgets are a
 * higher priority). Priority is a property of the FACET fixed by the surface,
 * never of which augmentation declared first — that keeps cross-facet overlap
 * order-independent. `assertDistinctPriorities` over the surface's roster
 * rejects a clash with decorations (0).
 */
export const anchoredWidgetsFacet: Facet<AnchoredWidget, ResolvedWidgetLayout> =
  defineFacet({
    name: "anchored-widgets",
    priority: 10,
    combine: (contributions) => combineAnchoredWidgets(contributions),
  });

// ── Enact helpers (M1) — resolve the plan against the layout-map ───────────
//
// The combine produced the order-independent STACKING PLAN; enact turns it into
// final rects by resolving each widget's anchor through the layout-map and
// applying the vertical de-overlap WITHIN each lane. This is the surface's
// "resolve + place" step; it is a pure function of (plan, layoutMap), so it is
// testable headlessly and SPR-05 composes its transform by handing in a
// layout-map whose `resolve` already folded the transform.

/** A widget after enact: its final resolved rect (post-transform, post-stack),
 *  or `null` when its anchor is not laid out (off-screen / folded / withheld).
 *  A null-rect widget renders nothing — the surface skips it (or calls render
 *  with null per the frozen contract; both yield nothing). */
export interface EnactedWidget {
  readonly widget: AnchoredWidget;
  readonly lane: WidgetLane;
  readonly stackIndex: number;
  /** The final rect the widget's `render` receives. `null` ⇒ not laid out. */
  readonly rect: Rect | null;
}

/** Default vertical gap (px) inserted between two STACKED (overlapping) widgets
 *  in a lane. Small + fixed; the surface may widen it, but a constant keeps the
 *  de-overlap deterministic. */
const STACK_GAP_PX = 8;

/**
 * Resolve a placement plan against the layout-map, applying the §5.2 vertical
 * de-overlap within each lane (M1 enact). Pure: `(plan, layout) → enacted[]`.
 *
 * Per lane (in the plan's stacking order):
 *   - resolve the widget's anchor via `layout.resolve` (the SINGLE geometry
 *     read — PR-5; this is the layout-map's job, not the widget's — PR-4);
 *   - a `null` resolution means "not laid out" → the widget keeps a null rect
 *     (renders nothing) and does NOT consume a slot;
 *   - otherwise, if its resolved top would overlap the previous placed widget's
 *     occupied band in this lane, push it DOWN to just below that band
 *     (`prevBottom + STACK_GAP_PX`). The FIRST (highest-priority) widget at a
 *     position keeps the slot nearest its anchor; later ones stack below — the
 *     canon §5.2 outcome. Because the stacking ORDER came from the combine
 *     (weight desc, id asc), the de-overlap is independent of declaration order.
 *
 * Different lanes are resolved independently (they never collide — §5.2).
 */
export function enactWidgetLayout(
  plan: ResolvedWidgetLayout,
  layout: LayoutMap,
): EnactedWidget[] {
  const enacted: EnactedWidget[] = [];
  for (const { lane, widgets } of plan.byLane) {
    // The bottom edge of the last PLACED (non-null) widget in this lane, so the
    // next overlapping widget stacks below it. Reset per lane.
    let laneOccupiedBottom: number | null = null;
    for (const { widget, stackIndex } of widgets) {
      const base = layout.resolve(widget.anchor);
      if (base === null) {
        // Not laid out → null rect, renders nothing, consumes no slot.
        enacted.push({ widget, lane, stackIndex, rect: null });
        continue;
      }
      let top = base.top;
      if (laneOccupiedBottom !== null && top < laneOccupiedBottom) {
        // Overlap with the band already taken by a higher-priority widget in
        // this lane → stack just below it.
        top = laneOccupiedBottom + STACK_GAP_PX;
      }
      const rect: Rect = { top, left: base.left, width: base.width, height: base.height };
      laneOccupiedBottom = top + base.height;
      enacted.push({ widget, lane, stackIndex, rect });
    }
  }
  return enacted;
}

/**
 * The full surface step: combine the declared widgets into a plan, then enact it
 * against the layout-map (M1). A convenience the surface calls; equivalent to
 * `enactWidgetLayout(anchoredWidgetsFacet.combine(widgets), layout)`. Pure and
 * deterministic in (widgets, layout): a shuffled `widgets` yields an enacted set
 * deep-equal to the original (the determinism test proves this end-to-end).
 */
export function resolveAnchoredWidgets(
  widgets: readonly AnchoredWidget[],
  layout: LayoutMap,
): EnactedWidget[] {
  return enactWidgetLayout(anchoredWidgetsFacet.combine(widgets), layout);
}

/** Re-export `anchorKey` so a reader of the widget enact sees the same stable
 *  semantic key the decorations facet uses (single source of truth; this is the
 *  key the surface's `BaseGeometry` is keyed by). */
export { anchorKey };

/** Run an enacted widget's render with its resolved rect + the context (M1).
 *  A thin helper so the surface calls one function per widget; keeps the
 *  frozen `render(rect, ctx)` call in one place. */
export function renderEnacted(e: EnactedWidget, ctx: RenderContext) {
  return e.widget.render(e.rect, ctx);
}
