import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { parseTabsSnapshot, type TabsSnapshot } from "../lib/api/projectTabs";
import { createInMemoryTabTreeAdapter, emptyTabTree, spawnChild, toSnapshot } from "./tabTree";
import { setTabOwner } from "./tabTreeOwner";
import { tabsSaved, useTabTrees } from "./tabTreeStore";
import { toWireSnapshot } from "./tabTreeWire";

const tabs = () => useTabTrees.getState();
const drain = async () => { for (let i = 0; i < 160; i++) await Promise.resolve(); };
const spawn = (tab_id: string) => tabs().spawnTab("reading", null, { tab_id, kind: "reader", ref: tab_id, mothership: "reading" });
function deferred() {
  let resolve: () => void = () => { throw new Error("not initialized"); };
  const promise = new Promise<void>((done) => { resolve = done; });
  return { promise, resolve };
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

beforeEach(() => { setTabOwner(null); setTabOwner("race-owner"); tabs().resetTabTrees(); });
afterEach(() => { setTabOwner(null); tabs().resetTabTrees(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it.each(["allocation", "conflict"] as const)("allocates a spawn made during the first %s await before its first accepted HTTP snapshot", async (boundary) => {
  const legacy = spawnChild(emptyTabTree("reading"), null, { tab_id: "legacy", kind: "reader", ref: "legacy", mothership: "reading" });
  if (!legacy.ok) throw new Error(legacy.error.message);
  let row = toWireSnapshot(legacy.tree);
  const gate = deferred();
  const requestedIds: string[] = [];
  const registered = new Map<string, number>();
  const putAttempts: TabsSnapshot[] = [];
  const fetcher = vi.fn<typeof fetch>(async (input, init) => {
    if (String(input).endsWith("/allocate")) {
      const body: unknown = JSON.parse(String(init?.body));
      if (!body || typeof body !== "object" || !("tab_id" in body) || typeof body.tab_id !== "string") throw new Error("bad allocation body");
      requestedIds.push(body.tab_id);
      if (boundary === "allocation" && requestedIds.length === 1) await gate.promise;
      const number = registered.get(body.tab_id) ?? registered.size + 1;
      registered.set(body.tab_id, number);
      return json({ public_number: number });
    }
    if (init?.method === "PUT") {
      const body: unknown = JSON.parse(String(init.body));
      if (!body || typeof body !== "object" || !("tree" in body) || !("active" in body) || !("expected_version" in body)) throw new Error("bad PUT body");
      const proposed = parseTabsSnapshot({ ...row, tree: body.tree, active: body.active });
      putAttempts.push(proposed);
      if (boundary === "conflict" && putAttempts.length === 1) {
        await gate.promise;
        row = { ...row, version: row.version + 1 };
        return json({ reason: "version_stale", current: row }, 409);
      }
      expect(body.expected_version).toBe(row.version);
      // Backend pin 1e30fff2b631: null is accepted when unregistered and
      // filled only when allocate already registered this exact tab ID.
      for (const node of Object.values(proposed.tree.nodes)) {
        if (node.public_number === null) node.public_number = registered.get(node.tab_id) ?? null;
        else expect(node.public_number).toBe(registered.get(node.tab_id));
      }
      row = {
        ...proposed,
        version: row.version + 1,
        next_child_index: { root: Math.max(row.next_child_index.root ?? 1, ...Object.values(proposed.tree.nodes).map((node) => Number(node.hier_number) + 1)) },
      };
      return json(row);
    }
    return json(row);
  });
  vi.stubGlobal("fetch", fetcher);
  await tabs().bindActiveProject(async () => "race-project");
  await tabs().ensureMothership("reading");
  expect(spawn("A").ok).toBe(true);
  await drain();
  expect(requestedIds).toEqual(["A"]);
  expect(putAttempts).toHaveLength(boundary === "conflict" ? 1 : 0);
  expect(spawn("B").ok).toBe(true);
  expect(tabsSaved(tabs())).toBe(false);
  gate.resolve();
  await drain();
  expect(requestedIds).toEqual(["A", "B"]);
  expect(row.tree.nodes.A.public_number).toBe(1);
  expect(row.tree.nodes.B.public_number).toBe(2);
  expect(row.tree.nodes.legacy.public_number).toBeNull();
  expect(putAttempts.filter((snapshot) => snapshot.tree.nodes.B).every((snapshot) => snapshot.tree.nodes.B.public_number === 2)).toBe(true);
  expect(tabs().pendingOps.reading).toEqual([]);
  expect(tabsSaved(tabs())).toBe(true);
  tabs().resetTabTrees();
  await tabs().bindActiveProject(async () => "race-project");
  await tabs().ensureMothership("reading");
  expect(tabs().trees.reading?.nodes.B.public_number).toBe(2);
  expect(tabs().trees.reading?.nodes.legacy.public_number).toBeNull();
  expect(requestedIds).toEqual(["A", "B"]);
});

it("keeps a spawn made during retry allocation pending through a held close and Undo", async () => {
  const adapter = createInMemoryTabTreeAdapter();
  const firstPut = deferred();
  const retryAllocation = deferred();
  const originalAllocate = adapter.allocate;
  const allocate = vi.spyOn(adapter, "allocate").mockImplementation(async (...args) => {
    if (args[2] === "B") await retryAllocation.promise;
    return originalAllocate(...args);
  });
  const originalSave = adapter.save;
  const save = vi.spyOn(adapter, "save").mockImplementationOnce(async () => {
    await firstPut.promise;
    return { status: "conflict", reason: "version_stale", current: toSnapshot(emptyTabTree("reading")) };
  }).mockImplementation(originalSave);
  await tabs().bindActiveProject(async () => "race-project", () => adapter);
  await tabs().ensureMothership("reading");
  spawn("A"); await drain();
  expect(save).toHaveBeenCalledTimes(1);
  spawn("B");
  tabs().closeTabById("reading", "A", "prune");
  const held = tabs().heldClose;
  expect(held).not.toBeNull();
  firstPut.resolve(); await drain();
  expect(allocate.mock.calls.map((call) => call[2])).toEqual(["A", "B"]);
  spawn("C");
  retryAllocation.resolve(); await drain();
  expect(save).toHaveBeenCalledTimes(2);
  expect(save.mock.calls[1][2].tree.nodes.A.public_number).toBe(1);
  expect(save.mock.calls[1][2].tree.nodes.B.public_number).toBe(2);
  expect(save.mock.calls[1][2].tree.nodes.C).toBeUndefined();
  expect(tabs().trees.reading?.nodes.A).toBeUndefined();
  expect(tabs().trees.reading?.nodes.C.public_number).toBeNull();
  expect(tabs().heldClose?.expiresAt).toBe(held?.expiresAt);
  expect(tabsSaved(tabs())).toBe(false);
  if (!held) throw new Error("held close missing");
  tabs().undoClose(held.token.close_id); await drain();
  expect(allocate.mock.calls.map((call) => call[2])).toEqual(["A", "B", "C"]);
  expect(save).toHaveBeenCalledTimes(3);
  const accepted = await adapter.load("race-project", "reading");
  expect(accepted.tree.nodes.A.public_number).toBe(1);
  expect(accepted.tree.nodes.B.public_number).toBe(2);
  expect(accepted.tree.nodes.C.public_number).toBe(3);
  expect(tabs().pendingOps.reading).toEqual([]);
  expect(tabsSaved(tabs())).toBe(true);
});
