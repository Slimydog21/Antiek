// SPR-07 M4 — Scroll-to-chunk on cite-jump.
//
// When the receiving WrestleApp mounts with ``?page=N&chunk=<id>`` in
// the URL we want to:
//   1. Jump to page N (existing ?page= behavior).
//   2. Scroll the chunk into view if it's rendered.
//   3. Briefly highlight the chunk with a 2-second yellow flash so
//      the operator's eye lands on the right passage.
//
// The chunk DOM hook: PdfViewer renders the text layer; chunks are
// rendered as <span data-chunk-id="..."> nodes once the per-chunk
// markup lands (Sprint 8 day 2 — out of scope here). For SPR-07 we
// ship the function shape + the highlight pulse; the data attribute
// gets added when the wrestle bridge starts emitting chunk-aware
// regions.
//
// If the chunk isn't in the DOM (because the page isn't rendered
// yet, or the chunk markup isn't on), this function is a NO-OP —
// the ``?page=`` part of the URL already handles the page jump and
// the operator finds their passage by reading.

/** Look up a chunk's DOM node by data attribute. Returns null if
 *  the chunk isn't on the page.
 *
 *  Chunk ids in the substrate are content-addressed hexadecimal +
 *  hyphens — no characters that need CSS escaping. We prefer the
 *  DOM-native ``CSS.escape`` when present (browser) and fall back to
 *  a hand-rolled escape that quotes ``"`` and ``\\`` (the only chars
 *  that can appear inside a double-quoted attribute selector and
 *  break the parse) when jsdom doesn't expose ``CSS`` (older
 *  testbed versions). */
function attrEscape(s: string): string {
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
    return CSS.escape(s);
  }
  return s.replace(/(["\\])/g, "\\$1");
}

function findChunkElement(chunkId: string): HTMLElement | null {
  return document.querySelector<HTMLElement>(
    `[data-chunk-id="${attrEscape(chunkId)}"]`,
  );
}

/** Pulse className applied for 2s on cite-jump arrival. Matches the
 *  existing onCiteJump pattern in WrestleApp/index.tsx — same
 *  amber-400 ring so the affordance reads consistent across the two
 *  cite-jump paths (NotesFeed and cross-doc). */
const CHUNK_PULSE_CLASSES = ["ring-2", "ring-amber-400", "bg-amber-50"];
const PULSE_DURATION_MS = 2000;

/** Scroll the named chunk into view and pulse-highlight it.
 *
 *  Returns ``true`` if the chunk was found and scrolled; ``false``
 *  if not in the DOM (caller may want to retry after the page
 *  renders, or fall through to the page-only jump).
 */
export function scrollToChunk(chunkId: string): boolean {
  const el = findChunkElement(chunkId);
  if (!el) return false;

  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add(...CHUNK_PULSE_CLASSES);
  window.setTimeout(() => {
    el.classList.remove(...CHUNK_PULSE_CLASSES);
  }, PULSE_DURATION_MS);

  // Note (taxonomy v2): we deliberately do NOT emit cite_jump here.
  // The cite_jump schema requires source/target document_id and a
  // direction; scrollToChunk only knows the target chunk_id. Callers
  // with full source/target context (Gutter cross_doc_link_clicked
  // already covers the gutter path; NotesFeed/CrossDocSidebar callers
  // can layer their own emit when they need the funnel signal) own
  // the emit. Adding a one-arg emit here would either fail schema
  // validation or pollute the trajectory with sentinel values.
  return true;
}

/** Wait for the chunk to appear in the DOM (with a timeout) and
 *  then scroll. Useful when the cite-jump arrives before the PDF
 *  page has finished rendering. */
export async function scrollToChunkWhenReady(
  chunkId: string,
  timeoutMs = 3000,
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  // Try immediately first.
  if (scrollToChunk(chunkId)) return true;
  return new Promise<boolean>((resolve) => {
    // Poll every 100ms — cheap and bounded.
    const tick = () => {
      if (scrollToChunk(chunkId)) {
        resolve(true);
        return;
      }
      if (Date.now() >= deadline) {
        resolve(false);
        return;
      }
      window.setTimeout(tick, 100);
    };
    window.setTimeout(tick, 100);
  });
}

/** Test helper — applies the pulse classes without scroll, returns
 *  the element so the caller can assert the pulse class is present
 *  during the duration. Not exported from the public surface. */
export function _applyPulseForTest(el: HTMLElement): void {
  el.classList.add(...CHUNK_PULSE_CLASSES);
  window.setTimeout(() => {
    el.classList.remove(...CHUNK_PULSE_CLASSES);
  }, PULSE_DURATION_MS);
}

export const _PULSE_DURATION_MS_FOR_TEST = PULSE_DURATION_MS;
