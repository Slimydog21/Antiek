import { useEffect, useMemo, useRef, useState } from "react";

import {
  fetchHtmlDocumentReference,
  parseHtmlDocumentResumeRef,
  type HtmlDocumentResumeRef,
  type HydratedHtmlDocument,
} from "../../api/htmlDocumentRefs";
import { useAuth } from "../../lib/auth";
import HostedHtmlDocumentHost, {
  type HostedHtmlDocumentHostProps,
} from "./HostedHtmlDocumentHost";

type ReferenceState =
  | { status: "loading" }
  | { status: "unavailable"; requestKey: string }
  | { status: "ready"; requestKey: string; document: HydratedHtmlDocument };

function ReferenceHydratedHtmlDocument({ reference }: { reference: HtmlDocumentResumeRef }) {
  const { state: authState, sessionGeneration } = useAuth();
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<ReferenceState>({ status: "loading" });
  const identity = `${reference.resolver}\u0000${reference.document_id}`;
  const requestKey = `${identity}\u0000${sessionGeneration}`;
  const currentRequest = useRef({ identity, sessionGeneration });
  currentRequest.current = { identity, sessionGeneration };

  useEffect(() => {
    const abort = new AbortController();
    const request = { identity, sessionGeneration };
    setState({ status: "loading" });
    if (authState.status !== "authenticated") {
      setState({ status: "unavailable", requestKey });
      return () => abort.abort();
    }
    void fetchHtmlDocumentReference(reference, abort.signal)
      .then((document) => {
        const current = currentRequest.current;
        if (
          abort.signal.aborted
          || current.identity !== request.identity
          || current.sessionGeneration !== request.sessionGeneration
        ) return;
        setState({ status: "ready", requestKey, document });
      })
      .catch((error: unknown) => {
        if (abort.signal.aborted || (error instanceof DOMException && error.name === "AbortError")) return;
        const current = currentRequest.current;
        if (
          current.identity === request.identity
          && current.sessionGeneration === request.sessionGeneration
        ) setState({ status: "unavailable", requestKey });
      });
    return () => abort.abort();
  }, [attempt, authState.status, identity, reference, sessionGeneration]);

  if (
    state.status === "ready"
    && state.requestKey === requestKey
    && authState.status === "authenticated"
  ) {
    return (
      <HostedHtmlDocumentHost
        document_id={state.document.document_id}
        title={state.document.title}
        view_format="html"
        html={state.document.html}
      />
    );
  }
  if (
    state.status === "loading"
    || state.requestKey !== requestKey
  ) {
    return (
      <div className="p-6 text-sm" data-testid="hosted-html-reference-loading" role="status">
        Loading current document…
      </div>
    );
  }
  return (
    <div className="p-6 text-sm" data-testid="hosted-html-reference-unavailable" role="alert">
      <p>This document is unavailable under the current account.</p>
      <button type="button" onClick={() => setAttempt((value) => value + 1)}>
        Retry
      </button>
    </div>
  );
}

export default function HostedHtmlDocumentBridge(props: HostedHtmlDocumentHostProps) {
  const reference = useMemo(() => parseHtmlDocumentResumeRef(props.resume_ref), [props.resume_ref]);
  if (reference === null) return <HostedHtmlDocumentHost {...props} />;
  return <ReferenceHydratedHtmlDocument reference={reference} />;
}
