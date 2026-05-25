import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { onTraceIntent } from "../Editor/traceIntent";
import { getTraceTarget } from "../writeApi";
import { traceActionFor, type TraceAction } from "./traceController";

/**
 * Trace-to-source wiring (specs/write/ SPR-07).
 *
 * Mounts a listener for the editor's ``write:trace-to-source`` intent
 * (emitted by Citation/BlockNode clicks), resolves the trace target via
 * ``GET /write/blocks/{id}/trace`` (which applies the gated-source-no-leak
 * gate), and acts:
 *   • source_span / servable_snippet → navigate to the shared BookReader
 *     at ``/read/{document_id}`` (the reader gates full-text vs snippet on
 *     its own fetch, so a gated source renders snippet-only);
 *   • session / node_only / unavailable → return a non-navigating state
 *     the host renders inline (labeled honestly — no invented document).
 *
 * Opening at the exact cited span (chunk anchor) is a follow-up once the
 * reader accepts a chunk position in its URL; today the trace lands the
 * writer in the right source document, gate-respecting.
 *
 * Returns the latest non-navigating trace state (or null) so a host can
 * render a small trace panel; ``clear`` dismisses it.
 */
export interface UseTraceResult {
  state: TraceAction | null;
  clear: () => void;
}

export function useTrace(): UseTraceResult {
  const navigate = useNavigate();
  const [state, setState] = useState<TraceAction | null>(null);

  useEffect(() => {
    return onTraceIntent(async (detail) => {
      // A node-only intent (e.g. a generated sentence's citation not yet a
      // placed block) has no outline_block_id to resolve server-side; fall
      // back to the intent's own provenance kind, honestly.
      if (!detail.outlineBlockId) {
        setState(
          detail.provenanceKind === "graph_node"
            ? { type: "node_only", detail: "citation resolves to a source node" }
            : { type: "session", detail: "user-originated — traces to the session" },
        );
        return;
      }
      try {
        const target = await getTraceTarget(detail.outlineBlockId);
        const action = traceActionFor(target);
        if (action.type === "open_reader" && action.documentId) {
          navigate(`/read/${encodeURIComponent(action.documentId)}`);
          setState(null);
        } else {
          setState(action);
        }
      } catch (e) {
        setState({ type: "unavailable", detail: String(e) });
      }
    });
  }, [navigate]);

  return { state, clear: () => setState(null) };
}
