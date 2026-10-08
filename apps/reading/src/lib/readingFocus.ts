/**
 * Reading focus bus — SERVABLE book/page mount for Thought Partner.
 *
 * Cite: issue 3135 (TP hybrid / gated→DuckDB only); ThoughtPartnerRequest.system_context;
 * BookReader (modes/Reading) ownerReadable / servable_full_text; dual structure.
 *
 * The reader publishes the open book + page. Thought Partner (AISidecar,
 * Surface E, FloatMenu Dialogue) merges this into system_context so the model
 * sees the current page WITHOUT manual @-compose. Gated / non-servable books
 * never publish page body — only an honest withheld stub.
 */

export const READING_FOCUS_EVENT = "antiek:reading:focus";

export interface ReadingFocus {
  documentId: string;
  pageIndex: number;
  title: string | null;
  /** Page body — ONLY set when servable (ownerReadable). */
  pageText: string | null;
  /** Rights-clean flag: false ⇒ body must not enter TP context. */
  servable: boolean;
}

export const PAGE_TEXT_CAP = 4000;

let current: ReadingFocus | null = null;

export function getReadingFocus(): ReadingFocus | null {
  return current;
}

export function setReadingFocus(focus: ReadingFocus | null): void {
  if (focus === null) {
    current = null;
  } else {
    const servable = focus.servable === true;
    current = {
      documentId: focus.documentId,
      pageIndex: focus.pageIndex,
      title: focus.title,
      servable,
      // Dual structure: never retain body for gated books.
      pageText: servable && focus.pageText ? focus.pageText : null,
    };
  }
  if (typeof window !== "undefined") {
    window.dispatchEvent(
      new CustomEvent(READING_FOCUS_EVENT, { detail: current }),
    );
  }
}

export function clearReadingFocus(): void {
  setReadingFocus(null);
}

/**
 * EXACTLY the page bytes the model's mount carries (trimmed, capped at
 * PAGE_TEXT_CAP, no marker); null when nothing servable is loaded. Anything
 * that verifies a quote "against the page the model sees" (the agent pane's
 * anchorContext.ts) must verify against this, never against `pageText`.
 */
export function mountedPageText(focus: ReadingFocus | null = current): string | null {
  if (!focus || !focus.servable) return null;
  const raw = (focus.pageText || "").trim();
  if (!raw) return null;
  return raw.length > PAGE_TEXT_CAP ? raw.slice(0, PAGE_TEXT_CAP) : raw;
}

/**
 * Format the current reading focus for ThoughtPartnerRequest.system_context.
 * Returns null when nothing is open. Gated books get an honest withheld stub
 * (no invented body).
 */
export function formatReadingFocusSystemContext(
  focus: ReadingFocus | null = current,
): string | null {
  if (!focus || !focus.documentId) return null;
  const title = focus.title?.trim() || "(untitled)";
  const pageDisplay = focus.pageIndex + 1;
  if (!focus.servable) {
    return [
      "# CURRENT READING (gated — page body withheld from thought-partner)",
      `document_id: ${focus.documentId}`,
      `title: ${title}`,
      `page_index: ${focus.pageIndex} (display page ${pageDisplay})`,
      "Do not invent or recall withheld page text. Ask the operator to open a",
      "SERVABLE copy, or discuss from their prompt alone.",
    ].join("\n");
  }
  const raw = (focus.pageText || "").trim();
  if (!raw) {
    return [
      "# CURRENT READING (SERVABLE — page not loaded yet)",
      `document_id: ${focus.documentId}`,
      `title: ${title}`,
      `page_index: ${focus.pageIndex} (display page ${pageDisplay})`,
    ].join("\n");
  }
  const mounted = mountedPageText(focus)!;
  const text = raw.length > PAGE_TEXT_CAP ? `${mounted}\n…[truncated]` : mounted;
  return [
    "# CURRENT READING (SERVABLE — rights-clean page mount)",
    `document_id: ${focus.documentId}`,
    `title: ${title}`,
    `page_index: ${focus.pageIndex} (display page ${pageDisplay})`,
    "",
    "Page text:",
    text,
  ].join("\n");
}
