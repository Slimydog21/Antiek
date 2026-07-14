import type { ReaderChunk } from "../../api/books";

/**
 * Pagination — the book reader's locator scheme (Read SPR-03).
 *
 * A book's served body is the extracted markdown the backend produces
 * (`acquisition/books/reader.py`), with `## Page N` markers between pages.
 * This splits that body into stable **page windows**: window `i` is page
 * index `i` (0-based) = `## Page (i+1)`. That index is THE locator the
 * whole Read workflow anchors to — TOC jumps (SPR-03), ad-border slots
 * (`slot:doc:p<index>:pos`, SPR-05), spin-research seeds (SPR-08), and
 * voice notes (SPR-06) all key off it. So pagination is content-derived
 * and deterministic, never tied to scroll offset or viewport height.
 */

export interface PageWindow {
  /** 0-based page index — the canonical locator. */
  pageIndex: number;
  /** 1-based page number shown to the reader (`## Page N`). */
  pageNumber: number;
  /** The page's body (the `## Page N` marker stripped). */
  text: string;
}

const PAGE_MARKER = /^##\s+Page\s+(\d+)\s*$/i;

/**
 * Split served markdown into page windows on `## Page N` markers.
 *
 * Any leading content before the first marker (the `# Title` / `_by_`
 * front matter) is dropped from the windows — it's metadata the reader
 * renders from the book detail, not a page. A body with no markers (a
 * snippet, or non-paginated text) becomes a single window at index 0, so
 * a gated preview still renders.
 */
export function paginate(markdown: string): PageWindow[] {
  if (!markdown.trim()) return [];
  const lines = markdown.split("\n");
  const windows: PageWindow[] = [];
  let current: { pageNumber: number; buf: string[] } | null = null;

  for (const line of lines) {
    const m = line.match(PAGE_MARKER);
    if (m) {
      if (current) {
        windows.push(finish(current));
      }
      current = { pageNumber: parseInt(m[1], 10), buf: [] };
    } else if (current) {
      current.buf.push(line);
    }
  }
  if (current) windows.push(finish(current));

  if (windows.length === 0) {
    // No page markers (snippet / unpaginated) — one window at index 0.
    return [{ pageIndex: 0, pageNumber: 1, text: markdown.trim() }];
  }
  // Re-index 0-based by position (defends against non-contiguous N).
  return windows.map((w, i) => ({ ...w, pageIndex: i }));
}

/** Return the authoritative chunks owned by one reader page. The ingestion
 * page heading and long-chunk carry marker are projection metadata already
 * represented by reader chrome, so they are not rendered as prose. */
export function chunksForPage(
  chunks: ReaderChunk[],
  pageIndex: number,
): ReaderChunk[] {
  return chunks
    .filter((chunk) => chunk.page_index === pageIndex)
    .sort((a, b) => a.chunk_index - b.chunk_index)
    .map((chunk) => ({
      ...chunk,
      text: chunk.text
        .replace(/^##\s+Page\s+\d+\s*(?:\r?\n)*/i, "")
        .replace(/^<!--\s*section:\s*.*?-->\s*(?:\r?\n)*/i, "")
        .trim(),
    }));
}

/** Use chunk-region rendering only when those regions reconstruct the complete
 * visible page. Any unresolved ownership falls back to full unanchored prose,
 * preserving content rather than overstating provenance. */
export function anchoredChunksForPage(
  chunks: ReaderChunk[],
  pageIndex: number,
  pageText: string,
): ReaderChunk[] {
  const owned = chunksForPage(chunks, pageIndex);
  const normalize = (value: string) => value.replace(/\s+/g, " ").trim();
  return normalize(owned.map((chunk) => chunk.text).join("\n")) ===
    normalize(pageText)
    ? owned
    : [];
}

/** Dwell uses the same coverage gate as DOM provenance. A page that cannot be
 * fully reconstructed has no representative chunk. */
export function representativeChunkIdsByPage(
  chunks: ReaderChunk[],
  pages: PageWindow[],
): Map<number, string> {
  const byPage = new Map<number, string>();
  for (const page of pages) {
    const [representative] = anchoredChunksForPage(
      chunks,
      page.pageIndex,
      page.text,
    );
    if (representative) byPage.set(page.pageIndex, representative.chunk_id);
  }
  return byPage;
}

function finish(c: { pageNumber: number; buf: string[] }): PageWindow {
  return {
    pageIndex: c.pageNumber - 1,
    pageNumber: c.pageNumber,
    text: c.buf.join("\n").trim(),
  };
}

/** Map a TOC entry's page_index to the window index to jump to, clamped
 * into range. Returns null when the TOC entry has no resolvable page. */
export function windowForTocPage(
  pages: PageWindow[],
  tocPageIndex: number | null,
): number | null {
  if (tocPageIndex === null || pages.length === 0) return null;
  return Math.max(0, Math.min(tocPageIndex, pages.length - 1));
}
