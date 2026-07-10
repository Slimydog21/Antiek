import { useCallback, useEffect, useRef, useState } from "react";
import { getHtmlProjectionByDocument, HtmlProjectionError, type HtmlProjection } from "../api/htmlProjections";
import { postTypedEvent } from "../lib/api";
import HtmlReader, { type HtmlReaderSelection } from "./HtmlReader";

export interface HtmlReaderPanelProps {
  documentId: string;
  anchorId?: string;
  investigationId?: string;
}

type State = { kind: "loading" } | { kind: "ready"; projection: HtmlProjection } | { kind: "error"; message: string };

function errorMessage(error: unknown): string {
  if (error instanceof HtmlProjectionError) {
    if (error.status === 404) return "No ready HTML projection is available for this document.";
    if (error.status === 409) return "This document has multiple ready HTML projections and cannot be opened unambiguously.";
    if (error.status === 503) return "HTML projection storage is temporarily unavailable.";
    return `The HTML projection service failed (HTTP ${error.status}).${error.detail ? ` ${error.detail}` : ""}`;
  }
  return error instanceof Error ? `Could not load the HTML projection. ${error.message}` : "Could not load the HTML projection.";
}

export default function HtmlReaderPanel({ documentId, anchorId, investigationId }: HtmlReaderPanelProps) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<State>({ kind: "loading" });
  const [postError, setPostError] = useState<string | null>(null);
  const lineageVersion = useRef(0);
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    lineageVersion.current += 1;
    return () => {
      mounted.current = false;
      lineageVersion.current += 1;
    };
  }, [documentId, investigationId]);

  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: "loading" });
    setPostError(null);
    void getHtmlProjectionByDocument(documentId, controller.signal).then(
      (projection) => { if (!controller.signal.aborted) setState({ kind: "ready", projection }); },
      (error) => { if (!controller.signal.aborted) setState({ kind: "error", message: errorMessage(error) }); },
    );
    return () => controller.abort();
  }, [documentId, attempt]);

  const onRegionSelected = useCallback(async (selection: HtmlReaderSelection) => {
    if (!investigationId) {
      setPostError("This selection could not be saved because no investigation is attached to the reader.");
      return;
    }
    const version = lineageVersion.current;
    setPostError(null);
    try {
      await postTypedEvent({ investigation_id: investigationId, document_id: documentId, payload: selection.payload, role: "user_agent" });
    } catch (error) {
      if (mounted.current && lineageVersion.current === version) {
        setPostError(error instanceof Error ? `Could not save selection: ${error.message}` : "Could not save selection.");
      }
    }
  }, [documentId, investigationId]);

  if (state.kind === "loading") return <div role="status" className="flex h-full items-center justify-center">Loading HTML projection…</div>;
  if (state.kind === "error") return <div role="alert" className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center"><p>{state.message}</p><button type="button" aria-label="Retry loading HTML projection" onClick={() => setAttempt((value) => value + 1)}>Retry</button></div>;
  return <div className="relative h-full overflow-hidden"><HtmlReader html={state.projection.html} documentId={documentId} investigationId={investigationId ?? ""} initialAnchorId={anchorId} onRegionSelected={onRegionSelected} />{postError && <p role="alert" className="absolute bottom-4 left-4 right-4">{postError}</p>}</div>;
}
