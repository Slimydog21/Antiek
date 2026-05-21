import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import type { DocumentLoadedPayload } from "../../generated/types";
import CrossDocSidebar from "../../components/CrossDocSidebar";
import NotesFeed from "../../components/NotesFeed";
import NotesPanel from "../../components/NotesPanel";
import PdfViewer from "../../components/PdfViewer";
import { useEventStream } from "../../hooks/useEventStream";
import { postTypedEvent } from "../../lib/api";
import { sha256Hex } from "../../lib/hash";
import HeaderBar from "../shared/HeaderBar";

import { scrollToChunkWhenReady } from "./PdfViewer/scrollToChunk";

/**
 * Mode B — Document Wrestler.
 *
 * Three columns: PDF (left), live trajectory chat (middle), notes
 * (right). One investigation per browser tab; document_id is
 * content-hash-derived so the same file uploaded twice reuses the
 * id.
 *
 * Deep-link query params (Sprint 11 day 8 + SPR-07 M4):
 *   ?page=N         — page to jump to on load
 *   ?chunk=<id>     — chunk to scroll to + pulse-highlight on arrival
 *
 * Both are optional. ?chunk= is the new cross-doc cite-jump target
 * (SPR-07): clicking "Open" on a gutter pill routes to
 * /wrestle/<target_doc>?page=N&chunk=<id>. The receiving instance
 * jumps to the page and calls ``scrollToChunkWhenReady`` once the
 * PDF text layer has rendered.
 *
 * CrossDocSidebar layout change (SPR-07 M5):
 * CrossDocSidebar is legacy — the primary cross-doc surface is gutter
 * pills (PdfViewer/Gutter.tsx). The component is still mounted but
 * gated behind Cmd+J for power users who want the wider question→
 * answer panel. The data path (cross_doc.question_answered events)
 * remains live — the sidebar simply isn't always-on anymore.
 */
export default function WrestleApp() {
  const params = useParams<{ documentId?: string }>();
  const initialDocumentId = params.documentId ?? null;
  // Read ?page= AND ?chunk= from the query string. Sprint 11 day 8
  // shipped page; SPR-07 M4 added chunk for the gutter cite-jump
  // target. Both fall back to null when absent or malformed.
  const { initialPage, initialChunk } = (() => {
    const usp = new URLSearchParams(window.location.search);
    const rawPage = usp.get("page");
    const page = rawPage ? parseInt(rawPage, 10) : NaN;
    const chunk = usp.get("chunk");
    return {
      initialPage: Number.isFinite(page) && page > 0 ? page : null,
      // Chunk ids in the substrate start with "chunk-" or similar
      // content-addressed prefixes — we accept whatever the URL
      // carries verbatim. The scrollToChunk lookup degrades to
      // no-op if the id isn't in the DOM.
      initialChunk: chunk && chunk.length > 0 ? chunk : null,
    };
  })();

  const [investigationId] = useState<string>(() => {
    const stored = window.sessionStorage.getItem("antiek.investigation_id");
    if (stored) return stored;
    const fresh = "inv-" + crypto.randomUUID().replace(/-/g, "").slice(0, 12);
    window.sessionStorage.setItem("antiek.investigation_id", fresh);
    return fresh;
  });

  const [pdfBytes, setPdfBytes] = useState<Uint8Array | null>(null);
  const [documentId, setDocumentId] = useState<string | null>(initialDocumentId);
  const [loadError, setLoadError] = useState<string | null>(null);

  // SPR-07 M5: Cmd+J toggles the legacy CrossDocSidebar slide-out.
  // Default hidden — gutter pills are the primary surface.
  const [legacySidebarOpen, setLegacySidebarOpen] = useState(false);

  const { events, status, reconnects } = useEventStream(investigationId);

  const onFileSelected = useCallback(
    async (file: File) => {
      setLoadError(null);
      try {
        const buf = new Uint8Array(await file.arrayBuffer());
        const hash = await sha256Hex(buf);
        const docId = "doc-" + hash.slice(0, 16);

        const payload: DocumentLoadedPayload = {
          action_type: "document.loaded",
          media_type: "pdf",
          content_hash: "sha256:" + hash,
          size_bytes: file.size,
          title: file.name,
          page_count: null,
          source_uri: null,
        };

        await postTypedEvent({
          investigation_id: investigationId,
          document_id: docId,
          payload,
          role: "user_agent",
        });

        setPdfBytes(buf);
        setDocumentId(docId);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setLoadError(msg);
      }
    },
    [investigationId],
  );

  useEffect(() => {
    console.info(
      "[antiek/wrestle] investigation_id:", investigationId,
      "documentId:", documentId,
      "initialPage:", initialPage,
      "initialChunk:", initialChunk,
    );
  }, [investigationId, documentId, initialPage, initialChunk]);

  // SPR-07 M4: when ?chunk= is present and the PDF has loaded, ask
  // the scroll helper to wait for the chunk DOM node and pulse it.
  // The helper polls with a 3s timeout so cite-jump arrivals don't
  // race the first-page render.
  useEffect(() => {
    if (!initialChunk || !pdfBytes) return;
    let cancelled = false;
    void scrollToChunkWhenReady(initialChunk).then((found) => {
      if (cancelled) return;
      if (!found) {
        console.info(
          "[antiek/wrestle] chunk not found in DOM after timeout:",
          initialChunk,
        );
      }
    });
    return () => {
      cancelled = true;
    };
  }, [initialChunk, pdfBytes]);

  // SPR-07 M5: Cmd+Shift+J keybinding for the legacy CrossDocSidebar
  // slide-out. The sprint spec asked for Cmd+J, but that combo is
  // already bound by AISidecar (apps/reading/src/components/
  // AISidecar.tsx:104) which is a different reading-surface rail.
  // Defining two listeners for the same combo would toggle both
  // panels on every press. Cmd+Shift+J is the operator-discoverable
  // adjacent binding — same letter, same finger, conflict-free.
  // The header hint string carries the binding so power users see
  // it in the UI.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (
        (e.metaKey || e.ctrlKey) &&
        e.shiftKey &&
        (e.key === "j" || e.key === "J")
      ) {
        e.preventDefault();
        setLegacySidebarOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Cite-jump: a NotesFeed chip click resolves to a chat-feed row by
  // DOM id (rendered by NotesPanel as `event-row-<event_id>`). Scroll
  // the target into view and pulse a ring class.
  const onCiteJump = useCallback((eventId: string) => {
    const el = document.getElementById(`event-row-${eventId}`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("ring-2", "ring-amber-400", "shadow");
    window.setTimeout(() => {
      el.classList.remove("ring-2", "ring-amber-400", "shadow");
    }, 1500);
  }, []);

  return (
    <div className="flex flex-col h-screen">
      <HeaderBar>
        <span className="text-xs font-mono text-stone-500">
          investigation: <span className="text-stone-900">{investigationId}</span>
        </span>
        <label className="cursor-pointer text-xs px-3 py-1.5 bg-stone-900 text-white rounded-md hover:bg-stone-700 transition-colors">
          load PDF
          <input
            type="file"
            accept="application/pdf"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onFileSelected(f);
            }}
          />
        </label>
        {/* Cmd+J hint — small, monospace, easy to ignore once you've
            seen it. The discoverability cost is the price of moving
            CrossDocSidebar out of the default layout. */}
        <span className="text-[10px] font-mono text-stone-400">
          press ⌘⇧J for cross-doc panel
        </span>
        {loadError && (
          <div className="text-xs font-mono text-red-700">{loadError}</div>
        )}
      </HeaderBar>
      {/*
        SPR-07 M5 layout: 2-column (PDF + NotesPanel/NotesFeed).
        CrossDocSidebar is no longer mounted in the default grid; it
        slides in from the right when legacySidebarOpen is true.
      */}
      <div className="grid grid-cols-1 md:grid-cols-[2fr_1fr] gap-0 flex-1 min-h-0 relative">
        <div className="flex flex-col h-full border-r border-stone-200 bg-stone-50 min-h-0">
          <div className="flex-1 overflow-hidden">
            {pdfBytes && documentId ? (
              <PdfViewer
                pdfBytes={pdfBytes}
                investigationId={investigationId}
                documentId={documentId}
                initialPage={initialPage ?? undefined}
              />
            ) : (
              <EmptyState />
            )}
          </div>
        </div>
        <div className="grid grid-rows-[3fr_2fr] h-full overflow-hidden min-h-0">
          <NotesPanel
            events={events}
            status={status}
            reconnects={reconnects}
            investigationId={investigationId}
            documentId={documentId}
          />
          <NotesFeed events={events} onCiteJump={onCiteJump} />
        </div>
        {/* SPR-07 M5 — CrossDocSidebar as a slide-out behind Cmd+J.
            Preserved so the question→answer cross-doc resolution
            data path stays visible to power users; default-hidden
            because the gutter pill surface (PdfViewer/Gutter.tsx)
            is the new primary affordance. */}
        {legacySidebarOpen && (
          <div
            data-testid="legacy-cross-doc-sidebar"
            className="absolute top-0 right-0 h-full w-[320px] shadow-lg z-20 bg-white"
          >
            <CrossDocSidebar events={events} onCiteJump={onCiteJump} />
            <button
              type="button"
              onClick={() => setLegacySidebarOpen(false)}
              className="absolute top-2 right-2 text-stone-500 hover:text-stone-900 text-sm"
              aria-label="close cross-doc panel"
            >
              ×
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="h-full flex flex-col items-center justify-center text-stone-400">
      <p className="text-sm">No document loaded.</p>
      <p className="text-xs mt-1 font-mono">
        Use the "load PDF" button to begin a wrestling session.
      </p>
    </div>
  );
}
