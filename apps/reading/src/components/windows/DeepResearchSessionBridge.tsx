import { useEffect, useMemo, useRef, useState } from "react";

import { fetchDeepResearchSessionReference, parseDeepResearchSessionResumeRef, type DeepResearchSessionResumeRef, type DeepResearchSessionProjection } from "../../api/deepResearchSessionRefs";
import { useAuth } from "../../lib/auth";
import DeepResearchSessionHost, { type DeepResearchSessionHostProps } from "./DeepResearchSessionHost";

type State = { status: "loading" } | { status: "unavailable"; key: string } | { status: "ready"; key: string; value: DeepResearchSessionProjection };

function Resolved({ reference }: { reference: DeepResearchSessionResumeRef }) {
  const { state: auth, sessionGeneration } = useAuth();
  const [attempt, setAttempt] = useState(0);
  const identity = reference.session_id;
  const key = `${sessionGeneration}\u0000${identity}`;
  const current = useRef({ sessionGeneration, identity });
  current.current = { sessionGeneration, identity };
  const [state, setState] = useState<State>({ status: "loading" });
  useEffect(() => {
    const abort = new AbortController();
    const request = { sessionGeneration, identity };
    setState({ status: "loading" });
    if (auth.status !== "authenticated") { setState({ status: "unavailable", key }); return () => abort.abort(); }
    void fetchDeepResearchSessionReference(identity, abort.signal).then((value) => {
      if (!abort.signal.aborted && current.current.sessionGeneration === request.sessionGeneration && current.current.identity === request.identity) setState({ status: "ready", key, value });
    }).catch((error: unknown) => {
      if (abort.signal.aborted || (error instanceof DOMException && error.name === "AbortError")) return;
      if (current.current.sessionGeneration === request.sessionGeneration && current.current.identity === request.identity) setState({ status: "unavailable", key });
    });
    return () => abort.abort();
  }, [attempt, auth.status, identity, key, sessionGeneration]);
  if (state.status === "ready" && state.key === key && auth.status === "authenticated") return <DeepResearchSessionHost {...state.value} />;
  if (state.status === "loading" || state.key !== key) return <div className="p-6 text-sm" role="status" data-testid="deep-research-reference-loading">Loading current research session…</div>;
  return <div className="p-6 text-sm" role="alert" data-testid="deep-research-reference-unavailable"><p>This research session is unavailable under the current account.</p><button type="button" onClick={() => setAttempt((value) => value + 1)}>Retry</button></div>;
}

export default function DeepResearchSessionBridge(props: DeepResearchSessionHostProps & { resume_ref?: unknown }) {
  const hasResumeReference = Object.prototype.hasOwnProperty.call(props, "resume_ref");
  const reference = useMemo(() => parseDeepResearchSessionResumeRef(props.resume_ref), [props.resume_ref]);
  if (!hasResumeReference) return <DeepResearchSessionHost {...props} />;
  if (reference === null) return <div className="p-6 text-sm" role="alert" data-testid="deep-research-reference-unavailable">This research session is unavailable under the current account.</div>;
  return <Resolved reference={reference} />;
}
