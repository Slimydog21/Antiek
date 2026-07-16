import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import thinkingArt from "../../brand/werner/poses/session/werner_thinking_session_v1.png";
import livingTvArt from "../../brand/werner/poses/session/werner_living_tv_session_v1.webp";
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
          investigationId={investigationId}
        />
      )}
    </PanelHost>
  );
}

function EmptyState({
  onFileSelected,
  loadError,
  investigationId,
}: {
  onFileSelected: (file: File) => void;
  loadError: string | null;
  investigationId: string;
}) {
  return (
    <div className="h-full flex items-center justify-center bg-ice-2 dark:bg-space-2">
      <div className="max-w-md text-center px-6 text-ink dark:text-bright">
        {/* Session brand densify — Wrestle empty state is a product door;
            living-TV invent + thinking mark so wait/load is home of the penguin. */}
        <div className="mb-4 flex flex-col items-center gap-2">
          <img
            src={thinkingArt}
            alt=""
            aria-hidden="true"
            data-testid="wrestle-empty-werner-brand"
            className="h-14 w-14 object-contain"
          />
          <img
            src={livingTvArt}
            alt=""
            aria-hidden="true"
            data-testid="wrestle-empty-living-tv-art"
            className="h-14 w-full max-w-sm rounded-md object-cover object-center antiek-living-tv-invent"
            loading="lazy"
            decoding="async"
          />
        </div>
        <h1 className="text-2xl font-serif mb-3">Load a PDF to wrestle.</h1>
        <p className="text-sm text-shadow-1 dark:text-moonlight font-serif leading-relaxed mb-5">
          Drop the PDF. Highlight any passage to capture it as a region.
          The trajectory feed will appear as a docked panel; cross-document
          bridges appear on the right.
        </p>
        <label className="inline-flex">
          <LemonButton variant="primary" size="lg" type="button" tabIndex={-1}>
            Choose PDF…
          </LemonButton>
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
          <div className="text-xs font-mono text-emperor mt-4">{loadError}</div>
        )}
        <p className="mt-6 text-[11px] font-mono text-ink-mute dark:text-moonlight">
          investigation:{" "}
          <span className="text-ink dark:text-bright">{investigationId}</span>
        </p>
      </div>
    </div>
  );
}
