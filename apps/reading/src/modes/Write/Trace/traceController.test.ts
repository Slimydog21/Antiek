import { describe, it, expect } from "vitest";

import type { TraceTargetResponse } from "../writeApi";
import { traceActionFor } from "./traceController";

/**
 * SPR-07: a resolved trace target maps to the right UI action, and a
 * gated source opens the reader as servable-only — never a full-text leak.
 */

function target(over: Partial<TraceTargetResponse>): TraceTargetResponse {
  return {
    kind: "source_span", full_text_allowed: true, document_id: "doc-1",
    document_title: "Doc", chunk_ids: [], servability_status: "public_domain",
    detail: "", ...over,
  };
}

describe("traceActionFor", () => {
  it("opens the reader (full) for a servable source span", () => {
    const a = traceActionFor(target({ kind: "source_span", full_text_allowed: true }));
    expect(a).toMatchObject({ type: "open_reader", documentId: "doc-1", servableOnly: false });
  });

  it("opens the reader as servable-only for a gated source (no leak)", () => {
    const a = traceActionFor(target({
      kind: "servable_snippet", full_text_allowed: false,
      servability_status: "gated_metadata_only",
    }));
    expect(a).toMatchObject({ type: "open_reader", servableOnly: true });
  });

  it("shows the session for a user-originated block", () => {
    const a = traceActionFor(target({ kind: "session", document_id: null }));
    expect(a.type).toBe("session");
  });

  it("shows unavailable for a dangling source", () => {
    const a = traceActionFor(target({ kind: "unavailable", document_id: null, full_text_allowed: false }));
    expect(a.type).toBe("unavailable");
  });

  it("shows node_only when resolved to a node with no document", () => {
    const a = traceActionFor(target({ kind: "node_only", document_id: null }));
    expect(a.type).toBe("node_only");
  });
});
