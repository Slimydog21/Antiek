/**
 * Trace-to-source action mapping (specs/write/ SPR-07).
 *
 * Maps a resolved trace target (from ``GET /write/blocks/{id}/trace``,
 * which already applied the gated-source-no-leak gate) to a UI action:
 * open the shared reader, or show a non-navigating state (user-originated
 * session, node-only, or unavailable). The reader (Read's BookReader)
 * additionally enforces servability on its own full-text fetch, so opening
 * a gated source is safe — it renders the snippet, not the gated full text.
 *
 * This is the pure, testable decision; ``useTrace`` performs the effect.
 */

import type { TraceTargetResponse } from "../writeApi";

export type TraceAction =
  | { type: "open_reader"; documentId: string; servableOnly: boolean; detail: string }
  | { type: "session"; detail: string }
  | { type: "node_only"; detail: string }
  | { type: "unavailable"; detail: string };

export function traceActionFor(target: TraceTargetResponse): TraceAction {
  switch (target.kind) {
    case "source_span":
      return {
        type: "open_reader",
        documentId: target.document_id ?? "",
        servableOnly: false,
        detail: target.detail,
      };
    case "servable_snippet":
      // Still opens the reader; the reader serves snippet-only for a gated
      // source. servableOnly drives the UI hint, never a full-text leak.
      return {
        type: "open_reader",
        documentId: target.document_id ?? "",
        servableOnly: true,
        detail: target.detail,
      };
    case "session":
      return { type: "session", detail: target.detail };
    case "node_only":
      return { type: "node_only", detail: target.detail };
    case "unavailable":
    default:
      return { type: "unavailable", detail: target.detail };
  }
}
