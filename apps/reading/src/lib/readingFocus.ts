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

const PAGE_TEXT_CAP = 4000;

// One entry per reader mount, in publish order. The Thought Partner reads the
// most recently published entry, so the reader last touched wins, and closing
// one reader window leaves another open reader's focus in place instead of
// wiping the only slot.
const DEFAULT_OWNER = Symbol("readingFocus.default");
const mounts = new Map<unknown, ReadingFocus>();
let current: ReadingFocus | null = null;

export function getReadingFocus(): ReadingFocus | null {
  return current;
}

/**
 * Publish `owner`'s focus (a reader mount passes a stable token of its own).
 * `null` with no owner clears every mount; with an owner, only that mount.
 */
export function setReadingFocus(
  focus: ReadingFocus | null,
  owner: unknown = DEFAULT_OWNER,
): void {
  if (focus === null) {
    if (owner === DEFAULT_OWNER) mounts.clear();
    else mounts.delete(owner);
  } else {
    const servable = focus.servable === true;
    mounts.delete(owner);
    mounts.set(owner, {
      documentId: focus.documentId,
      pageIndex: focus.pageIndex,
      title: focus.title,
      servable,
      // Dual structure: never retain body for gated books.
      pageText: servable && focus.pageText ? focus.pageText : null,
    });
  }
  current = null;
  for (const latest of mounts.values()) current = latest;
  if (typeof window !== "undefined") {
    window.dispatchEvent(
      new CustomEvent(READING_FOCUS_EVENT, { detail: current }),
    );
  }
}

export function clearReadingFocus(owner: unknown = DEFAULT_OWNER): void {
  setReadingFocus(null, owner);
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
  const text =
    raw.length > PAGE_TEXT_CAP
      ? `${raw.slice(0, PAGE_TEXT_CAP)}\n…[truncated]`
      : raw;
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
