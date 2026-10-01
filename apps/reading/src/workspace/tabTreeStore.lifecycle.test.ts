import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../lib/api";
import { createInMemoryTabTreeAdapter, emptyTabTree, spawnChild, toSnapshot, type TabTreeAdapter } from "./tabTree";
import { tabTreeHandle } from "./tabTreeHandle";
import { setTabOwner, suspendTabDispatch } from "./tabTreeOwner";
import { tabsSaved, useTabTrees } from "./tabTreeStore";

const tabs = () => useTabTrees.getState();
const drain = async () => { for (let i = 0; i < 100; i++) await Promise.resolve(); };
function deferred<T>() {
  let resolve: (value: T) => void = () => { throw new Error("not initialized"); };
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}
const spawn = (id: string) => tabs().spawnTab("reading", null, { tab_id: id, kind: "reader", ref: id, mothership: "reading" });
function snapshot(id: string, version = 0) {
  const spawned = spawnChild(emptyTabTree("reading", version), null, { tab_id: id, kind: "reader", ref: id, mothership: "reading" });
  if (!spawned.ok) throw new Error(spawned.error.message);
  return toSnapshot(spawned.tree);
}
async function bind(adapter: TabTreeAdapter) {
  await tabs().bindActiveProject(async () => "project-A", () => adapter);
  await tabs().ensureMothership("reading");
}
beforeEach(() => { setTabOwner(null); setTabOwner("owner-A"); tabs().resetTabTrees(); });
afterEach(() => { setTabOwner(null); tabs().resetTabTrees(); tabTreeHandle.bindOnLoad = false; vi.useRealTimers(); vi.restoreAllMocks(); });

describe("A2 binding, cancellation and retry boundaries", () => {
  it("replays tabs created before binding and initial load onto the server tree", async () => {
    const project = deferred<string | null>();
    const adapter = createInMemoryTabTreeAdapter();
    const binding = tabs().bindActiveProject(() => project.promise, () => adapter);
    spawn("pending");
    project.resolve("project-A"); await binding; await drain();
    expect(tabs().loaded.reading).toBe(true);
    expect(Object.keys((await adapter.load("project-A", "reading")).tree.nodes)).toEqual(["pending"]);
    expect(tabs().trees.reading!.nodes.pending.public_number).toBe(1);
    expect(tabsSaved(tabs())).toBe(true);
  });

  it("a session load that predates binding cannot replace the loaded server tree", async () => {
    const old = deferred<ReturnType<typeof toSnapshot>>();
    const session: TabTreeAdapter = { ...createInMemoryTabTreeAdapter(), load: () => old.promise };
    tabs().setTabTreeAdapter(session);
    const loading = tabs().ensureMothership("reading");
    const server = createInMemoryTabTreeAdapter();
    await server.save("project-A", "reading", snapshot("serverTab"));
    await tabs().bindActiveProject(async () => "project-A", () => server);
    await tabs().ensureMothership("reading");
    old.resolve(snapshot("obsoleteSession")); await loading;
    expect(Object.keys(tabs().trees.reading!.nodes)).toEqual(["serverTab"]);
  });

  it("a new project ignores late old PUTs and does not carry old project operations", async () => {
    const adapter = createInMemoryTabTreeAdapter(); const accepted = adapter.save;
    const gate = deferred<void>();
    vi.spyOn(adapter, "save").mockImplementationOnce(async (...args) => { await gate.promise; return accepted(...args); });
    await bind(adapter); spawn("old"); await drain(); spawn("oldPending");
    const next = createInMemoryTabTreeAdapter();
    await tabs().bindActiveProject(async () => "project-B", () => next);
    await tabs().ensureMothership("reading");
    spawn("new"); await drain(); gate.resolve(); await drain();
    expect(tabs().projectId).toBe("project-B");
    expect(Object.keys(tabs().trees.reading!.nodes)).toEqual(["new"]);
    expect(Object.keys((await next.load("project-B", "reading")).tree.nodes)).toEqual(["new"]);
    expect(tabs().pendingOps.reading).toEqual([]);
  });

  it("duplicate retry clicks during persistent contention share one bounded attempt sequence", async () => {
    vi.useFakeTimers();
    const adapter = createInMemoryTabTreeAdapter();
    const save = vi.spyOn(adapter, "save").mockResolvedValue({ status: "conflict", reason: "version_stale", current: toSnapshot(emptyTabTree("reading")) });
    await bind(adapter); spawn("pending"); await drain();
    tabs().retrySave("reading"); tabs().retrySave("reading"); tabs().retrySave("reading");
    await vi.advanceTimersByTimeAsync(1000); await drain();
    expect(save).toHaveBeenCalledTimes(3);
    expect(tabs().persistenceIssue?.reason).toBe("conflict");
    expect(tabs().trees.reading!.nodes.pending).toBeTruthy();
  });

  it("suspension invalidates a late load and same-owner resume loads again", async () => {
    const gate = deferred<ReturnType<typeof toSnapshot>>();
    const adapter = createInMemoryTabTreeAdapter();
    const load = vi.spyOn(adapter, "load").mockReturnValueOnce(gate.promise);
    await tabs().bindActiveProject(async () => "project-A", () => adapter);
    const loading = tabs().ensureMothership("reading"); await drain();
    suspendTabDispatch();
    gate.resolve(snapshot("late")); await loading;
    expect(tabs().trees.reading).toBeNull();
    setTabOwner("owner-A"); await tabs().ensureMothership("reading");
    expect(load).toHaveBeenCalledTimes(2);
    expect(tabs().loaded.reading).toBe(true);
    expect(tabs().trees.reading!.nodes).toEqual({});
  });

  it("closing an unnumbered tab during allocation retains the issued number through held Undo", async () => {
    const adapter = createInMemoryTabTreeAdapter(); const allocate = adapter.allocate;
    const gate = deferred<void>();
    vi.spyOn(adapter, "allocate").mockImplementationOnce(async (...args) => { await gate.promise; return allocate(...args); });
    await bind(adapter); spawn("held"); await drain();
    tabs().closeTabById("reading", "held", "prune");
    const closeId = tabs().heldClose!.token.close_id;
    gate.resolve(); await drain();
    tabs().undoClose(closeId); await drain();
    expect(tabs().trees.reading!.nodes.held.public_number).toBe(1);
    expect((await adapter.load("project-A", "reading")).tree.nodes.held.public_number).toBe(1);
    expect(tabsSaved(tabs())).toBe(true);
  });

  it("resuming with a held close keeps it hidden and preserves the original Undo deadline", async () => {
    vi.useFakeTimers();
    const adapter = createInMemoryTabTreeAdapter();
    await bind(adapter); spawn("held"); await drain();
    tabs().closeTabById("reading", "held", "prune");
    const held = tabs().heldClose;
    await vi.advanceTimersByTimeAsync(1000);
    suspendTabDispatch(); setTabOwner("owner-A"); await tabs().ensureMothership("reading");
    expect(tabs().trees.reading!.nodes.held).toBeUndefined();
    expect(tabs().heldClose?.expiresAt).toBe(held?.expiresAt);
    expect(tabs().heldClose?.token.close_id).toBe(held?.token.close_id);
    await vi.advanceTimersByTimeAsync(9000); await drain();
    expect(tabs().heldClose).toBeNull();
    expect((await adapter.load("project-A", "reading")).tree.nodes.held).toBeUndefined();
  });

  it("two conflicts followed by acceptance save without another user action", async () => {
    vi.useFakeTimers();
    const adapter = createInMemoryTabTreeAdapter(); const accepted = adapter.save;
    const conflict = { status: "conflict", reason: "version_stale", current: toSnapshot(emptyTabTree("reading")) } as const;
    const save = vi.spyOn(adapter, "save").mockResolvedValueOnce(conflict).mockResolvedValueOnce(conflict).mockImplementation(accepted);
    await bind(adapter); spawn("pending"); await vi.advanceTimersByTimeAsync(100); await drain();
    expect(save).toHaveBeenCalledTimes(3);
    expect(tabsSaved(tabs())).toBe(true);
    expect((await adapter.load("project-A", "reading")).tree.nodes.pending).toBeTruthy();
  });

  it("a project lookup that finds no current project revokes the old HTTP binding", async () => {
    const adapter = createInMemoryTabTreeAdapter();
    await bind(adapter); spawn("old"); await drain();
    const writes = vi.spyOn(adapter, "save");
    await tabs().bindActiveProject(async () => null);
    await tabs().ensureMothership("reading"); spawn("session"); await drain();
    expect(tabs().tabsPersistence).toBe("session");
    expect(tabs().adapter).not.toBe(adapter);
    expect(Object.keys(tabs().trees.reading!.nodes)).toEqual(["session"]);
    expect(writes).not.toHaveBeenCalled();
  });

  it("a failed project lookup preserves the existing binding and unsaved work", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const adapter = createInMemoryTabTreeAdapter();
    await bind(adapter);
    vi.spyOn(adapter, "save").mockRejectedValue(new Error("offline"));
    spawn("pending"); await drain();
    await tabs().bindActiveProject(async () => { throw new ApiError("project lookup failed", 503, ""); });
    expect(tabs().projectId).toBe("project-A");
    expect(tabs().adapter).toBe(adapter);
    expect(tabs().trees.reading!.nodes.pending).toBeTruthy();
    expect(tabs().pendingOps.reading.length).toBeGreaterThan(0);
    expect(tabsSaved(tabs())).toBe(false);
  });
});
