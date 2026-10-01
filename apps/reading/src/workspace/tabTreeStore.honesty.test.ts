import { ApiError } from "../lib/api";
import { setTabOwner } from "./tabTreeOwner";
/**
 * tabTreeStore.honesty.test.ts — A2b items 5 and 6:
 *  - `persistenceIssue`: a save the server refuses (422) is recorded, after
 *    the existing log, refetch and rebase, and a later accepted save clears
 *    it, so "server" never claims tabs are saved while they are not;
 *  - GET /projects: a network error is retried (1 s, 4 s, 15 s) before the
 *    trees settle on session persistence, and a 200 whose body is not JSON
 *    (the SPA fallback when the edge does not route /projects) is treated
 *    like a 404: the route is absent, so session, with no retry.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { toast } from "../components/lemon/LemonToast";
import {
  createInMemoryTabTreeAdapter,
  type SaveResult,
  type TabTreeAdapter,
} from "./tabTree";
import { tabsSaved, useTabTrees } from "./tabTreeStore";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", async (orig) => {
  const actual = await orig<typeof import("../lib/api")>();
  return { ...actual, apiFetch: apiFetchMock };
});

const tabs = () => useTabTrees.getState();
const flush = async (n = 8) => {
  for (let i = 0; i < n; i++) await Promise.resolve();
};

function project(id: string) {
  return {
    project_id: id,
    title: id,
    kind: "project",
    order: 0,
    pinned: false,
    archived_at: null,
    primary_document_id: null,
    created_at: "2026-09-27T00:00:00Z",
    updated_at: null,
    member_count: 0,
  };
}

function respond(status: number, body: unknown) {
  apiFetchMock.mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    json: async () => structuredClone(body),
    text: async () => JSON.stringify(body),
  });
}

/** What a real Response does with index.html: 200, and json() rejects. */
function respondHtml() {
  const html = '<!doctype html><html><head><title>Antiek</title></head><body><div id="root"></div></body></html>';
  apiFetchMock.mockResolvedValueOnce({
    ok: true,
    status: 200,
    headers: new Headers({ "content-type": "text/html" }),
    json: async () => {
      throw new SyntaxError("Unexpected token '<', \"<!doctype \"... is not valid JSON");
    },
    text: async () => html,
  });
}

/** What fetch does with no network: it rejects with a TypeError. */
function networkDown() {
  apiFetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
}

beforeEach(() => {
  setTabOwner(null);
  setTabOwner("a2-fixture-owner");
  apiFetchMock.mockReset();
  tabs().resetTabTrees();
});
afterEach(() => {
  setTabOwner(null);
  vi.useRealTimers();
  vi.restoreAllMocks();
  tabs().resetTabTrees();
});

describe("persistenceIssue: the last save was accepted, or it says so (A2b item 5)", () => {
  it("a 422 records {reason: refused, at}; a later accepted save clears it", async () => {
    const inner = createInMemoryTabTreeAdapter();
    let refuse = true;
    let loads = 0;
    const adapter: TabTreeAdapter = {
      ...inner,
      load: async (p, m) => {
        loads++;
        return inner.load(p, m);
      },
      save: async (p, m, s): Promise<SaveResult> =>
        refuse
          ? { status: "invalid", reason: "tab_tree_invalid", tab_id: "A", detail: "tab_id A is not 1-64 of [A-Za-z0-9_-]" }
          : inner.save(p, m, s),
    };
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    const shown = [vi.spyOn(toast, "info"), vi.spyOn(toast, "err"), vi.spyOn(toast, "warn")];
    tabs().setTabTreeAdapter(adapter);
    await tabs().ensureMothership("reading");
    expect(tabs().persistenceIssue).toBeNull();

    const before = Date.now();
    tabs().spawnTab("reading", null, { tab_id: "A", kind: "reader", ref: "doc-a", mothership: "reading" });
    await flush(20);
    // The existing handling still runs: logged, refetched, rebased, never shown.
    expect(error.mock.calls.flat().join(" ")).toContain("tab_id A is not 1-64 of [A-Za-z0-9_-]");
    expect(loads).toBe(2);
    expect(tabs().trees.reading!.nodes.A).toBeTruthy();
    for (const spy of shown) expect(spy).not.toHaveBeenCalled();
    // And now the refusal is state, not only a log line.
    const issue = tabs().persistenceIssue;
    expect(issue).toMatchObject({ reason: "refused", mothership: "reading" });
    expect(Date.parse(issue!.at)).toBeGreaterThanOrEqual(before - 1);

    refuse = false;
    tabs().spawnTab("reading", null, { tab_id: "B", kind: "reader", ref: "doc-b", mothership: "reading" });
    await flush(20);
    expect(tabs().persistenceIssue).toBeNull();
    const persisted = await inner.load("default", "reading");
    expect(Object.keys(persisted.tree.nodes).sort()).toEqual(["A", "B"]);
  });

  it("a 422 on the retry after a 409 is recorded too", async () => {
    const inner = createInMemoryTabTreeAdapter();
    let call = 0;
    const adapter: TabTreeAdapter = {
      ...inner,
      save: async (p, m): Promise<SaveResult> => {
        call++;
        if (call === 1) return { status: "conflict", reason: "version_stale", current: await inner.load(p, m) };
        return { status: "invalid", reason: "tab_tree_invalid", tab_id: null, detail: "tree too large" };
      },
    };
    vi.spyOn(console, "error").mockImplementation(() => {});
    tabs().setTabTreeAdapter(adapter);
    await tabs().ensureMothership("reading");
    tabs().spawnTab("reading", null, { tab_id: "A", kind: "reader", ref: "doc-a", mothership: "reading" });
    await flush(20);
    expect(call).toBe(2);
    expect(tabs().persistenceIssue).toMatchObject({ reason: "refused", mothership: "reading" });
  });

  it("a refusal of one tree survives another tree's refusal and acceptance", async () => {
    // Verifier finding (A2b repair 2): one shared slot let writing's 422
    // overwrite reading's, and writing's accepted save then cleared it, so
    // tabsSaved() said true while reading's tabs were not saved.
    const inner = createInMemoryTabTreeAdapter();
    const refuse: Record<string, boolean> = { reading: true, writing: true };
    const adapter: TabTreeAdapter = {
      ...inner,
      save: async (p, m, s): Promise<SaveResult> =>
        refuse[m]
          ? { status: "invalid", reason: "tab_tree_invalid", tab_id: null, detail: `${m} refused` }
          : inner.save(p, m, s),
    };
    vi.spyOn(console, "error").mockImplementation(() => {});
    await tabs().bindActiveProject(async () => "p1", () => adapter);
    expect(tabs().tabsPersistence).toBe("server");
    await tabs().ensureMothership("reading");
    await tabs().ensureMothership("writing");
    expect(tabsSaved(tabs())).toBe(true);

    tabs().spawnTab("reading", null, { tab_id: "R", kind: "reader", ref: "doc-r", mothership: "reading" });
    await flush(20);
    tabs().spawnTab("writing", null, { tab_id: "W", kind: "reader", ref: "doc-w", mothership: "writing" });
    await flush(20);
    expect(tabs().persistenceIssues.reading).toMatchObject({ reason: "refused", mothership: "reading" });
    expect(tabs().persistenceIssues.writing).toMatchObject({ reason: "refused", mothership: "writing" });

    refuse.writing = false;
    tabs().spawnTab("writing", null, { tab_id: "W2", kind: "reader", ref: "doc-w2", mothership: "writing" });
    await flush(20);
    expect(Object.keys((await inner.load("p1", "writing")).tree.nodes).sort()).toEqual(["W", "W2"]);
    expect(tabs().persistenceIssues.writing).toBeNull();
    // Reading's tabs are still not saved, and the store still says so.
    expect(Object.keys((await inner.load("p1", "reading")).tree.nodes)).toEqual([]);
    expect(tabs().persistenceIssues.reading).toMatchObject({ reason: "refused", mothership: "reading" });
    expect(tabs().persistenceIssue).toMatchObject({ mothership: "reading" });
    expect(tabsSaved(tabs())).toBe(false);

    refuse.reading = false;
    tabs().spawnTab("reading", null, { tab_id: "R2", kind: "reader", ref: "doc-r2", mothership: "reading" });
    await flush(20);
    expect(tabs().persistenceIssues.reading).toBeNull();
    expect(tabs().persistenceIssue).toBeNull();
    expect(tabsSaved(tabs())).toBe(true);
  });

  it("rebinding starts clean", async () => {
    const adapter: TabTreeAdapter = {
      ...createInMemoryTabTreeAdapter(),
      save: async (): Promise<SaveResult> => ({ status: "invalid", reason: "tab_tree_invalid", tab_id: null, detail: "x" }),
    };
    vi.spyOn(console, "error").mockImplementation(() => {});
    tabs().setTabTreeAdapter(adapter);
    await tabs().ensureMothership("reading");
    tabs().spawnTab("reading", null, { tab_id: "A", kind: "reader", ref: "doc-a", mothership: "reading" });
    await flush(20);
    expect(tabs().persistenceIssue).not.toBeNull();
    tabs().setTabTreeAdapter(createInMemoryTabTreeAdapter());
    expect(tabs().persistenceIssue).toBeNull();
  });
});

describe("GET /projects failures (A2b item 6)", () => {
  it("a network error is retried after 1 s, then 4 s: the third try binds to the server", async () => {
    vi.useFakeTimers();
    vi.spyOn(console, "error").mockImplementation(() => {});
    networkDown();
    networkDown();
    respond(200, { projects: [project("p1")] });
    let settled: string | null = null;
    void tabs().bindActiveProject().then((p) => (settled = p));
    await vi.advanceTimersByTimeAsync(0);
    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(999);
    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(apiFetchMock).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(3_999);
    expect(apiFetchMock).toHaveBeenCalledTimes(2);
    expect(settled).toBeNull();
    await vi.advanceTimersByTimeAsync(1);
    expect(apiFetchMock).toHaveBeenCalledTimes(3);
    await vi.advanceTimersByTimeAsync(0);
    expect(settled).toBe("server");
    expect(tabs().tabsPersistence).toBe("server");
    expect(tabs().projectId).toBe("p1");
  });

  it("three retries (1 s, 4 s, 15 s) then session, with no further tries", async () => {
    vi.useFakeTimers();
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    for (let i = 0; i < 4; i++) networkDown();
    let settled: string | null = null;
    void tabs().bindActiveProject().then((p) => (settled = p));
    await vi.advanceTimersByTimeAsync(1_000 + 4_000);
    expect(apiFetchMock).toHaveBeenCalledTimes(3);
    await vi.advanceTimersByTimeAsync(14_999);
    expect(apiFetchMock).toHaveBeenCalledTimes(3);
    expect(settled).toBeNull();
    await vi.advanceTimersByTimeAsync(1);
    expect(apiFetchMock).toHaveBeenCalledTimes(4);
    await vi.advanceTimersByTimeAsync(0);
    expect(settled).toBe("session");
    expect(tabs().tabsPersistence).toBe("session");
    await vi.advanceTimersByTimeAsync(120_000);
    expect(apiFetchMock).toHaveBeenCalledTimes(4);
    expect(error).toHaveBeenCalled();
  });

  it("a load waits for the retries, so the tree is read from the server once one succeeds", async () => {
    vi.useFakeTimers();
    vi.spyOn(console, "error").mockImplementation(() => {});
    networkDown();
    respond(200, { projects: [project("p1")] });
    respond(200, { tree: { nodes: {}, root_order: [] }, active: { left: null, right: null }, version: 5, next_child_index: {}, retired: [] });
    void tabs().bindActiveProject();
    const loading = tabs().ensureMothership("reading");
    await vi.advanceTimersByTimeAsync(1_000);
    await loading;
    expect(apiFetchMock.mock.calls[2][0]).toMatch(/\/projects\/p1\/tabs\/reading$/);
    expect(tabs().trees.reading!.version).toBe(5);
  });

  it("a 200 answering HTML (the SPA fallback) is the route being absent: session, no retry, nothing logged", async () => {
    vi.useFakeTimers();
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    const before = tabs().adapter;
    respondHtml();
    let settled: string | null = null;
    void tabs().bindActiveProject().then((p) => (settled = p));
    await vi.advanceTimersByTimeAsync(0);
    expect(settled).toBe("session");
    expect(tabs().tabsPersistence).toBe("session");
    expect(tabs().adapter).toBe(before);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(apiFetchMock).toHaveBeenCalledTimes(1);
    expect(error).not.toHaveBeenCalled();
  });
});

it("wrapped HTML fallback is absent, but malformed project JSON is diagnosed", async () => {
  const error = vi.spyOn(console, "error").mockImplementation(() => {});
  const html = vi.fn(async () => { throw new ApiError("invalid JSON", 0, "<!DOCTYPE html><html>SPA</html>"); });
  await tabs().bindActiveProject(html);
  expect(html).toHaveBeenCalledTimes(1);
  expect(error).not.toHaveBeenCalled();
  await tabs().bindActiveProject(async () => { throw new ApiError("malformed list", 0, '{"projects":false}'); });
  expect(error).toHaveBeenCalledTimes(1);
});
