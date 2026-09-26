// ─────────────────────────────────────────────────────────────────────────
// ThreadIslandAugmentation — the research-thread island, re-homed as a
// DECLARED anchored widget (island SPR-02).
//
// Modeled line-for-line on makeChaseLauncherAugmentation
// (augmentations/chase-launcher.ts): imports ONLY react (createElement) +
// ../types. It DECLARES one anchored widget per island pinned to the island's
// PASSAGE anchor ({ kind: "passage", chunkId, start, end } — types.ts:54-63),
// the PR-4 semantic anchor: chunk-relative offsets, never a pixel, so the
// island follows the passage under any transform. It sits in the `inline-end`
// lane (the passage-level affordance lane — the same lane the chase launcher
// uses, never colliding with gutter rails).
//
// The render returns the SURFACE-SUPPLIED ThreadIsland component from
// ctx.components (the PR-8 surface-owned component map): the augmentation
// never imports the card — it declares the VIEW it wants with
// substrate-derived props captured at DECLARE time (the island's anchor
// identity + thread id + the servable-or-not quote boundary), and a pass
// without the component yields nothing (graceful no-op, exactly like a null
// rect). Collapsed and expanded are render states of THAT one component,
// driven by its own local view state — this file knows nothing of them.
// ─────────────────────────────────────────────────────────────────────────

import { createElement } from "react";
import type { ReactNode } from "react";

import type {
  Anchor,
  AnchoredWidget,
  ChunkId,
  FacetRegistry,
  ReadingAugmentation,
  ReadingContext,
  Rect,
  RenderContext,
} from "../types";

/** The substrate-derived seed for one island (captured at declare time — the
 *  render reads no substrate field, PR-2). */
export interface IslandWidgetSpec {
  /** The unit-1 anchor the island hangs from (first-link-wins: one island
   *  per anchor by construction). */
  readonly anchorId: string;
  readonly documentId: string;
  /** The chunk the island's passage lives in — the PR-4 anchor base. */
  readonly chunkId: string;
  /** Chunk-relative passage offsets (half-open [start, end)), never pixels. */
  readonly start: number;
  readonly end: number;
  /** The research thread the island holds. */
  readonly investigationId: string;
  /** §9.0 at the render boundary: the passage quote ONLY when the anchor is
   *  servable; null on a metadata-only anchor (the card then shows position,
   *  never a quote). */
  readonly passageQuote: string | null;
  readonly servable: boolean;
  /** The anchor's page hint — the position the card shows on a metadata-only
   *  anchor (page + never a quote). */
  readonly pageIndexHint: number | null;
}

/** Stable widget id for one island (one anchor ↔ at most one island). */
export function islandWidgetId(spec: IslandWidgetSpec): string {
  return `thread-island:${spec.anchorId}`;
}

/**
 * Build a ThreadIsland augmentation for one island. Declares ONE anchored
 * widget pinned to the island's passage anchor in the `inline-end` lane,
 * weight 0 — a passage-level affordance, distinct from header rails; two
 * islands never share an anchor (first-link-wins), so no collision case
 * exists. The render returns the surface-supplied ThreadIsland component
 * with the captured spec; absent component ⇒ nothing.
 */
export function makeIslandAugmentation(spec: IslandWidgetSpec): ReadingAugmentation {
  const id = islandWidgetId(spec);
  const anchor: Anchor = {
    kind: "passage",
    chunkId: spec.chunkId as ChunkId,
    start: spec.start,
    end: spec.end,
  };
  return {
    id,
    contribute(_ctx: ReadingContext, registry: FacetRegistry): void {
      const widget: AnchoredWidget = {
        id,
        anchor,
        lane: "inline-end",
        weight: 0,
        render(_rect: Rect | null, ctx: RenderContext): ReactNode {
          // RENDER-time context is the RenderContext (pass + layout +
          // surface-injected `components`), NOT the declare-time
          // ReadingContext. The island spec was captured at declare time;
          // the render reads no substrate field. The SURFACE owns the
          // ThreadIsland component and everything it does; absent ⇒ nothing.
          const Island = ctx.components?.ThreadIsland;
          if (!Island) return null;
          return createElement(Island, {
            anchorId: spec.anchorId,
            documentId: spec.documentId,
            investigationId: spec.investigationId,
            servable: spec.servable,
            passageQuote: spec.passageQuote,
            pageIndexHint: spec.pageIndexHint,
          });
        },
      };
      registry.declareAnchoredWidget(widget);
    },
  };
}
