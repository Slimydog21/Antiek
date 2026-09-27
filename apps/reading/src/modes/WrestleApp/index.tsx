import WorkflowArt from "../../brand/WorkflowArt";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { getBook } from "../../api/books";
import LemonButton from "../../components/lemon/LemonButton";
import PdfViewer from "../../components/PdfViewer";
import type { DocumentLoadedPayload } from "../../generated/types";
import { useEventStream } from "../../hooks/useEventStream";
import { postTypedEvent } from "../../lib/api";
import { sha256Hex } from "../../lib/hash";
import { PanelHost } from "../../workspace/PanelHost";
import type { StarterPanel } from "../../workspace/PanelHost";

/**
 * Mode B — Document Wrestler (S6 redesign).
 *
 * Pre-S6 the route hand-rolled a 3-column grid (PDF | NotesPanel |
 * CrossDocSidebar) and rendered HeaderBar at the top. After S6 the
 * route renders inside `PanelHost`, which provides the chrome via
 * `AppShell`:
 *
 *   - NotesPanel        docked-left  (trajectory chat panel)
 *   - CrossDocSidebar   docked-right (cross-document bridges)
 *   - PdfViewer         main slot    (the PDF you're wrestling)
 *
 * The "load PDF" upload affordance has moved out of the legacy
 * HeaderBar (now no-op) into the empty-state of the main slot.
 * The investigation id is still stable per browser tab via
 * sessionStorage.
 *
 * pdf.js inside a docked panel uses `usePanelSizeStable` to debounce
 * re-rasterisation so the worker doesn't thrash during resize gestures.
 */
export default function WrestleApp() {
  const params = useParams<{ documentId?: string }>();
  const initialDocumentId = params.documentId ?? null;

  // Read ?page= deep-link from Mode A's chunk-citation modal.
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

  // /wrestle/:documentId is linked from Documents, the command palette, the
  // citation modal and the project tree. Wrestle only opens PDF bytes chosen
  // from the reader's computer (no endpoint serves a stored PDF by id), so a
  // deep link must say what the id is and where it can be read, instead of
  // landing on the generic "Load a PDF" page.
  const [linked, setLinked] = useState<LinkedDocument>(
    initialDocumentId ? { kind: "loading" } : { kind: "none" },
  );
  const [lookupToken, setLookupToken] = useState(0);
  useEffect(() => {
    if (!initialDocumentId) return;
    let cancelled = false;
    setLinked({ kind: "loading" });
    getBook(initialDocumentId).then(
      (book) => {
        if (!cancelled) setLinked({ kind: "book", title: book.title });
      },
      (err: unknown) => {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : String(err);
        setLinked(message === "book_not_found" ? { kind: "not_stored" } : { kind: "error" });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [initialDocumentId, lookupToken]);

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
      "[antiek/wrestle] investigation_id:",
      investigationId,
      "documentId:",
      documentId,
      "initialPage:",
      initialPage,
    );
  }, [investigationId, documentId, initialPage]);

  // Side panels start only when a document is loaded. Until then the
  // PanelHost shows just the upload-prompting EmptyState in the main slot.
  const starters: StarterPanel[] = documentId
    ? ([
        {
          kind: "Notes",
          mode: "docked-left",
          props: {
            events,
            status,
            reconnects,
            investigationId,
            documentId,
          },
          title: "Notes · trajectory",
          id: `wrestle:notes:${investigationId}`,
        },
        {
          kind: "CrossDocs",
          mode: "docked-right",
          props: { events },
          title: "Cross-doc",
          id: `wrestle:crossdocs:${investigationId}`,
        },
      ] as StarterPanel[])
    : [];

  return (
    <PanelHost starters={starters}>
      {pdfBytes && documentId ? (
        <div className="h-full overflow-hidden bg-ice-2 dark:bg-space-2">
          <PdfViewer
            pdfBytes={pdfBytes}
            investigationId={investigationId}
            documentId={documentId}
            initialPage={initialPage ?? undefined}
          />
        </div>
      ) : (
        <EmptyState
          onFileSelected={onFileSelected}
          loadError={loadError}
          linked={linked}
          linkedDocumentId={initialDocumentId}
          onRetryLookup={() => setLookupToken((n) => n + 1)}
        />
      )}
    </PanelHost>
  );
}

type LinkedDocument =
  | { kind: "none" }
  | { kind: "loading" }
  | { kind: "book"; title: string | null }
  | { kind: "not_stored" }
  | { kind: "error" };

function EmptyState({
  onFileSelected,
  loadError,
  linked,
  linkedDocumentId,
  onRetryLookup,
}: {
  onFileSelected: (file: File) => void;
  loadError: string | null;
  linked: LinkedDocument;
  linkedDocumentId: string | null;
  onRetryLookup: () => void;
}) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const navigate = useNavigate();
  const choosePdf = () => fileInputRef.current?.click();

  let heading = "Load a PDF to wrestle.";
  let body: ReactNode =
    "Drop the PDF. Highlight any passage to capture it as a region. The " +
    "trajectory feed will appear as a docked panel; cross-document bridges " +
    "appear on the right.";
  let actions: ReactNode = (
    <LemonButton variant="primary" size="lg" type="button" onClick={choosePdf}>
      Choose PDF…
    </LemonButton>
  );
  if (linked.kind === "loading") {
    heading = "Looking up this document…";
    body = null;
    actions = null;
  } else if (linked.kind === "book" && linkedDocumentId) {
    heading = linked.title ?? "This book is in your library.";
    body =
      (linked.title ? "This book is in your library. " : "") +
      "Read it in the Reader, or choose its PDF from your computer to " +
      "wrestle with it here.";
    actions = (
      <>
        <LemonButton
          variant="primary"
          size="lg"
          type="button"
          onClick={() => navigate(`/read/${encodeURIComponent(linkedDocumentId)}`)}
        >
          Open in the Reader
        </LemonButton>
        <LemonButton variant="secondary" size="lg" type="button" onClick={choosePdf}>
          Choose its PDF…
        </LemonButton>
      </>
    );
  } else if (linked.kind === "not_stored") {
    heading = "There's no PDF stored for this document.";
    body =
      "Wrestle works on a PDF you choose from your computer. Choose this " +
      "document's PDF to wrestle with it, or go back to your documents.";
    actions = (
      <>
        <LemonButton variant="primary" size="lg" type="button" onClick={choosePdf}>
          Choose its PDF…
        </LemonButton>
        <Link to="/documents" className="text-sm underline underline-offset-2">
          Back to documents
        </Link>
      </>
    );
  } else if (linked.kind === "error") {
    heading = "Couldn't look up this document.";
    body =
      "The server didn't answer. Try again, or choose the PDF from your " +
      "computer to wrestle with it now.";
    actions = (
      <>
        <LemonButton variant="primary" size="lg" type="button" onClick={onRetryLookup}>
          Try again
        </LemonButton>
        <LemonButton variant="secondary" size="lg" type="button" onClick={choosePdf}>
          Choose PDF…
        </LemonButton>
      </>
    );
  }

  return (
    <div className="h-full flex items-center justify-center bg-ice-2 dark:bg-space-2">
      <div
        className="max-w-md text-center px-6 text-ink dark:text-bright"
        role={linked.kind === "loading" ? "status" : undefined}
      >
        <span className="flex items-center gap-3"><WorkflowArt workflow="wrestler" size={52} className="shrink-0" /><h1 className="text-2xl font-serif mb-3">{heading}</h1></span>
        {body && (
          <p className="text-sm text-shadow-1 dark:text-moonlight font-serif leading-relaxed mb-5">
            {body}
          </p>
        )}
        {/* Real focusable buttons that delegate to the input — the previous
            label-wrapped tabIndex={-1} button + hidden input was unreachable
            by keyboard and screen reader (ui-audit 15-modes-f). */}
        {actions && (
          <div className="flex flex-wrap items-center justify-center gap-3">{actions}</div>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          tabIndex={-1}
          aria-hidden="true"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onFileSelected(f);
          }}
        />
        {loadError && (
          <p role="alert" className="text-sm text-emperor mt-4">
            Couldn't open that PDF: {loadError}
          </p>
        )}
        {/* No investigation id is rendered — the house no-id posture (Speak,
            Write). The id stays in console.info for debugging. */}
      </div>
    </div>
  );
}
