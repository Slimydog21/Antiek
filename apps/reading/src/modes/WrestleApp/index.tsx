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

/**
 * Mode B — Document Wrestler.
 *
 * Three columns: PDF (left), live trajectory chat (middle), notes +
 * cross-doc stack (right). One investigation per browser tab; document_id
 * is content-hash-derived so the same file uploaded twice reuses the
 * id. The `?page=` query param (read in PdfViewer via initialPage prop
 * — Sprint 11 day 8 wiring) jumps to a specific page on load — used
 * when Mode A's chunk-citation modal opens a source document.
 *
 * Behavior unchanged from the pre–Sprint-11 single-mode App.tsx. Only
 * structural change: moved under /wrestle route, header bar shared with
 * Mode A.
 */
export default function WrestleApp() {
  const params = useParams<{ documentId?: string }>();
  const initialDocumentId = params.documentId ?? null;
  // Read ?page= from the query string (Sprint 11 day 8: deep-link from
  // Mode A's chunk modal). PdfViewer reads initialPage to jump.
  const initialPage = (() => {
    const usp = new URLSearchParams(window.location.search);
    const raw = usp.get("page");
    if (!raw) return null;
    const n = parseInt(raw, 10);
    return Number.isFinite(n) && n > 0 ? n : null;
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
      "documentId:", documentId, "initialPage:", initialPage,
    );
  }, [investigationId, documentId, initialPage]);

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
        {loadError && (
          <div className="text-xs font-mono text-red-700">{loadError}</div>
        )}
      </HeaderBar>
      <div className="grid grid-cols-1 md:grid-cols-[2fr_1fr_1fr] gap-0 flex-1 min-h-0">
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
        <NotesPanel
          events={events}
          status={status}
          reconnects={reconnects}
          investigationId={investigationId}
          documentId={documentId}
        />
        <div className="grid grid-rows-[3fr_2fr] h-full overflow-hidden min-h-0">
          <NotesFeed events={events} onCiteJump={onCiteJump} />
          <CrossDocSidebar events={events} />
        </div>
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
