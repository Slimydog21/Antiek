import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BookAnchor } from "../lib/api";
import { setWorkspaceOwner } from "../lib/accountWorkspaceOwner";
import { useAnchors } from "./useAnchors";

// Real hook and apiFetch; only the external HTTP boundary is synthetic.
const documentId = "shared-book";
const aAnchor: BookAnchor = {
  anchor_id: "a-private-anchor", document_id: documentId,
  anchor: { normalization: "unicode-nfc-v1", node_id: "a-chunk", node_text_sha256: "a".repeat(64),
    start_scalar: 0, end_scalar: 15, quote: "A private quote", prefix: "A prefix", suffix: "A suffix" },
  servable_at_pin: true, selection_text_sha256: "b".repeat(64), page_index_hint: 0,
  source: "pin", status: "active", exact_valid: true, investigation_id: "a-private-investigation",
  created_at: "2026-10-06T00:00:00Z", updated_at: "2026-10-06T00:00:00Z",
};
function response(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
function list(anchors: BookAnchor[]): Response {
  return response(200, { document_id: documentId, anchors, count: anchors.length });
}
function deferred<T>() {
  let resolve: (value: T) => void = () => { throw new Error("deferred not initialized"); };
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}
let listReply: () => Promise<Response>;
let pinReply: () => Promise<Response>;
const fetches = vi.fn<typeof fetch>();
beforeEach(() => {
  setWorkspaceOwner("account-a");
  listReply = async () => list([aAnchor]);
  pinReply = async () => response(201, aAnchor);
  fetches.mockReset().mockImplementation(async (input, init) => {
    const path = new URL(String(input), "http://localhost").pathname;
    if (path !== `/books/${documentId}/anchors`) throw new Error(`Unexpected anchor control request: ${path}`);
    return init?.method === "POST" ? pinReply() : listReply();
  });
  vi.stubGlobal("fetch", fetches);
});
afterEach(() => { cleanup(); setWorkspaceOwner(null); vi.unstubAllGlobals(); });

describe("same-document anchors follow the trusted owner session", () => {
  it("immediately retires loaded A quotes, ids and research links when B is admitted", async () => {
    const { result } = renderHook(() => useAnchors(documentId));
    await waitFor(() => expect(result.current.anchors).toEqual([aAnchor]), { timeout: 10000 });
    const b = deferred<Response>();
    listReply = () => b.promise;
    act(() => { setWorkspaceOwner("account-b"); });
    expect(result.current.anchors).toEqual([]);
    expect(JSON.stringify(result.current)).not.toContain("a-private");
    expect(JSON.stringify(result.current)).not.toContain("A private quote");
    expect(result.current.loading).toBe(true);
    await act(async () => { b.resolve(list([])); });
    expect(result.current.anchors).toEqual([]);
    expect(result.current.loading).toBe(false);
  }, 15000);

  it("refuses a delayed A list after B loads the same document", async () => {
    const a = deferred<Response>();
    listReply = () => a.promise;
    const { result } = renderHook(() => useAnchors(documentId));
    listReply = async () => list([]);
    act(() => { setWorkspaceOwner("account-b"); });
    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 10000 });
    await act(async () => { a.resolve(list([aAnchor])); });
    expect(result.current.anchors).toEqual([]);
    expect(result.current.error).toBeNull();
  }, 15000);

  it("preserves A's loaded anchors and normal pin/refetch under the same owner", async () => {
    const { result } = renderHook(() => useAnchors(documentId));
    await waitFor(() => expect(result.current.anchors).toEqual([aAnchor]), { timeout: 10000 });
    const count = fetches.mock.calls.length;
    act(() => { setWorkspaceOwner("account-a"); });
    expect(result.current.anchors).toEqual([aAnchor]);
    expect(fetches).toHaveBeenCalledTimes(count);
    const stored: BookAnchor = { ...aAnchor, anchor_id: "a-new-pin" };
    pinReply = async () => response(201, stored);
    listReply = async () => list([aAnchor, stored]);
    await act(async () => { expect(await result.current.pin({ quote: "A private quote", source: "pin" })).toEqual(stored); });
    await waitFor(() => expect(result.current.anchors).toEqual([aAnchor, stored]), { timeout: 10000 });
    const post = fetches.mock.calls.find(([, init]) => init?.method === "POST");
    expect(post?.[1]?.credentials).toBe("include");
    expect(post?.[1]?.body).toBe(JSON.stringify({ quote: "A private quote", source: "pin" }));
    act(result.current.refetch);
    await waitFor(() => expect(fetches).toHaveBeenCalledTimes(count + 3), { timeout: 10000 });
    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 10000 });
    expect(result.current.anchors).toEqual([aAnchor, stored]);
  }, 15000);

  it("a captured A refetch callback cannot dispatch as B", async () => {
    const { result } = renderHook(() => useAnchors(documentId));
    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 10000 });
    const staleRefetch = result.current.refetch;
    const stalePin = result.current.pin;
    listReply = async () => list([]);
    act(() => { setWorkspaceOwner("account-b"); });
    await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 10000 });
    const count = fetches.mock.calls.length;
    act(staleRefetch);
    await act(async () => { await expect(stalePin({ quote: "A private quote" })).rejects.toThrow("Account changed"); });
    expect(fetches).toHaveBeenCalledTimes(count);
    expect(result.current.anchors).toEqual([]);
  }, 15000);
});
