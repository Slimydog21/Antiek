// ─────────────────────────────────────────────────────────────────────────
// The reading minimap (SPR-05 M4) — a SECOND RENDER PASS of the SAME facets.
//
// THE PR-5 PAYOFF. Because "what to show" (a decoration/widget an augmentation
// declared) is cleanly separated from "where to show it" (the layout-map's
// resolved pixel), the surface can render the SAME facets MORE THAN ONCE. The
// minimap is exactly that: a second `RenderContext` with `pass: "minimap"` and
// its OWN layout-map (compressed geometry), running the SAME decoration-facet
// resolution the main view used. It is NOT a re-implementation of the decoration
// logic — it consumes the identical `ResolvedDecoration[]` the main column paints
// and re-projects it at minimap scale. No augmentation knows there is a second
// pass (canon §5.5 / §8 case 4).
//
// This lives at reading-physics/ root (NOT under augmentations/) because it is a
// SURFACE render component, not an augmentation — it legitimately renders JSX and
// owns geometry projection. It imports the decorations facet's RESOLVED type +
// the layout-map, never re-deriving the combine.
//
// PR-5 (what/where separation): the minimap takes the SAME resolved decorations
// and asks ITS layout-map where each anchor sits — a different `resolve`, same
// `what`. Prove-out: the minimap's decoration set is byte-derived from the main
// view's resolution (the test asserts `minimapDecorations === sameResolvedSet`).
// PR multi-render (§5.5): `contribute()` runs once per context; the minimap is a
// pure function of (resolved facets, minimap layout-map) — no cross-pass state.
// ─────────────────────────────────────────────────────────────────────────

import { createElement } from "react";
import type { ReactNode } from "react";

import type { ResolvedDecoration } from "./facets/decorations";
import type { Anchor, LayoutMap, Rect, RenderContext } from "./types";

/**
 * One decoration projected into the minimap (M4). It carries the SAME resolved
 * decoration the main view paints (its classes/title/widgets/owners) plus the
 * minimap-scale rect its anchor resolves to in the minimap's layout-map. The
 * `decoration` field is a REFERENCE to the main view's resolved value — not a
 * re-derivation — which is what makes "shares the facet" literally true.
 */
export interface MinimapMark {
  /** The resolved decoration the main view also paints (shared, not re-derived). */
  readonly decoration: ResolvedDecoration;
  /** Where the decoration's anchor sits in the MINIMAP's coordinate space, or
   *  null when the anchor is not laid out in the minimap (off its viewport). */
  readonly rect: Rect | null;
}

/**
 * Project the main view's resolved decorations into the minimap (M4) — the
 * second render pass. Given the EXACT `ResolvedDecoration[]` the main view's
 * decorations facet produced (NOT a re-combine) and the minimap's own
 * layout-map, resolve each decoration's anchor at minimap scale.
 *
 * This is the load-bearing "shares the facet, not a re-impl" step: the input IS
 * the main view's resolution; this function only re-projects geometry through a
 * second `resolve`. A different `RenderContext.layout` (the minimap's) gives
 * different pixels; the `what` is identical (canon §5.5).
 *
 * A null-resolving anchor (not in the minimap viewport) keeps a null rect — the
 * surface paints nothing for it, exactly as a widget tolerates a null rect.
 */
export function projectDecorationsToMinimap(
  resolved: readonly ResolvedDecoration[],
  minimapLayout: LayoutMap,
): MinimapMark[] {
  return resolved.map((decoration) => ({
    decoration, // the SAME resolved value the main view paints — shared
    rect: minimapLayout.resolve(decoration.anchor),
  }));
}

/**
 * A minimap-scale layout-map (M4) derived from the main view's layout-map by a
 * uniform vertical compression. The minimap is the whole document squeezed into a
 * narrow column, so each anchor's main-view top is scaled by `scale` (< 1) and
 * its height likewise; left/width collapse to the minimap's own column.
 *
 * This is a SECOND layout-map instance (canon §5.5: "each with its own
 * layout-map instance"), built by WRAPPING the main view's `resolve` — so it sees
 * every spatial transform the main view's layout-map already folded in (a
 * collapsed section is collapsed in the minimap too, for free). It measures no
 * pixel of its own; it re-scales the rects the main layout-map resolved.
 *
 * @param mainLayout   the main view's layout-map (post-transform geometry).
 * @param scale        vertical compression factor (0 < scale ≤ 1).
 * @param columnWidth  the minimap column's width in px.
 */
export function minimapLayoutFrom(
  mainLayout: LayoutMap,
  scale: number,
  columnWidth: number,
): LayoutMap {
  const s = Math.min(Math.max(0, scale), 1);
  return {
    resolve(anchor: Anchor): Rect | null {
      const r = mainLayout.resolve(anchor);
      if (r === null) return null;
      return {
        top: r.top * s,
        left: 0, // the minimap is its own narrow column
        width: columnWidth,
        height: Math.max(1, r.height * s), // ≥ 1px so a mark stays visible
      };
    },
  };
}

/** The minimap's `RenderContext` (M4). `pass: "minimap"` is the frozen §6
 *  multi-render pass marker; `layout` is the minimap's own compressed layout-map.
 *  No `components` (the minimap shows decoration colors, not heavy widgets). */
export function minimapRenderContext(minimapLayout: LayoutMap): RenderContext {
  return { pass: "minimap", layout: minimapLayout };
}

/**
 * Render the minimap (M4) — a narrow column of colored marks, one per decoration,
 * at the minimap-scale position. The colors are the SAME decoration classes the
 * main view paints (the rhetorical / servability colors), so the minimap is a
 * faithful compressed overview — a fingerprint of the whole document.
 *
 * Pure view: returns a ReactNode, touches no DOM (PR-1). A mark with a null rect
 * (anchor not in the minimap viewport) renders nothing. The class string is the
 * resolved decoration's `classNames` joined — IDENTICAL to what the main view
 * applies — plus a minimap marker class so the surface can style the compressed
 * form. NO decoration BODY/title text is rendered (a minimap shows COLOR, not
 * content), which is also the §9.0-safe form: a withheld source's mark carries
 * only its verdict CLASS, never any text.
 */
export function renderMinimap(
  marks: readonly MinimapMark[],
  columnWidth: number,
): ReactNode {
  const children: ReactNode[] = [];
  for (const mark of marks) {
    if (mark.rect === null) continue; // not laid out in the minimap → nothing
    children.push(
      createElement("div", {
        key: mark.decoration.key,
        // The SAME verdict/rhetorical classes the main view paints + a minimap
        // marker class. Color comes from the shared classes; no text/body.
        className: `reading-minimap__mark ${mark.decoration.classNames.join(" ")}`.trim(),
        style: {
          position: "absolute",
          top: `${mark.rect.top}px`,
          left: "0px",
          width: `${mark.rect.width}px`,
          height: `${mark.rect.height}px`,
        },
        // aria-only: the title is the SAME joined title the main view uses, but
        // it is NOT painted as visible body — a tooltip handle, not content.
        "aria-label": mark.decoration.title || undefined,
      }),
    );
  }
  return createElement(
    "div",
    {
      className: "reading-minimap",
      "aria-hidden": children.length === 0 ? true : undefined,
      style: { position: "relative", width: `${columnWidth}px` },
    },
    ...children,
  );
}
