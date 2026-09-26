/**
 * tabTreeStore.persistence.test.ts — A2a items 4 and 6 at the store:
 *  - a saved PUT's snapshot is adopted (numbers, version and retired come
 *    from the server), ops made in flight replayed on top;
 *  - both 409 reasons rebase the same way; a 422 is logged with its detail,
 *    refetched and rebased, and never shown to the operator;
 *  - the trees bind to the active project (an injectable getter, default the
 *    first non-archived project from GET /projects), and a 404 on
 *    GET /projects keeps the in-memory adapter with `tabsPersistence:
 *    "session"`;
 *  - tab state never reaches localStorage or sessionStorage.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { toast } from "../components/lemon/LemonToast";
import { ApiError } from "../lib/api";
import {
  createInMemoryTabTreeAdapter,
  fromSnapshot,
  toSnapshot,
  type SaveResult,
  type TabTreeAdapter,
  type TabTreeSnapshot,
} from "./tabTree";
import { firstOpenProject, useTabTrees } from "./tabTreeStore";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", async (orig) => {
  const actual = await orig<typeof import("../lib/api")>();
  return { ...actual, apiFetch: apiFetchMock };
});

const tabs = () => useTabTrees.getState();
const flush = async (n = 8) => {
  for (let i = 0; i < n; i++) await new Promise((r) => setTimeout(r, 0));
};

function respond(status: number, body: unknown) {
  apiFetchMock.mockResolvedValueOnce({
    ok: status >= 200 && status < 300,
    status,
    json: async () => JSON.parse(JSON.stringify(body)),
    text: async () => JSON.stringify(body),
  });
}

function project(id: string, archived: string | null = null) {
  return {
    project_id: id,
    title: id,
    kind: "project",
    order: 0,
    pinned: false,
    archived_at: archived,
    primary_document_id: null,
    created_at: "2026-09-27T00:00:00Z",
    updated_at: null,
    member_count: 0,
  };
}

const emptyWire = (version = 0) => ({
  tree: { nodes: {}, root_order: [] },
  active: { left: null, right: null },
  version,
  next_child_index: {},
  retired: [],
});

beforeEach(() => {
  apiFetchMock.mockReset();
  tabs().resetTabTrees();
});
afterEach(() => {
  vi.restoreAllMocks();
  tabs().resetTabTrees();
});

describe("the store adopts the server's answer (A2a item 4)", () => {
  it("a saved PUT hands back the server snapshot: its version and numbers replace the local ones", async () => {
    const inner = createInMemoryTabTreeAdapter();
    const adapter: TabTreeAdapter = {
      ...inner,
      async save(p, m, snap): Promise<SaveResult> {
        const r = await inner.save(p, m, snap);
        if (r.status !== "saved") return r;
        const server = JSON.parse(JSON.stringify(r.snapshot)) as TabTreeSnapshot;
        server.version = 41;
        for (const node of Object.values(server.tree.nodes)) node.public_number ??= 9;
        return { status: "saved", snapshot: server };
      },
    };
    tabs().setTabTreeAdapter(adapter);
    await tabs().ensureMothership("reading");
    tabs().spawnTab("reading", null, { tab_id: "A", kind: "reader", ref: "doc-a", mothership: "reading" });
    await flush();
    const tree = tabs().trees.reading!;
    expect(tree.version).toBe(41);
    expect(tree.nodes.A.public_number).toBe(9);
    expect(tabs().pendingOps.reading).toEqual([]);
  });

  it("a number_conflict rebases like a version_stale: the local spawn survives, renumbered", async () => {
    const inner = createInMemoryTabTreeAdapter();
    let first = true;
    const adapter: TabTreeAdapter = {
      ...inner,
      async save(p, m, snap): Promise<SaveResult> {
        if (first) {
          first = false;
          // Another device's spawn took hier "1" first.
          const other = await inner.load(p, m);
          const t = fromSnapshot(other);
          if (!t.ok) throw new Error(t.error.message);
          const spawned = (await import("./tabTree")).spawnChild(t.tree, null, {
            tab_id: "other", kind: "reader", ref: "doc-o", mothership: m,
          });
          if (!spawned.ok) throw new Error(spawned.error.message);
          await inner.save(p, m, toSnapshot(spawned.tree));
          return { status: "conflict", reason: "number_conflict", tab_id: "A", detail: "1 belongs to other", current: await inner.load(p, m) };
        }
        return inner.save(p, m, snap);
      },
    };
    const info = vi.spyOn(toast, "info");
    tabs().setTabTreeAdapter(adapter);
    await tabs().ensureMothership("reading");
    tabs().spawnTab("reading", null, { tab_id: "A", kind: "reader", ref: "doc-a", mothership: "reading" });
    await flush();
    const tree = tabs().trees.reading!;
    expect(tree.nodes.other.hier_number).toBe("1");
    expect(tree.nodes.A.hier_number).toBe("2");
    const persisted = await inner.load("default", "reading");
    expect(Object.keys(persisted.tree.nodes).sort()).toEqual(["A", "other"]);
    expect(info).not.toHaveBeenCalled();
  });

  it("a 422 is logged with its detail, refetched and rebased, and never shown", async () => {
    const inner = createInMemoryTabTreeAdapter();
    let loads = 0;
    const adapter: TabTreeAdapter = {
      ...inner,
      load: async (p, m) => {
        loads++;
        return inner.load(p, m);
      },
      save: async (): Promise<SaveResult> => ({
        status: "invalid",
        reason: "tab_tree_invalid",
        tab_id: "A",
        detail: "tab_id A is not 1-64 of [A-Za-z0-9_-]",
      }),
    };
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    const shown = [vi.spyOn(toast, "info"), vi.spyOn(toast, "err"), vi.spyOn(toast, "warn")];
    tabs().setTabTreeAdapter(adapter);
    await tabs().ensureMothership("reading");
    expect(loads).toBe(1);
    tabs().spawnTab("reading", null, { tab_id: "A", kind: "reader", ref: "doc-a", mothership: "reading" });
    await flush();
    expect(loads).toBe(2);
    expect(error.mock.calls.flat().join(" ")).toContain("tab_id A is not 1-64 of [A-Za-z0-9_-]");
    for (const spy of shown) expect(spy).not.toHaveBeenCalled();
    // Rebased onto the refetched tree: the local spawn is still there.
    expect(tabs().trees.reading!.nodes.A).toBeTruthy();
  });

  it("a save that throws (network) keeps the pending ops for the next write", async () => {
    const inner = createInMemoryTabTreeAdapter();
    let fail = true;
    const adapter: TabTreeAdapter = {
      ...inner,
      save: async (p, m, s) => {
        if (fail) throw new Error("network down");
        return inner.save(p, m, s);
      },
    };
    vi.spyOn(console, "error").mockImplementation(() => {});
    tabs().setTabTreeAdapter(adapter);
    await tabs().ensureMothership("reading");
    tabs().spawnTab("reading", null, { tab_id: "A", kind: "reader", ref: "doc-a", mothership: "reading" });
    await flush();
    expect(tabs().pendingOps.reading).toHaveLength(1);
    fail = false;
    tabs().spawnTab("reading", null, { tab_id: "B", kind: "reader", ref: "doc-b", mothership: "reading" });
    await flush();
    const persisted = await inner.load("default", "reading");
    expect(Object.keys(persisted.tree.nodes).sort()).toEqual(["A", "B"]);
    expect(tabs().pendingOps.reading).toEqual([]);
  });
});

describe("binding to the active project (A2a item 6)", () => {
  it("defaults to session persistence on the in-memory adapter", () => {
    expect(tabs().tabsPersistence).toBe("session");
    expect(tabs().projectId).toBeNull();
  });

  it("binds the trees to the active project's server row", async () => {
    await tabs().bindActiveProject(async () => "fld-7");
    expect(tabs().tabsPersistence).toBe("server");
    expect(tabs().projectId).toBe("fld-7");
    respond(200, emptyWire(3));
    await tabs().ensureMothership("research");
    expect(apiFetchMock.mock.calls[0][0]).toMatch(/\/projects\/fld-7\/tabs\/research$/);
    expect(tabs().trees.research!.version).toBe(3);

    const t1 = {
      tab_id: "t-1", parent_tab_id: null, side: "left", kind: "reader", ref: "doc-1", title: "",
      mothership: "research", public_number: 12, hier_number: "1", child_order: [],
    };
    respond(200, { ...emptyWire(4), tree: { nodes: { "t-1": t1 }, root_order: ["t-1"] }, active: { left: "t-1", right: null }, next_child_index: { root: 2 } });
    tabs().spawnTab("research", null, { tab_id: "t-1", kind: "reader", ref: "doc-1", mothership: "research" });
    await flush();
    const [url, init] = apiFetchMock.mock.calls[1];
    expect(url).toMatch(/\/projects\/fld-7\/tabs\/research$/);
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string).expected_version).toBe(3);
    expect(tabs().trees.research!.version).toBe(4);
    expect(tabs().trees.research!.nodes["t-1"].public_number).toBe(12);
  });

  it("a load waits for a binding in flight, so no tree is read from the wrong adapter", async () => {
    let release: (id: string | null) => void = () => {};
    const bound = tabs().bindActiveProject(() => new Promise((r) => (release = r)));
    const loading = tabs().ensureMothership("reading");
    expect(apiFetchMock).not.toHaveBeenCalled();
    respond(200, emptyWire(1));
    release("fld-2");
    await bound;
    await loading;
    expect(apiFetchMock.mock.calls[0][0]).toMatch(/\/projects\/fld-2\/tabs\/reading$/);
    expect(tabs().trees.reading!.version).toBe(1);
  });

  it("GET /projects answering 404 keeps the in-memory adapter: session persistence", async () => {
    const before = tabs().adapter;
    respond(404, { detail: "Not Found" });
    await tabs().bindActiveProject();
    expect(tabs().tabsPersistence).toBe("session");
    expect(tabs().adapter).toBe(before);
    expect(tabs().projectId).toBeNull();
  });

  it("no project to bind to also stays session", async () => {
    await tabs().bindActiveProject(async () => null);
    expect(tabs().tabsPersistence).toBe("session");
  });

  it("the default getter picks the first non-archived project, else null", async () => {
    respond(200, { projects: [project("old", "2026-09-01T00:00:00Z"), project("live"), project("later")] });
    await expect(firstOpenProject()).resolves.toBe("live");
    respond(200, { projects: [project("old", "2026-09-01T00:00:00Z")] });
    await expect(firstOpenProject()).resolves.toBeNull();
    respond(404, { detail: "Not Found" });
    await expect(firstOpenProject()).rejects.toBeInstanceOf(ApiError);
  });

  it("server-bound tabs never touch localStorage or sessionStorage", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const getItem = vi.spyOn(Storage.prototype, "getItem");
    await tabs().bindActiveProject(async () => "fld-7");
    respond(200, emptyWire(0));
    await tabs().ensureMothership("reading");
    respond(200, emptyWire(1));
    tabs().spawnTab("reading", null, { tab_id: "t-1", kind: "reader", ref: "doc-1", mothership: "reading" });
    await flush();
    expect(setItem).not.toHaveBeenCalled();
    expect(getItem).not.toHaveBeenCalled();
  });
});
