import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import LemonButton from "../../components/lemon/LemonButton";
import type { DocumentRegionSelectedPayload } from "../../generated/types";
import { useEventStream } from "../../hooks/useEventStream";
import { postTypedEvent } from "../../lib/api";
import { sanitizeHostedHtml } from "../../lib/sanitizeHostedHtml";
import { PanelHost } from "../../workspace/PanelHost";
import type { StarterPanel } from "../../workspace/PanelHost";
import {
  fetchHostedDocument,
  ingestHostedDocument,
} from "../../api/hostedDocuments";

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

  const [hostedHtml, setHostedHtml] = useState<string | null>(null);
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const loadVersion = useRef(0);

  const { events, status, reconnects } = useEventStream(investigationId);

  const onFileSelected = useCallback(
    async (file: File) => {
      const version = ++loadVersion.current;
      setLoadError(null);
      try {
        const receipt = await ingestHostedDocument({
          content_b64: await fileToBase64(file),
          source_format: sourceFormat(file),
          investigation_id: investigationId,
          title: file.name,
        });
        if (receipt.state !== "ready" || !receipt.html?.trim()) {
          throw new Error(
            `Source retained as a non-viewable receipt: ${receipt.non_viewable_reason || "empty canonical HTML"}`,
          );
        }
        if (version === loadVersion.current) {
          setHostedHtml(receipt.html);
          setDocumentId(receipt.document_id);
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        if (version === loadVersion.current) setLoadError(msg);
      }
    },
    [investigationId],
  );

  useEffect(() => {
    const version = ++loadVersion.current;
    setHostedHtml(null);
    setDocumentId(null);
    setLoadError(null);
    if (!routeDocumentId) return;
    let cancelled = false;
    fetchHostedDocument(routeDocumentId)
      .then((receipt) => {
        if (
          !cancelled &&
          version === loadVersion.current &&
          receipt.state === "ready" &&
          receipt.html
        ) {
          setHostedHtml(receipt.html);
          setDocumentId(receipt.document_id);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled && version === loadVersion.current) {
          setLoadError(error instanceof Error ? error.message : String(error));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [routeDocumentId]);

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
      {hostedHtml && documentId ? (
        <div className="h-full overflow-auto bg-ice-2 p-6 dark:bg-space-2">
          <CanonicalHtmlWrestler
            html={hostedHtml}
            investigationId={investigationId}
            documentId={documentId}
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
        <h1 className="text-2xl font-serif mb-3">Load a document to wrestle.</h1>
        <p className="text-sm text-shadow-1 dark:text-moonlight font-serif leading-relaxed mb-5">
          Drop a PDF, EPUB, HTML, Markdown, or text file. Antiek converts it to
          canonical HTML; highlight any passage to capture it as a region.
          The trajectory feed will appear as a docked panel; cross-document
          bridges appear on the right.
        </p>
        <label className="inline-flex">
          <LemonButton variant="primary" size="lg" type="button" tabIndex={-1}>
            Choose document…
          </LemonButton>
          <input
            type="file"
            accept="application/pdf,.epub,text/html,text/plain,text/markdown,.md"
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

function CanonicalHtmlWrestler({
  html,
  investigationId,
  documentId,
}: {
  html: string;
  investigationId: string;
  documentId: string;
}) {
  const captureSelection = useCallback(async () => {
    const selection = window.getSelection();
    const rawSelection = selection?.toString() || "";
    const excerpt = rawSelection.trim();
    if (!excerpt) return;
    const article = selection?.anchorNode?.parentElement?.closest("article");
    if (!article) return;
    let charStart = Math.max(0, (article.textContent || "").indexOf(excerpt));
    if (selection && selection.rangeCount > 0) {
      const selectedRange = selection.getRangeAt(0);
      if (article.contains(selectedRange.commonAncestorContainer)) {
        const prefix = selectedRange.cloneRange();
        prefix.selectNodeContents(article);
        prefix.setEnd(selectedRange.startContainer, selectedRange.startOffset);
        charStart = prefix.toString().length + rawSelection.search(/\S/);
      }
    }
    const boundedExcerpt = excerpt.slice(0, 2_000);
    const payload: DocumentRegionSelectedPayload = {
      action_type: "document.region_selected",
      region_id: `region-${crypto.randomUUID()}`,
      page: null,
      char_start: charStart,
      char_end: charStart + boundedExcerpt.length,
      bbox: null,
      text_excerpt: boundedExcerpt,
    };
    await postTypedEvent({
      investigation_id: investigationId,
      document_id: documentId,
      payload,
      role: "user_agent",
    });
  }, [documentId, investigationId]);

  return (
    <article
      data-testid="canonical-html-wrestler"
      data-document-id={documentId}
      className="prose mx-auto max-w-4xl dark:prose-invert"
      onMouseUp={() => void captureSelection()}
      dangerouslySetInnerHTML={{ __html: sanitizeHostedHtml(html) }}
    />
  );
}
