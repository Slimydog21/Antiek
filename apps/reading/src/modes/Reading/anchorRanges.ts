/**
 * anchorRanges.ts — pure mapping from persisted anchors to page-painted
 * highlight ranges (anchor-first SPR-02).
 *
 * The geometry is CONTENT-derived, never pixel-derived: the anchor-map
 * gives each chunk's [body_start, body_end) in the normalized served body;
 * an anchor's passage [start, end) is chunk-relative, so its body range is
 * [chunk.body_start + start, chunk.body_start + end). A page window knows
 * its own bodyStart (paginate.ts), so the range maps to page-relative
 * offsets by intersection. Painting is then INLINE (part of the text flow):
 * the mark repaginates for free — no layout-map pixel pass could do better
 * for a text-level treatment.
 *
 * `normalizeNodeText` mirrors the cross-runtime `unicode-nfc-v1` contract
 * (substrate/feedback/domain.py:18-20) so client offsets and the server's
 * anchor-map offsets live in ONE scalar space.
 */
import type { AnchorMapChunk, BookAnchor } from "../../lib/api";
import type { PageWindow } from "./paginate";

/** unicode-nfc-v1: CRLF and CR collapse to LF, then NFC — the exact
 *  normalization the anchor schema validates against server-side. */
export function normalizeNodeText(value: string): string {
  return value.replace(/\r\n/g, "\n").replace(/\r/g, "\n").normalize("NFC");
}

export interface PaintedRange {
  anchorId: string;
  /** Page-relative [start, end) into the window's text. */
  start: number;
  end: number;
  treatment: "active" | "drifted";
  title: string;
}

/** The closed decoration vocabulary the highlight augmentation declares and
 *  the surface maps to classes — one place, no CSS free-form (PR-1). */
export function treatmentForStatus(status: BookAnchor["status"]): "active" | "drifted" | "orphaned" {
  return status;
}

export const ANCHOR_TREATMENT_TITLES: Record<"active" | "drifted", string> = {
  active: "Anchored highlight",
  drifted: "Moved — re-anchored here after the text changed",
};

/** Map one anchor to its body range via the anchor-map, or null when its
 *  chunk isn't in the manifest (an orphaned anchor's chunk may be gone —
 *  nothing to paint, which is exactly the orphaned visual contract). */
export function anchorBodyRange(
  anchor: BookAnchor,
  chunksById: Map<string, AnchorMapChunk>,
): { start: number; end: number } | null {
  const chunk = chunksById.get(anchor.anchor.node_id);
  if (!chunk) return null;
  const start = chunk.body_start + anchor.anchor.start_scalar;
  const end = chunk.body_start + anchor.anchor.end_scalar;
  return end > start ? { start, end } : null;
}

/** The painted ranges for one page window: every non-orphaned anchor whose
 *  body range intersects the window, clipped to page-relative offsets. */
export function rangesForPage(
  page: PageWindow,
  anchors: readonly BookAnchor[],
  chunksById: Map<string, AnchorMapChunk>,
): PaintedRange[] {
  const pageStart = page.bodyStart;
  const pageEnd = page.bodyStart + page.text.length;
  const out: PaintedRange[] = [];
  for (const anchor of anchors) {
    const treatment = treatmentForStatus(anchor.status);
    if (treatment === "orphaned") continue;
    const body = anchorBodyRange(anchor, chunksById);
    if (!body) continue;
    const start = Math.max(body.start, pageStart);
    const end = Math.min(body.end, pageEnd);
    if (end <= start) continue;
    out.push({
      anchorId: anchor.anchor_id,
      start: start - pageStart,
      end: end - pageStart,
      treatment,
      title: ANCHOR_TREATMENT_TITLES[treatment],
    });
  }
  out.sort((a, b) => a.start - b.start || a.end - b.end || a.anchorId.localeCompare(b.anchorId));
  return out;
}

/** Orphaned anchors for the reader's honest list (never painted in the
 *  body): page hint + the "text no longer found" label, oldest first. */
export function orphanedForList(anchors: readonly BookAnchor[]): BookAnchor[] {
  return anchors
    .filter((a) => a.status === "orphaned")
    .sort((a, b) => a.created_at.localeCompare(b.created_at) || a.anchor_id.localeCompare(b.anchor_id));
}

/** The chunk a body offset falls in (the HONEST GAP closure — the reader
 *  finally resolves a real chunk id from the served body, via the
 *  anchor-map, instead of recording null). Null when the offset lands
 *  between chunks or the manifest is empty. */
export function chunkIdAtOffset(
  offset: number,
  chunks: readonly AnchorMapChunk[],
): string | null {
  for (const chunk of chunks) {
    if (offset >= chunk.body_start && offset < chunk.body_end) return chunk.chunk_id;
  }
  return null;
}
