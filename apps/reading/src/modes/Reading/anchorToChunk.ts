/**
 * Chunk-span anchoring for the BookReader (Read-side enhancement; the
 * minor follow-up Write SPR-07 needs to land a trace on the EXACT cited
 * span rather than just the document).
 *
 * The reader paginates the served markdown into ``PageWindow``s; a trace
 * carries the source ``chunk_id``. ``getChunk`` resolves the chunk to its
 * text; this pure function maps that text to the page that contains it, so
 * the reader can open at the cited span. It is deterministic and unit-
 * testable without a browser.
 *
 * Matching is whitespace-normalized and uses a distinctive prefix probe
 * (so minor served-vs-stored formatting differences don't defeat it),
 * with a first-sentence fallback for the case where the prefix straddles a
 * page boundary. Returns -1 when the chunk isn't located (the reader then
 * just opens at the saved position — never throws).
 */

import type { PageWindow } from "./paginate";

export function normalizeForMatch(s: string): string {
  return s.replace(/\s+/g, " ").trim().toLowerCase();
}

/** A distinctive prefix of the chunk used to locate it on a page. */
export function chunkProbe(chunkText: string, len = 80): string {
  return normalizeForMatch(chunkText).slice(0, len);
}

/**
 * The 0-based page index containing ``chunkText``, or -1 if not found.
 * Tries an 80-char prefix first, then the chunk's first sentence (handles
 * a prefix that straddles a page boundary).
 */
export function findPageForChunkText(pages: PageWindow[], chunkText: string): number {
  const probe = chunkProbe(chunkText);
  if (!probe) return -1;

  for (const p of pages) {
    if (normalizeForMatch(p.text).includes(probe)) return p.pageIndex;
  }

  // Fallback: a shorter first-sentence probe.
  const firstSentence = normalizeForMatch(chunkText.split(/(?<=[.!?])\s/)[0] ?? "").slice(0, 60);
  if (firstSentence && firstSentence !== probe) {
    for (const p of pages) {
      if (normalizeForMatch(p.text).includes(firstSentence)) return p.pageIndex;
    }
  }
  return -1;
}
