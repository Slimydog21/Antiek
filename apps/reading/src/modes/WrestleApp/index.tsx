import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import LemonButton from "../../components/lemon/LemonButton";
import type { DocumentRegionSelectedPayload } from "../../generated/types";
import { useEventStream } from "../../hooks/useEventStream";
import { postTypedEvent } from "../../lib/api";
import { PanelHost } from "../../workspace/PanelHost";
import type { StarterPanel } from "../../workspace/PanelHost";
import {
  fetchHostedDocument,
  ingestHostedDocument,
  type HostedDocumentReceipt,
} from "../../api/hostedDocuments";

const HostedHtmlDocumentHost = lazy(
  () => import("../../components/windows/HostedHtmlDocumentHost"),
);

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
 *   - Canonical HTML    main slot    (PDF/EPUB are ingest sources only)
 *
 * The "load PDF" upload affordance has moved out of the legacy
 * HeaderBar (now no-op) into the empty-state of the main slot.
 * The investigation id is still stable per browser tab via
 * sessionStorage.
 *
 * The server owns extraction, document identity, and document.loaded.
 * This surface emits only user interaction events over canonical HTML.
 */
export default function WrestleApp() {
  const params = useParams<{ documentId?: string }>();
  const navigate = useNavigate();
  const routeDocumentId = params.documentId ?? null;

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

  const [loadState, setLoadState] = useState<WrestleLoadState>({ kind: "empty" });
  const [interactionError, setInteractionError] = useState<string | null>(null);
  const loadVersion = useRef(0);
  const adoptedReceipt = useRef<HostedDocumentReceipt | null>(null);

  const hosted = loadState.kind === "ready" ? loadState.receipt : null;
  const documentId = hosted?.document_id ?? null;

  const { events, status, reconnects } = useEventStream(investigationId);

  const onFileSelected = useCallback(
    async (file: File) => {
      const version = ++loadVersion.current;
      adoptedReceipt.current = null;
      setInteractionError(null);
      setLoadState({ kind: "loading", source: "upload", title: file.name });
      try {
        const receipt = await ingestHostedDocument({
          content_b64: await fileToBase64(file),
          source_format: sourceFormat(file),
          investigation_id: investigationId,
          title: file.name,
          intent: "user_owned",
        });
        if (version !== loadVersion.current) return;
        if (receipt.state !== "ready" || !receipt.html?.trim()) {
          adoptedReceipt.current = receipt;
          setLoadState({ kind: "non_viewable", receipt });
          navigate(`/wrestle/${encodeURIComponent(receipt.document_id)}`, {
            replace: true,
          });
          return;
        }
        adoptedReceipt.current = receipt;
        setLoadState({ kind: "ready", receipt });
        navigate(`/wrestle/${encodeURIComponent(receipt.document_id)}`, {
          replace: true,
        });
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        if (version === loadVersion.current) {
          setLoadState({ kind: "error", message: msg });
        }
      }
    },
    [investigationId, navigate],
  );

  useEffect(() => {
    const version = ++loadVersion.current;
    setInteractionError(null);
    if (!routeDocumentId) {
      adoptedReceipt.current = null;
      setLoadState({ kind: "empty" });
      return;
    }
    if (adoptedReceipt.current?.document_id === routeDocumentId) return;
    adoptedReceipt.current = null;
    setLoadState({ kind: "loading", source: "route", title: null });
    let cancelled = false;
    fetchHostedDocument(routeDocumentId)
      .then((receipt) => {
        if (cancelled || version !== loadVersion.current) return;
        adoptedReceipt.current = receipt;
        if (receipt.state === "ready" && receipt.html?.trim()) {
          setLoadState({ kind: "ready", receipt });
        } else {
          setLoadState({ kind: "non_viewable", receipt });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled && version === loadVersion.current) {
          setLoadState({
            kind: "error",
            message: error instanceof Error ? error.message : String(error),
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [routeDocumentId]);

  const onHighlightSelection = useCallback(
    async (selection: { text: string; charStart: number; charEnd: number }) => {
      if (!documentId) return;
      const boundedText = selection.text.slice(0, 2_000);
      const payload: DocumentRegionSelectedPayload = {
        action_type: "document.region_selected",
        region_id: `region-${crypto.randomUUID()}`,
        page: null,
        char_start: selection.charStart,
        char_end: selection.charStart + boundedText.length,
        bbox: null,
        text_excerpt: boundedText,
      };
      try {
        await postTypedEvent({
          investigation_id: investigationId,
          document_id: documentId,
          payload,
          role: "user_agent",
        });
      } catch (error: unknown) {
        setInteractionError(
          `Highlight event failed: ${error instanceof Error ? error.message : String(error)}`,
        );
      }
    },
    [documentId, investigationId],
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
          id: `wrestle:notes:${investigationId}:${documentId}`,
        },
        {
          kind: "CrossDocs",
          mode: "docked-right",
          props: { events },
          title: "Cross-doc",
          id: `wrestle:crossdocs:${investigationId}:${documentId}`,
        },
      ] as StarterPanel[])
    : [];

  return (
    <PanelHost key={documentId ?? "empty"} starters={starters}>
      {hosted?.html && documentId ? (
        <div className="relative h-full overflow-auto bg-ice-2 dark:bg-space-2">
          {interactionError ? (
            <div
              className="sticky top-0 z-10 bg-emperor px-3 py-2 text-xs font-mono text-white"
              role="alert"
            >
              {interactionError}
            </div>
          ) : null}
          <Suspense
            fallback={
              <p className="p-4 text-xs font-mono" role="status">
                Loading canonical reading tools…
              </p>
            }
          >
            <HostedHtmlDocumentHost
              document_id={documentId}
              title={hosted.title}
              html={hosted.html}
              view_format="html"
              license_class="private_upload"
              owner_id={hosted.owner_id}
              source="wrestle"
              onHighlightSelection={(selection) =>
                void onHighlightSelection(selection)
              }
            />
          </Suspense>
        </div>
      ) : loadState.kind === "non_viewable" ? (
        <NonViewableReceipt
          receipt={loadState.receipt}
          onFileSelected={onFileSelected}
        />
      ) : (
        <EmptyState
          onFileSelected={onFileSelected}
          loadState={loadState}
          investigationId={investigationId}
        />
      )}
    </PanelHost>
  );
}

function EmptyState({
  onFileSelected,
  loadState,
  investigationId,
}: {
  onFileSelected: (file: File) => void;
  loadState: WrestleLoadState;
  investigationId: string;
}) {
  return (
    <div className="h-full flex items-center justify-center bg-ice-2 dark:bg-space-2">
      <div className="max-w-md text-center px-6 text-ink dark:text-bright">
        <h1 className="text-2xl font-serif mb-3">Load a document to wrestle.</h1>
        <p className="text-sm text-shadow-1 dark:text-moonlight font-serif leading-relaxed mb-5">
          Drop a PDF, EPUB, HTML, Markdown, or text file. Antiek converts it to
          canonical HTML; highlight any passage to capture it as a region.
          The trajectory feed will appear as a docked panel; cross-document
          bridges appear on the right.
        </p>
        <DocumentPicker
          onFileSelected={onFileSelected}
          disabled={loadState.kind === "loading"}
        />
        {loadState.kind === "loading" && (
          <p className="mt-4 text-xs font-mono text-ink dark:text-bright" role="status">
            {loadState.source === "upload"
              ? `Extracting ${loadState.title ?? "document"} into canonical HTML…`
              : "Opening the hosted document…"}
          </p>
        )}
        {loadState.kind === "error" && (
          <div className="text-xs font-mono text-emperor mt-4" role="alert">
            {loadState.message}
          </div>
        )}
        <p className="mt-6 text-[11px] font-mono text-ink-mute dark:text-moonlight">
          investigation:{" "}
          <span className="text-ink dark:text-bright">{investigationId}</span>
        </p>
      </div>
    </div>
  );
}

function NonViewableReceipt({
  receipt,
  onFileSelected,
}: {
  receipt: HostedDocumentReceipt;
  onFileSelected: (file: File) => void;
}) {
  return (
    <div className="h-full flex items-center justify-center bg-ice-2 dark:bg-space-2">
      <section
        className="max-w-md px-6 text-center text-ink dark:text-bright"
        aria-labelledby="non-viewable-title"
        data-testid="wrestle-non-viewable-receipt"
      >
        <h1 id="non-viewable-title" className="text-2xl font-serif mb-3">
          This source was retained, but it isn’t viewable yet.
        </h1>
        <p className="text-sm font-serif text-shadow-1 dark:text-moonlight mb-4">
          Antiek kept the extraction receipt without inventing an empty reading surface.
        </p>
        <dl className="mb-5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-left text-xs font-mono">
          <dt className="text-ink-mute dark:text-moonlight">Title</dt>
          <dd>{receipt.title}</dd>
          <dt className="text-ink-mute dark:text-moonlight">Format</dt>
          <dd>{receipt.source_format.toUpperCase()}</dd>
          <dt className="text-ink-mute dark:text-moonlight">Words extracted</dt>
          <dd>{receipt.word_count.toLocaleString()}</dd>
          <dt className="text-ink-mute dark:text-moonlight">Reason</dt>
          <dd>{receipt.non_viewable_reason ?? "No canonical HTML was produced."}</dd>
        </dl>
        <DocumentPicker onFileSelected={onFileSelected} label="Choose another document…" />
      </section>
    </div>
  );
}

function DocumentPicker({
  onFileSelected,
  disabled = false,
  label = "Choose document…",
}: {
  onFileSelected: (file: File) => void;
  disabled?: boolean;
  label?: string;
}) {
  return (
    <label className={disabled ? "inline-flex cursor-wait opacity-60" : "inline-flex"}>
          <LemonButton
            variant="primary"
            size="lg"
            type="button"
            tabIndex={-1}
            disabled={disabled}
          >
            {label}
          </LemonButton>
          <input
            type="file"
            accept="application/pdf,.epub,text/html,text/plain,text/markdown,.md"
            className="hidden"
            disabled={disabled}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onFileSelected(f);
            }}
          />
        </label>
  );
}

type WrestleLoadState =
  | { kind: "empty" }
  | { kind: "loading"; source: "upload" | "route"; title: string | null }
  | { kind: "ready"; receipt: HostedDocumentReceipt }
  | { kind: "non_viewable"; receipt: HostedDocumentReceipt }
  | { kind: "error"; message: string };

function sourceFormat(file: File): string {
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (extension && ["pdf", "epub", "html", "htm", "txt", "md"].includes(extension)) {
    return extension;
  }
  if (file.type === "application/pdf") return "pdf";
  if (file.type === "text/html") return "html";
  return "text";
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error || new Error("file read failed"));
    reader.onload = () => {
      const value = String(reader.result || "");
      const comma = value.indexOf(",");
      if (comma < 0) reject(new Error("file encoding failed"));
      else resolve(value.slice(comma + 1));
    };
    reader.readAsDataURL(file);
  });
}
