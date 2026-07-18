import { useCallback, useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.mjs?url";

import type { DocumentRegionSelectedPayload } from "../generated/types";
import { postTypedEvent } from "../lib/api";
import { openNotebook } from "../workspace/actions";
import { usePanelSizeStable } from "../workspace/PanelLayoutPanel";
import LemonButton from "./lemon/LemonButton";
import { toast } from "./lemon/LemonToast";
import { emitWernerExperience } from "../werner/reactionBus";

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
  const [renderState, setRenderState] = useState<PageRenderState | null>(null);
  const [postError, setPostError] = useState<string | null>(null);

  // S6 acceptance: when the PDF is rendered inside a floating panel,
  // resizing the panel doesn't crash pdf.js. We use the workspace's
  // debounced size hook (`usePanelSizeStable`) — it fires only after
  // the resize gesture has settled for 120 ms, so we don't re-render
  // on every animation frame of a drag. Mid-gesture the previous
  // canvas remains mounted (CSS-scaled by the parent container);
  // sharp-again after the gesture ends.
  //
  // The single-page renderer in this file keeps a fixed rasterization
  // scale (1.4) and lets the parent container CSS-scale via its
  // overflow + flexbox; the stable-size subscription is here for
  // future multi-page resize-adaptive rendering. It's a real
  // consumer of the hook (not orphan code) — when adaptive rendering
  // lands, the size reads the new container width + re-renders.
  const [outerRef, stableSize] = usePanelSizeStable<HTMLDivElement>(120);
  // Bind the size to a ref the consumer can observe (currently no-op
  // beyond the subscription itself, which exercises the hook + keeps
  // pdf.worker idle during in-progress resize gestures).
  void stableSize;

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
  }, [renderState, investigationId, documentId, onRegionSelected]);

  return (
    <div ref={outerRef as React.RefObject<HTMLDivElement>} className="flex flex-col items-stretch h-full">
      <div className="px-4 py-2 text-xs font-mono bg-ice-3 dark:bg-charcoal-1 border-b border-rule dark:border-charcoal-1 text-ink-soft dark:text-starlight flex items-center justify-between gap-3">
        <span>document_id: <span className="text-ink dark:text-bright">{documentId}</span></span>
        <span className="flex items-center gap-3">
          <span>page: {renderState?.pageNum ?? "—"}</span>
          <LemonButton
            size="sm"
            variant="secondary"
            onClick={() => {
              emitWernerExperience("note_saved");
              // S7 acceptance — "Add to notebook" from PdfViewer.
              // Opens the notebook editor; the operator inserts a
              // region-embed block via the slash menu referencing the
              // current page.
              openNotebook({
                kind: "NotebookEditor",
                mode: "floating",
                notebookId: `doc-${documentId}`,
                title: "Add to notebook",
              });
              toast.ok(
                "Notebook open — use the slash menu to insert a region-embed block for this page.",
              );
            }}
          >
            Add to notebook
          </LemonButton>
        </span>
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
        <div className="relative shadow-md ring-1 ring-rule dark:ring-charcoal-1 bg-ice-0 dark:bg-charcoal-2">
          <canvas ref={canvasRef} />
          <div ref={textLayerRef} className="pdf-text-layer" />
        </div>
      </div>
    </div>
  );
}
