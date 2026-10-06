import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DocumentFork } from "../api/forks";
import { setWorkspaceOwner, workspaceOwnerSession } from "../lib/accountWorkspaceOwner";
import { fetchDocumentForks, forkLineageOf, recordFork, resetForkLineage, useForkLineage } from "./forkLineage";

// The real listForks parser and apiFetch run against synthetic HTTP responses.
// These unit rows are not evidence of a real account, fork or book read.
const aFork: DocumentFork = {
  fork_id: "a-private-fork", parent_document_id: "shared-parent", fork_document_id: "shared-child",
  operation_id: "a-private-operation", fork_point_locator: "page:1", note: "A private fork note",
  generation_id: "a-private-generation", parent_body_sha256: "a".repeat(64), fork_body_sha256: "b".repeat(64),
  created_at: "2026-10-06T00:00:00Z", parent_title: "A private parent title",
};
function response(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
function listed(rows: DocumentFork[], parent: DocumentFork | null = null): Response {
  return response(200, { forks: rows, forked_from: parent });
}
function deferred<T>() {
  let resolve: (value: T) => void = () => { throw new Error("deferred not initialized"); };
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}
const fetches = vi.fn<typeof fetch>();
let reply: () => Promise<Response>;
function expectNoARows() {
  expect(forkLineageOf("shared-child")).toEqual({ forkedFrom: null, forks: [] });
  expect(forkLineageOf("shared-parent")).toEqual({ forkedFrom: null, forks: [] });
  expect(useForkLineage.getState()).toEqual({ byFork: {}, byParent: {} });
}
beforeEach(() => {
  setWorkspaceOwner("account-a");
  resetForkLineage();
  reply = async () => listed([], aFork);
  fetches.mockReset().mockImplementation(async (input) => {
    const path = new URL(String(input), "http://localhost").pathname;
    if (!path.endsWith("/forks")) throw new Error(`Unexpected fork control request: ${path}`);
    return reply();
  });
  vi.stubGlobal("fetch", fetches);
});
afterEach(() => {
  setWorkspaceOwner(null);
  resetForkLineage();
  vi.unstubAllGlobals();
});

describe("fork lineage belongs to the dispatched owner session", () => {
  it("a delayed A HTTP list cannot fill B's same-document lineage after B fails", async () => {
    const a = deferred<Response>();
    reply = () => a.promise;
    const old = fetchDocumentForks("shared-child");
    setWorkspaceOwner("account-b");
    reply = async () => response(503, { detail: "controlled B failure" });
    await fetchDocumentForks("shared-child");
    expect(fetches).toHaveBeenCalledTimes(2);
    expectNoARows();
    a.resolve(listed([], aFork));
    await old;
    expectNoARows();
  });

  it("loaded A notes, titles and relation ids retire immediately and B failure cannot retain them", async () => {
    await fetchDocumentForks("shared-child");
    expect(forkLineageOf("shared-child").forkedFrom).toEqual(aFork);
    expect(forkLineageOf("shared-parent").forks).toEqual([aFork]);
    setWorkspaceOwner("account-b");
    expectNoARows();
    reply = async () => response(403, { detail: "controlled B denial" });
    await fetchDocumentForks("shared-child");
    expectNoARows();
  });

  it("same-owner callers dedupe the real HTTP request and learn both relation directions", async () => {
    const a = deferred<Response>();
    reply = () => a.promise;
    const owner = workspaceOwnerSession();
    const first = fetchDocumentForks("shared-parent");
    const second = fetchDocumentForks("shared-parent");
    expect(second).toBe(first);
    setWorkspaceOwner("account-a");
    expect(workspaceOwnerSession()).toBe(owner);
    expect(fetchDocumentForks("shared-parent")).toBe(first);
    expect(fetches).toHaveBeenCalledOnce();
    expect(fetches.mock.calls[0][1]?.credentials).toBe("include");
    a.resolve(listed([aFork]));
    await first;
    expect(forkLineageOf("shared-parent").forks).toEqual([aFork]);
    expect(forkLineageOf("shared-child").forkedFrom).toEqual(aFork);
  });

  it("an old A finalizer cannot remove B's pending dedupe slot", async () => {
    const a = deferred<Response>();
    reply = () => a.promise;
    const old = fetchDocumentForks("shared-parent");
    setWorkspaceOwner("account-b");
    const b = deferred<Response>();
    reply = () => b.promise;
    const current = fetchDocumentForks("shared-parent");
    expect(current).not.toBe(old);
    a.resolve(listed([aFork]));
    await old;
    expect(fetchDocumentForks("shared-parent")).toBe(current);
    expect(fetches).toHaveBeenCalledTimes(2);
    expectNoARows();
    const bFork: DocumentFork = { ...aFork, fork_id: "b-fork", operation_id: "b-operation",
      note: "B fork note", generation_id: null, parent_title: "B parent title" };
    b.resolve(listed([bFork]));
    await current;
    expect(forkLineageOf("shared-parent").forks).toEqual([bFork]);
    expect(forkLineageOf("shared-child").forkedFrom).toEqual(bFork);
    expect(JSON.stringify(useForkLineage.getState())).not.toContain("A private");
  });

  it("direct writes captured by retired A are rejected even after A-B-A, while fresh A succeeds", () => {
    const oldOwner = workspaceOwnerSession();
    setWorkspaceOwner("account-b");
    recordFork(aFork, oldOwner);
    expectNoARows();
    setWorkspaceOwner("account-a");
    recordFork(aFork, oldOwner);
    expectNoARows();
    recordFork(aFork, workspaceOwnerSession());
    expect(forkLineageOf("shared-child").forkedFrom).toEqual(aFork);
  });

  it("unknown identity dispatches no HTTP request and cannot learn a direct row", async () => {
    setWorkspaceOwner(null);
    await fetchDocumentForks("shared-parent");
    recordFork(aFork, workspaceOwnerSession());
    expect(fetches).not.toHaveBeenCalled();
    expectNoARows();
  });
});
