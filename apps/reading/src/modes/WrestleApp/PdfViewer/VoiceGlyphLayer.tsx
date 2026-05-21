// SPR-05 / M4 — Glyph layer for the current PDF page.
//
// Fetches anchors via getAnchorsOnPage (SPR-02 API), maps each
// anchor's PDF-space bbox into DOM coordinates relative to the
// page container, and renders one VoiceGlyph per anchor.
//
// Coordinate mapping (the load-bearing visual gate — SPR-05 rigor #3)
// ───────────────────────────────────────────────────────────────
// The PdfViewer renders the page into a canvas at a fixed
// ``RENDER_SCALE`` and renders a text layer absolutely positioned
// inside the same parent. Glyphs need to track scroll + zoom + page
// change. We achieve this by:
//   1. Positioning this layer ABSOLUTELY inside the same page-
//      container element that holds the canvas + text layer. When
//      the container scrolls or rerenders at a new scale, the
//      layer comes along for the ride — same parent stacking
//      context.
//   2. Mapping PDF user-space (bbox.x0, bbox.y0, bbox.x1, bbox.y1)
//      into DOM coordinates using the SAME render scale the
//      PdfViewer applies. The mapping is a single multiplication
//      (DOM = PDF * scale). Y-axis convention: PdfViewer.tsx uses
//      page-local top-left origin (selRect.top - layerRect.top);
//      we follow the same convention — bbox y values are top-down.
//   3. Collision detection: two anchors whose vertical centers
//      are within COLLISION_PX of each other get staggered
//      horizontally so both remain clickable.
//
// If glyphs drift through scroll / zoom transitions on the manual
// test fixture, the bug is in the mapping math above — NOT in
// VoiceGlyph itself. Don't touch the glyph file; fix the mapping.

import { useEffect, useMemo, useState } from "react";

import { getAnchorsOnPage } from "../../../lib/voiceAnchors";
import type { VoiceNoteAnchor } from "../../../lib/voiceAnchors";
import VoiceGlyph from "./VoiceGlyph";

const COLLISION_PX = 24;
const BASE_GUTTER_LEFT_PX = 16;
const STAGGER_PX = 22;

export interface VoiceGlyphLayerProps {
  documentId: string;
  /** 0-indexed page number, matching the substrate convention. */
  page: number;
  /** The render scale the PdfViewer applied to this page.
   *  Multiply PDF-space bbox coordinates by this to get DOM
   *  coordinates within the page container. */
  renderScale: number;
  /** Pixel height of the rendered page in DOM units. Used as the
   *  vertical clamp so a malformed bbox doesn't render off-page. */
  pageHeightPx: number;
  /** Pixel width of the rendered page in DOM units. The gutter
   *  sits to the right of the page; left = pageWidthPx +
   *  BASE_GUTTER_LEFT_PX. */
  pageWidthPx: number;
  /** Bump this counter to force a re-fetch after a save. */
  refreshKey?: number;
  /** Optional override (tests). Defaults to the real REST client. */
  fetchAnchors?: typeof getAnchorsOnPage;
  /** Called when the operator clicks a glyph. */
  onOpenPlayback: (anchor: VoiceNoteAnchor) => void;
  /** Optional: map anchor_id → transcript snippet for hover. */
  transcriptSnippets?: Record<string, string | null>;
}

interface PositionedGlyph {
  anchor: VoiceNoteAnchor;
  top: number;
  left: number;
}

export default function VoiceGlyphLayer({
  documentId,
  page,
  renderScale,
  pageHeightPx,
  pageWidthPx,
  refreshKey = 0,
  fetchAnchors,
  onOpenPlayback,
  transcriptSnippets,
}: VoiceGlyphLayerProps) {
  const [anchors, setAnchors] = useState<VoiceNoteAnchor[]>([]);

  useEffect(() => {
    let cancelled = false;
    const fetcher = fetchAnchors ?? getAnchorsOnPage;
    void (async () => {
      try {
        const rows = await fetcher(documentId, page);
        if (!cancelled) setAnchors(rows);
      } catch (e) {
        // Glyph layer is non-critical; log and stay empty.
        // eslint-disable-next-line no-console
        console.warn("[voice-glyph-layer] fetch failed:", e);
        if (!cancelled) setAnchors([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [documentId, page, refreshKey, fetchAnchors]);

  const positioned = useMemo<PositionedGlyph[]>(
    () => placeGlyphs(anchors, { renderScale, pageHeightPx }),
    [anchors, renderScale, pageHeightPx],
  );

  return (
    <div
      data-testid="voice-glyph-layer"
      style={{
        position: "absolute",
        top: 0,
        left: pageWidthPx,
        width: 60,
        height: pageHeightPx,
        pointerEvents: "none",
      }}
    >
      {positioned.map(({ anchor, top, left }) => (
        <div
          key={anchor.anchor_id}
          style={{ pointerEvents: "auto" }}
        >
          <VoiceGlyph
            anchor={anchor}
            top={top}
            left={left}
            transcriptSnippet={transcriptSnippets?.[anchor.anchor_id]}
            onOpenPlayback={onOpenPlayback}
          />
        </div>
      ))}
    </div>
  );
}

/**
 * Pure positioning helper — exported for unit testing of the
 * coordinate map + collision stacking. The "is the glyph in the
 * right place?" gate (rigor #3) is enforced here.
 */
export function placeGlyphs(
  anchors: readonly VoiceNoteAnchor[],
  opts: { renderScale: number; pageHeightPx: number },
): PositionedGlyph[] {
  const { renderScale, pageHeightPx } = opts;
  // Map each anchor to its vertical-center DOM coordinate.
  const raw = anchors.map((anchor) => {
    const yCenterPdf = (anchor.bbox.y0 + anchor.bbox.y1) / 2;
    const topPx = Math.min(
      Math.max(yCenterPdf * renderScale, 8),
      pageHeightPx - 8,
    );
    return { anchor, topPx };
  });
  // Sort by topPx ASC so the stacking decisions are deterministic.
  raw.sort((a, b) => a.topPx - b.topPx);
  // Walk and assign columns: if the current anchor's topPx is
  // within COLLISION_PX of the previous, bump the column.
  const result: PositionedGlyph[] = [];
  let prevTop = -Infinity;
  let column = 0;
  for (const { anchor, topPx } of raw) {
    if (topPx - prevTop < COLLISION_PX) {
      column += 1;
    } else {
      column = 0;
    }
    result.push({
      anchor,
      top: topPx,
      left: BASE_GUTTER_LEFT_PX + column * STAGGER_PX,
    });
    prevTop = topPx;
  }
  return result;
}
