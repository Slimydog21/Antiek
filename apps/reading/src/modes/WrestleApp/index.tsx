import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getHtmlProjectionByDocument, HtmlProjectionError, type HtmlProjection } from "../../api/htmlProjections";
import HtmlReader, { type HtmlReaderSelection } from "../../components/HtmlReader";
import { useEventStream } from "../../hooks/useEventStream";
import { postTypedEvent } from "../../lib/api";
import { PanelHost, type StarterPanel } from "../../workspace/PanelHost";

type LoadState = { kind: "loading" } | { kind: "ready"; projection: HtmlProjection } | { kind: "error"; message: string };

function loadMessage(error: unknown): string {
  if (error instanceof HtmlProjectionError) {
    if (error.status === 404) return "No ready HTML projection is available for this document.";
    if (error.status === 409) return "This document has multiple ready HTML projections, so it cannot be opened unambiguously.";
    if (error.status === 503) return "HTML projection storage is temporarily unavailable.";
    return `The HTML projection service failed (HTTP ${error.status}).${error.detail ? ` ${error.detail}` : ""}`;
  }
  return error instanceof Error ? `Could not reach the HTML projection service. ${error.message}` : "Could not reach the HTML projection service.";
}

export default function WrestleApp() {
  const { documentId } = useParams<{ documentId?: string }>();
  const anchor = new URLSearchParams(window.location.search).get("anchor") || undefined;
  const [investigationId] = useState(() => {
    const stored = sessionStorage.getItem("antiek.investigation_id");
    if (stored) return stored;
    const fresh = `inv-${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
    sessionStorage.setItem("antiek.investigation_id", fresh);
    return fresh;
  });
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<LoadState>(() => documentId ? { kind: "loading" } : { kind: "error", message: "A document ID is required to open WrestleApp." });
  const [postError, setPostError] = useState<string | null>(null);
  const { events, status, reconnects } = useEventStream(investigationId);

  useEffect(() => {
    if (!documentId) { setState({ kind: "error", message: "A document ID is required to open WrestleApp." }); return; }
    const controller = new AbortController();
    setState({ kind: "loading" }); setPostError(null);
    void getHtmlProjectionByDocument(documentId, controller.signal).then(
      (projection) => { if (!controller.signal.aborted) setState({ kind: "ready", projection }); },
      (error) => { if (!controller.signal.aborted) setState({ kind: "error", message: loadMessage(error) }); },
    );
    return () => controller.abort();
  }, [documentId, attempt]);

  const onRegionSelected = useCallback(async (selection: HtmlReaderSelection) => {
    if (!documentId) return;
    setPostError(null);
    try {
      await postTypedEvent({ investigation_id: investigationId, document_id: documentId, payload: selection.payload, role: "user_agent" });
    } catch (error) {
      setPostError(error instanceof Error ? `Could not save selection: ${error.message}` : "Could not save selection.");
    }
  }, [documentId, investigationId]);

  const starters: StarterPanel[] = documentId ? [{
    kind: "Notes", mode: "docked-left", props: { events, status, reconnects, investigationId, documentId },
    title: "Notes · trajectory", id: `wrestle:notes:${investigationId}`,
  }, { kind: "CrossDocs", mode: "docked-right", props: { events }, title: "Cross-doc", id: `wrestle:crossdocs:${investigationId}` }] : [];

  return <PanelHost starters={starters}>
    <div className="h-full overflow-hidden bg-ice-2 dark:bg-space-2">
      {state.kind === "loading" && <div role="status" className="flex h-full items-center justify-center">Loading HTML projection…</div>}
      {state.kind === "error" && <div role="alert" className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center"><p>{state.message}</p>{documentId && <button type="button" onClick={() => setAttempt((value) => value + 1)}>Retry</button>}</div>}
      {state.kind === "ready" && <><HtmlReader html={state.projection.html} investigationId={investigationId} documentId={documentId!} initialAnchorId={anchor} onRegionSelected={onRegionSelected} />{postError && <p role="alert" className="absolute bottom-4 left-4 right-4">{postError}</p>}</>}
    </div>
  </PanelHost>;
}
