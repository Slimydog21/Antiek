// ─────────────────────────────────────────────────────────────────────────
// HighlightAnchorAugmentation — a persisted highlight, re-homed as a
// DECLARED anchored decoration (anchor-first SPR-02).
//
// Modeled on makeChaseLauncherAugmentation (augmentations/chase-launcher.ts):
// imports ONLY ../types (a Decoration carries no render callback — lighter
// than the chase widget's React surface). It DECLARES a
// Decoration pinned to a PASSAGE anchor ({ kind: "passage", chunkId, start,
// end } — types.ts:54-63), the PR-4 semantic anchor: chunk-relative offsets,
// never a pixel, so the mark follows the passage under any transform. The
// surface ENACTS it (the book reader paints the combined decoration inline,
// as part of the text flow — the strongest possible repagination story, and
// the reason no layout-map pixel pass is needed for a text-level treatment).
//
// The decoration class comes from a CLOSED vocabulary ("anchor-active" |
// "anchor-drifted") — the surface maps it to the design-token treatment
// (sun wash + underline; dashed + reduced opacity when drifted). The title
// is the honest affordance text (the drifted "moved" note). Everything is
// captured at DECLARE time from the persisted anchor row (PR-2: the render
// reads no substrate field).
// ─────────────────────────────────────────────────────────────────────────

import type {
  Anchor,
  ChunkId,
  Decoration,
  FacetRegistry,
  ReadingAugmentation,
  ReadingContext,
} from "../types";

/** The closed decoration vocabulary the surface understands. */
export type AnchorTreatment = "active" | "drifted";

export interface HighlightAnchorSpec {
  /** The persisted anchor id — the decoration's stable identity. */
  readonly anchorId: string;
  readonly chunkId: string;
  /** Chunk-relative passage offsets (half-open [start, end)), never pixels. */
  readonly start: number;
  readonly end: number;
  readonly treatment: AnchorTreatment;
  /** The honest affordance text (the drifted "moved" note). */
  readonly title: string;
}

/** The decoration class vocabulary (the surface maps these to tokens). */
export const ANCHOR_DECORATION_CLASSES: Record<AnchorTreatment, string> = {
  active: "anchor-active",
  drifted: "anchor-drifted",
};

/**
 * Build a HighlightAnchor augmentation for one persisted anchor. Declares
 * ONE decoration pinned to the anchor's passage, id incorporating the chunk
 * + offsets so two anchors on different passages are distinct decorations
 * (stable across renders), while one anchor keeps one id.
 */
export function makeHighlightAnchorAugmentation(
  spec: HighlightAnchorSpec,
): ReadingAugmentation {
  const id = `highlight-anchor:${spec.chunkId}:${spec.start}:${spec.end}`;
  const anchor: Anchor = {
    kind: "passage",
    chunkId: spec.chunkId as ChunkId,
    start: spec.start,
    end: spec.end,
  };
  const className = ANCHOR_DECORATION_CLASSES[spec.treatment];
  return {
    id,
    contribute(_ctx: ReadingContext, registry: FacetRegistry): void {
      const decoration: Decoration = {
        anchor,
        className,
        title: spec.title,
      };
      registry.declareDecoration(decoration);
    },
  };
}
