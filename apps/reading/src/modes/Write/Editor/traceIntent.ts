/**
 * Trace-to-source intent (specs/write/ SPR-04 M3 ↔ SPR-07).
 *
 * Clicking a citation in the editor must not couple the editor to a
 * specific reader. It emits a decoupled `write:trace-to-source` intent;
 * WriteHome commits the production seam command and opens the shared HTML
 * reader only after the backend resolves current provenance and servability.
 */

export const TRACE_INTENT_EVENT = "write:trace-to-source";

export interface TraceIntentDetail {
  sectionId: string;
  /** The OutlineBlock id, when the citation came from a placed block. */
  outlineBlockId: string | null;
  /** The graph node id for graph-node provenance; null for user-originated. */
  nodeId: string | null;
  provenanceKind: "graph_node" | "user_authored" | "synthesized" | "brainstorm";
  label?: string;
}

/** Dispatch a trace-to-source intent. No-op outside a DOM (SSR/tests
 * without jsdom). Returns whether it dispatched. */
export function emitTraceIntent(detail: TraceIntentDetail): boolean {
  if (typeof window === "undefined" || typeof CustomEvent === "undefined") {
    return false;
  }
  window.dispatchEvent(new CustomEvent<TraceIntentDetail>(TRACE_INTENT_EVENT, { detail }));
  return true;
}

/** Subscribe to trace intents (SPR-07's entry point). Returns an
 * unsubscribe fn. */
export function onTraceIntent(
  handler: (detail: TraceIntentDetail) => void,
): () => void {
  if (typeof window === "undefined") return () => {};
  const listener = (e: Event) => handler((e as CustomEvent<TraceIntentDetail>).detail);
  window.addEventListener(TRACE_INTENT_EVENT, listener);
  return () => window.removeEventListener(TRACE_INTENT_EVENT, listener);
}
