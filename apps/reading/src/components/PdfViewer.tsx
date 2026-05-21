import { useCallback, useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.mjs?url";

import type { DocumentRegionSelectedPayload } from "../generated/types";
import { postTypedEvent } from "../lib/api";
import Gutter, {
  type ActiveHighlight,
} from "../modes/WrestleApp/PdfViewer/Gutter";

// One-time worker registration. pdf.js requires this before any
// getDocument call.
pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

interface PdfViewerProps {
  pdfBytes: Uint8Array;
  investigationId: string;
  documentId: string;
  /**
   * Called after a region selection POST succeeds. Lets the parent
   * surface a transient "selected" affordance without re-fetching the
   * trajectory.
   */
  onRegionSelected?: (regionId: string) => void;
  /**
   * 1-based page index to jump to on load. Used by Mode A's chunk-
   * citation modal which deep-links into /wrestle/<doc>?page=N.
   *
   * Sprint 11 day 2 accepts the prop but the underlying viewer still
   * renders page 1 only (single-page legacy implementation). Multi-
   * page navigation lands in Sprint 11 day 8 polish.
   */
  initialPage?: number;
}

// Scale chosen for legibility on retina; lower = denser, higher = bigger.
const RENDER_SCALE = 1.4;

// Maximum characters of selected text we put on the wire. The substrate
// stores ``text_excerpt`` for UI rendering; the canonical content is on
// disk (the loaded document). Truncating defends against an accidental
// "select-all" producing a 200KB payload.
const MAX_EXCERPT_CHARS = 1000;

interface PageRenderState {
  pageNum: number;
  pageText: string;        // flat text used to compute char offsets
}

/**
 * Render the FIRST page of the PDF and capture selection events.
 *
 * Scope note: Sprint 2 day-1 renders one page and uses ``window.getSelection().toString()``
 * as the text. Multi-page render + accurate per-page char_offset
 * mapping via the text-layer DOM lands in Sprint 2 day-3 alongside the
 * chat panel iteration.
 */
export default function PdfViewer({
  pdfBytes,
  investigationId,
  documentId,
  onRegionSelected,
}: PdfViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textLayerRef = useRef<HTMLDivElement>(null);
  // SPR-07 M2: the relative-positioned container holds the canvas, the
  // text layer, AND the gutter overlay. We use this ref to compute
  // selection-rect coordinates in container-local space (the gutter
  // sits absolutely positioned inside this container).
  const pageContainerRef = useRef<HTMLDivElement>(null);
  const [renderState, setRenderState] = useState<PageRenderState | null>(null);
  const [postError, setPostError] = useState<string | null>(null);

  // SPR-07 M2: active highlights — drives the gutter pill stack. We
  // keep at most ONE active highlight at a time today (one selection
  // per finalize); the Gutter is built to accept many, in case a
  // future iteration tracks multiple selections (one per saved note).
  const [activeHighlights, setActiveHighlights] = useState<ActiveHighlight[]>(
    [],
  );

  // Render the page once when pdfBytes changes.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // pdfjs.getDocument consumes a fresh buffer; never share with
        // upstream React state (it gets transferred).
        const buf = pdfBytes.slice().buffer;
        const pdf = await pdfjs.getDocument({ data: buf }).promise;
        const page = await pdf.getPage(1);
        const viewport = page.getViewport({ scale: RENDER_SCALE });
        const canvas = canvasRef.current;
        const textLayer = textLayerRef.current;
        if (!canvas || !textLayer || cancelled) return;

        canvas.width = viewport.width;
        canvas.height = viewport.height;
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;
        textLayer.style.width = `${viewport.width}px`;
        textLayer.style.height = `${viewport.height}px`;

        const ctx = canvas.getContext("2d");
        if (!ctx) return;
        await page.render({ canvasContext: ctx, viewport }).promise;

        // Render the text layer so the user can select text.
        const textContent = await page.getTextContent();
        textLayer.replaceChildren();
        // pdf.js exposes ``TextLayer`` (v4+) which builds the absolutely-
        // positioned spans for us. It's renderer-internal but stable.
        const TextLayer = (pdfjs as unknown as {
          TextLayer: new (args: {
            textContentSource: unknown;
            container: HTMLElement;
            viewport: unknown;
          }) => { render: () => Promise<void> };
        }).TextLayer;
        const tl = new TextLayer({
          textContentSource: textContent,
          container: textLayer,
          viewport,
        });
        await tl.render();

        // Build a flat string of page text for char-offset reporting.
        // Concatenate items in their natural order.
        const pageText = textContent.items
          .map((item) => ("str" in item ? (item as { str: string }).str : ""))
          .join("");

        if (!cancelled) {
          setRenderState({ pageNum: 1, pageText });
        }
      } catch (err) {
        console.error("PDF render failed:", err);
        if (!cancelled) {
          setPostError(`PDF render failed: ${err instanceof Error ? err.message : String(err)}`);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pdfBytes]);

  const onMouseUp = useCallback(async () => {
    if (!renderState) return;
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed) return;
    const text = sel.toString();
    if (!text.trim()) return;
    // Selection must be inside the text layer to count.
    const layer = textLayerRef.current;
    if (!layer || !layer.contains(sel.anchorNode)) return;

    const range = sel.getRangeAt(0);
    const layerRect = layer.getBoundingClientRect();
    const selRect = range.getBoundingClientRect();
    // bbox in page-local coordinates (top-left origin = page top-left).
    const bbox: [number, number, number, number] = [
      selRect.left - layerRect.left,
      selRect.top - layerRect.top,
      selRect.right - layerRect.left,
      selRect.bottom - layerRect.top,
    ];

    // char_start / char_end via indexOf into the flat page text. This
    // is approximate when the selection text appears multiple times on
    // the page (we pick the first match). Sprint 3 will replace this
    // with a proper text-layer DOM walk that yields the exact node-
    // sequence offset.
    let charStart = renderState.pageText.indexOf(text);
    if (charStart < 0) charStart = 0;
    const charEnd = charStart + text.length;

    const regionId =
      "r-" +
      crypto.randomUUID().replace(/-/g, "").slice(0, 12) +
      "-" +
      Date.now().toString(36);

    const excerpt =
      text.length > MAX_EXCERPT_CHARS
        ? text.slice(0, MAX_EXCERPT_CHARS) + "…"
        : text;

    const payload: DocumentRegionSelectedPayload = {
      action_type: "document.region_selected",
      region_id: regionId,
      page: renderState.pageNum,
      char_start: charStart,
      char_end: charEnd,
      bbox,
      text_excerpt: excerpt,
    };

    try {
      await postTypedEvent({
        investigation_id: investigationId,
        document_id: documentId,
        payload,
        role: "user_agent",
      });
      setPostError(null);
      onRegionSelected?.(regionId);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setPostError(msg);
    }

    // SPR-07 M2: register the highlight with the Gutter overlay. The
    // topPx is the selection's vertical position relative to the
    // page container (which is the gutter's positioning parent). We
    // replace the entire active set rather than append — selections
    // are typically one-at-a-time and accumulating stale highlights
    // creates visual clutter. The Gutter's dismiss-on-removal logic
    // fires for the previously-active highlight via the rerender,
    // so the funnel event lands honestly.
    const container = pageContainerRef.current;
    if (container) {
      const containerRect = container.getBoundingClientRect();
      const topPx = selRect.top - containerRect.top;
      const newHighlight: ActiveHighlight = {
        highlightId: regionId,
        documentId,
        page: renderState.pageNum,
        bbox,
        topPx,
        selectedText: text,
      };
      setActiveHighlights([newHighlight]);
    }
  }, [renderState, investigationId, documentId, onRegionSelected]);

  // SPR-07 M2 acceptance: pills disappear on highlight clear.
  // Document-level selectionchange triggers when the operator
  // dismisses their selection (click elsewhere, escape, etc.).
  useEffect(() => {
    const onSelectionChange = () => {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed) {
        // Defer the clear by a tick — the onMouseUp handler often
        // fires AFTER a selection-collapse on a fresh click, so
        // synchronous clearing would race the new highlight.
        // The 50ms delay gives the new selection time to land.
        window.setTimeout(() => {
          const s = window.getSelection();
          if (!s || s.isCollapsed) {
            setActiveHighlights([]);
          }
        }, 50);
      }
    };
    document.addEventListener("selectionchange", onSelectionChange);
    return () =>
      document.removeEventListener("selectionchange", onSelectionChange);
  }, []);

  return (
    <div className="flex flex-col items-stretch h-full">
      <div className="px-4 py-2 text-xs font-mono bg-stone-100 border-b border-stone-200 text-stone-600 flex items-center justify-between">
        <span>document_id: <span className="text-stone-900">{documentId}</span></span>
        <span>page: {renderState?.pageNum ?? "—"}</span>
      </div>
      {postError && (
        <div className="px-4 py-2 text-xs font-mono bg-red-50 text-red-800 border-b border-red-200">
          {postError}
        </div>
      )}
      <div
        className="flex-1 overflow-auto p-6 flex justify-center"
        onMouseUp={onMouseUp}
      >
        <div
          ref={pageContainerRef}
          className="relative shadow-md ring-1 ring-stone-200 bg-white"
        >
          <canvas ref={canvasRef} />
          <div ref={textLayerRef} className="pdf-text-layer" />
          {/* SPR-07 M2: gutter overlay — pill stacks for any active
              highlight. Positioned absolutely against this container,
              so the topPx coordinates from getBoundingClientRect map
              directly. */}
          <Gutter highlights={activeHighlights} />
        </div>
      </div>
    </div>
  );
}
