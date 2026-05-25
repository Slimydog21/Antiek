/**
 * DRW SPR-10 — highlight anchoring across edits (the case that bites).
 *
 * Notes anchor to the TEXT of their source chunk, never to a fragile
 * `(start, end)` offset — because the document is editable and offsets rot
 * the instant a span is edited. To draw a highlight we LOCATE the anchor text
 * in the current `raw_text` by WHITESPACE-NORMALIZED content match, then map
 * back to original offsets. If the text is gone (edited away) the anchor is
 * STALE — surfaced, never silently pointed at the wrong span.
 *
 * Why normalized, not exact: chunks are paragraph-joined (so a chunk is not a
 * verbatim byte-substring of `raw_text` even before any edit), and human edits
 * reflow whitespace constantly. We normalize runs of whitespace to a single
 * space on BOTH sides, search the normalized text, and use an index map to
 * recover the original-text offsets of the matched region. This degrades
 * gracefully by construction: small edits inside an anchored region keep the
 * match (the surrounding text still locates it); an edit that removes the
 * anchor text marks it stale.
 *
 * Pure functions — the anchor-survives-edit gate (`anchor.test.ts`) exercises
 * them directly, no DOM.
 */

export interface NormalizedText {
  /** Whitespace-collapsed text. */
  norm: string;
  /** `map[i]` = the index in the ORIGINAL string of `norm[i]`. */
  map: number[];
}

/** Collapse runs of whitespace to a single space; record, for each kept
 * char, its index in the original string. Leading whitespace is dropped. */
export function normalizeWithMap(raw: string): NormalizedText {
  const out: string[] = [];
  const map: number[] = [];
  let inWs = false;
  let started = false;
  for (let i = 0; i < raw.length; i++) {
    const ch = raw[i];
    if (/\s/.test(ch)) {
      inWs = true;
      continue;
    }
    if (inWs && started) {
      out.push(" ");
      map.push(i); // the space stands in for the run ending at this char
    }
    out.push(ch);
    map.push(i);
    inWs = false;
    started = true;
  }
  return { norm: out.join(""), map };
}

export interface AnchorSpan {
  start: number; // inclusive offset into the ORIGINAL raw_text
  end: number; // exclusive
}

/** Locate `anchorText` in `raw` by normalized content match. Returns the
 * original-text span, or `null` when the anchor is no longer present
 * (stale). When the anchor appears more than once, the first match wins —
 * deterministic. */
export function findAnchor(raw: string, anchorText: string): AnchorSpan | null {
  const target = anchorText.trim().split(/\s+/).join(" ");
  if (!target) return null;
  const { norm, map } = normalizeWithMap(raw);
  const idx = norm.indexOf(target);
  if (idx === -1) return null;
  const start = map[idx];
  const lastNorm = idx + target.length - 1;
  const end = map[lastNorm] + 1; // exclusive, in original coordinates
  return { start, end };
}

export interface Highlight {
  noteId: string;
  kind: "insight" | "question";
  start: number;
  end: number;
}

export interface AnchoringResult {
  highlights: Highlight[];
  /** Notes whose anchor text is no longer in the document (edited away). */
  staleNoteIds: string[];
}

export interface AnchorableNote {
  node_id: string;
  kind: "insight" | "question";
  anchors: string[];
}

/** Compute non-overlapping highlight spans for a document's notes. A note
 * with multiple anchors uses its first locatable one; a note with no
 * locatable anchor is reported stale. Overlapping highlights are resolved by
 * keeping the earlier-starting, then-longer span (deterministic), so the
 * renderer never sees crossing ranges. */
export function computeHighlights(raw: string, notes: AnchorableNote[]): AnchoringResult {
  const highlights: Highlight[] = [];
  const staleNoteIds: string[] = [];
  for (const note of notes) {
    let placed: AnchorSpan | null = null;
    for (const a of note.anchors) {
      placed = findAnchor(raw, a);
      if (placed) break;
    }
    if (!placed) {
      staleNoteIds.push(note.node_id);
      continue;
    }
    highlights.push({ noteId: note.node_id, kind: note.kind, start: placed.start, end: placed.end });
  }
  highlights.sort((a, b) => a.start - b.start || b.end - a.end || a.noteId.localeCompare(b.noteId));
  // Drop spans that overlap an already-accepted earlier span.
  const accepted: Highlight[] = [];
  let lastEnd = -1;
  for (const h of highlights) {
    if (h.start >= lastEnd) {
      accepted.push(h);
      lastEnd = h.end;
    }
  }
  return { highlights: accepted, staleNoteIds };
}

export interface Segment {
  text: string;
  highlight: Highlight | null;
}

/** Split `raw` into render segments: plain runs interleaved with highlighted
 * runs, in document order. The renderer maps each highlighted segment to its
 * note. */
export function toSegments(raw: string, highlights: Highlight[]): Segment[] {
  const segments: Segment[] = [];
  let cursor = 0;
  for (const h of highlights) {
    if (h.start > cursor) segments.push({ text: raw.slice(cursor, h.start), highlight: null });
    segments.push({ text: raw.slice(h.start, h.end), highlight: h });
    cursor = h.end;
  }
  if (cursor < raw.length) segments.push({ text: raw.slice(cursor), highlight: null });
  return segments;
}
