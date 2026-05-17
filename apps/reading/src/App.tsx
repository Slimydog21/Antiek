import { useCallback, useEffect, useState } from "react";

import type {
  DocumentLoadedPayload,
} from "./generated/types";
import CrossDocSidebar from "./components/CrossDocSidebar";
import NotesFeed from "./components/NotesFeed";
import NotesPanel from "./components/NotesPanel";
import PdfViewer from "./components/PdfViewer";
import { useEventStream } from "./hooks/useEventStream";
import { postTypedEvent } from "./lib/api";
import { sha256Hex } from "./lib/hash";

/**
 * Top-level layout: three columns at md+ — PDF render (left), live
 * trajectory chat feed (middle), notes + cross-doc stack (right). The
 * investigation_id is stable per browser tab; the document_id is
 * derived from the content hash so the same file uploaded twice
 * reuses the same id.
 *
 * Sprint 5 day 1-2 added the third column (NotesFeed + CrossDocSidebar)
 * so emergent insights + cross-document linkages are visible in real
 * time alongside the wrestling chat. Pre-Sprint-5 the events were
 * landing in the trajectory log but invisible without ``curl
 * /trajectory/...``.
 */
export default function App() {
  const [investigationId] = useState<string>(() => {
    const stored = window.sessionStorage.getItem("antiek.investigation_id");
    if (stored) return stored;
    const fresh =
      "inv-" + crypto.randomUUID().replace(/-/g, "").slice(0, 12);
    window.sessionStorage.setItem("antiek.investigation_id", fresh);
    return fresh;
  });

  const [pdfBytes, setPdfBytes] = useState<Uint8Array | null>(null);
  const [documentId, setDocumentId] = useState<string | null>(null);
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
          // page_count is filled in after the PDF parses in PdfViewer.
          // For the document.loaded event we leave it null; a future
          // turn could fire a follow-up event with the page count once
          // pdf.js reports it.
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

  // Useful debug surface for the operator.
  useEffect(() => {
    console.info("[antiek] investigation_id:", investigationId);
  }, [investigationId]);

  // Cite-jump: a NotesFeed chip click resolves to a chat-feed row by
  // DOM id (rendered by NotesPanel as `event-row-<event_id>`). We
  // scroll the target into view and pulse a ring class so the eye
  // catches the landing. Failing to resolve is silent — the row may
  // not be rendered yet (event still in flight).
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
    <div className="grid grid-cols-1 md:grid-cols-[2fr_1fr_1fr] gap-0 h-screen">
      <div className="flex flex-col h-full border-r border-stone-200 bg-stone-50">
        <Header
          investigationId={investigationId}
          onFileSelected={onFileSelected}
          loadError={loadError}
        />
        <div className="flex-1 overflow-hidden">
          {pdfBytes && documentId ? (
            <PdfViewer
              pdfBytes={pdfBytes}
              investigationId={investigationId}
              documentId={documentId}
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
      {/* Third column: notes (top half) + cross-doc resolutions (bottom).
          The two stacks share the WebSocket event stream — no extra
          subscription, just different filters. */}
      <div className="grid grid-rows-[3fr_2fr] h-full overflow-hidden">
        <NotesFeed events={events} onCiteJump={onCiteJump} />
        <CrossDocSidebar events={events} />
      </div>
    </div>
  );
}

function Header({
  investigationId,
  onFileSelected,
  loadError,
}: {
  investigationId: string;
  onFileSelected: (f: File) => void;
  loadError: string | null;
}) {
  return (
    <div className="px-4 py-3 bg-white border-b border-stone-200 flex items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <span className="text-base font-semibold">Antiek</span>
        <span className="text-xs font-mono text-stone-500">
          investigation: <span className="text-stone-900">{investigationId}</span>
        </span>
      </div>
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
