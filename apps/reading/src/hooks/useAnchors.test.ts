/**
 * useAnchors.test.ts — the anchor-first SPR-03 client hook.
 *
 * The proofs the spec names: load → a paint-ready anchor list (status +
 * exact_valid + the nullable investigation_id seam); pin → POST → refetch
 * (the stored row shows up); delete → idempotent 204 → the row is gone.
 * The transport is the real apiFetch mocked at the module boundary.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";

import type { BookAnchor } from "../lib/api";

function makeAnchor(over: Partial<BookAnchor> = {}): BookAnchor {
  return {
    anchor_id: "ahl-1",
    document_id: "doc-1",
    anchor: {
      normalization: "unicode-nfc-v1",
      node_id: "c-1",
      node_text_sha256: "h".repeat(64),
      start_scalar: 10,
      end_scalar: 21,
      quote: "gamma delta",
      prefix: "Alpha beta ",
      suffix: " epsilon",
    },
    servable_at_pin: true,
    selection_text_sha256: "s".repeat(64),
    page_index_hint: 2,
    source: "pin",
    status: "active",
    exact_valid: true,
    investigation_id: null,
    created_at: "2026-09-24T10:00:00Z",
    updated_at: "2026-09-24T10:00:00Z",
    ...over,
  };
}

// Mock the REAL boundary: apiFetch's own functions keep their module-local
// apiFetch binding, but every call ends at the global fetch. Stub that.
const fetchMock = vi.fn();

import { useAnchors } from "./useAnchors";

function queueResponse(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => (typeof body === "string" ? body : JSON.stringify(body)),
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("useAnchors", () => {
  it("loads the owner's anchors on mount, paint-ready with the SPR-04 seam", async () => {
    const anchor = makeAnchor();
    queueResponse(200, { document_id: "doc-1", anchors: [anchor], count: 1 });
    const { result } = renderHook(() => useAnchors("doc-1"));

    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeNull();
    expect(result.current.anchors).toHaveLength(1);
    const a = result.current.anchors[0];
    expect(a.status).toBe("active");
    expect(a.exact_valid).toBe(true);
    expect(a.investigation_id).toBeNull();
    expect(fetchMock.mock.calls[0][0]).toContain("/books/doc-1/anchors");
  });

  it("pin POSTs the quote and refetches so the stored row shows up", async () => {
    queueResponse(200, { document_id: "doc-1", anchors: [], count: 0 });
    const { result } = renderHook(() => useAnchors("doc-1"));
    await waitFor(() => expect(result.current.loading).toBe(false));

    const stored = makeAnchor({ anchor_id: "ahl-2" });
    queueResponse(201, stored);
    queueResponse(200, { document_id: "doc-1", anchors: [stored], count: 1 });
    await act(async () => {
      await result.current.pin({
        quote: "gamma delta",
        prefix: "Alpha beta ",
        suffix: " epsilon",
        source: "pin",
      });
    });
    const post = fetchMock.mock.calls[1];
    expect(post[0]).toContain("/books/doc-1/anchors");
    expect(post[1]?.method).toBe("POST");
    expect(JSON.parse(String(post[1]?.body)).quote).toBe("gamma delta");
    await waitFor(() => expect(result.current.anchors).toHaveLength(1));
    expect(result.current.anchors[0].anchor_id).toBe("ahl-2");
  });

  it("delete is an idempotent 204 and the row is gone after refetch", async () => {
    const stored = makeAnchor();
    queueResponse(200, { document_id: "doc-1", anchors: [stored], count: 1 });
    const { result } = renderHook(() => useAnchors("doc-1"));
    await waitFor(() => expect(result.current.anchors).toHaveLength(1));

    queueResponse(204, "");
    queueResponse(200, { document_id: "doc-1", anchors: [], count: 0 });
    await act(async () => {
      await result.current.remove(stored.anchor_id);
    });
    const del = fetchMock.mock.calls[1];
    expect(del[0]).toContain(`/books/doc-1/anchors/${stored.anchor_id}`);
    expect(del[1]?.method).toBe("DELETE");
    await waitFor(() => expect(result.current.anchors).toHaveLength(0));
  });

  it("a load failure surfaces the error honestly and empties the list", async () => {
    queueResponse(500, "server exploded");
    const { result } = renderHook(() => useAnchors("doc-1"));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toContain("500");
    expect(result.current.anchors).toHaveLength(0);
  });

  it("a null document id loads nothing and never fetches", () => {
    const { result } = renderHook(() => useAnchors(null));
    expect(result.current.loading).toBe(false);
    expect(result.current.anchors).toHaveLength(0);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
