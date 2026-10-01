import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createInMemoryTabTreeAdapter, toSnapshot, emptyTabTree } from "./tabTree";
import { useTabTrees, tabsSaved } from "./tabTreeStore";
import { setTabOwner, suspendTabDispatch } from "./tabTreeOwner";
import { tabTreeHandle } from "./tabTreeHandle";
const tabs = () => useTabTrees.getState();
const drain = async () => { for (let i = 0; i < 60; i++) await Promise.resolve(); };
const spawn = (id: string) => tabs().spawnTab("reading", null, { tab_id: id, kind: "reader", ref: id, mothership: "reading" });
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>((r) => { resolve = r; }); return { resolve, promise }; }
beforeEach(() => { setTabOwner(null); setTabOwner("owner-A"); tabs().resetTabTrees(); });
afterEach(() => { setTabOwner(null); tabs().resetTabTrees(); tabTreeHandle.bindOnLoad = false; vi.useRealTimers(); vi.restoreAllMocks(); });
async function bind(adapter = createInMemoryTabTreeAdapter()) {
  await tabs().bindActiveProject(async () => "project-A", () => adapter);
  await tabs().ensureMothership("reading");
  return adapter;
}

describe("A2 actual store dispatch", () => {
  it("allocates new IDs once and never announces saved while a write is outstanding", async () => {
    const adapter = createInMemoryTabTreeAdapter();
    const allocate = vi.spyOn(adapter, "allocate");
    const original = adapter.save;
    const gate = deferred<void>();
    vi.spyOn(adapter, "save").mockImplementationOnce(async (...args) => { await gate.promise; return original(...args); });
    await bind(adapter);
    spawn("first"); expect(tabsSaved(tabs())).toBe(false);
    await drain(); expect(tabsSaved(tabs())).toBe(false);
    expect(allocate).toHaveBeenCalledExactlyOnceWith("project-A", "reading", "first", expect.any(AbortSignal));
    gate.resolve(); await drain(); expect(tabsSaved(tabs())).toBe(true);
    spawn("second"); await drain();
    expect(allocate.mock.calls.map((call) => call[2])).toEqual(["first", "second"]);
    expect(tabs().trees.reading!.nodes.first.public_number).toBe(1);
    expect(tabs().trees.reading!.nodes.second.public_number).toBe(2);
    tabs().closeTabById("reading", "second", "prune");
    expect(tabsSaved(tabs())).toBe(false);
  });
  it("retries a lost allocate answer with the same ID and restores honest status after transport failure", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const adapter = createInMemoryTabTreeAdapter(); const original = adapter.allocate;
    const allocate = vi.spyOn(adapter, "allocate").mockImplementationOnce(async (...args) => { await original(...args); throw new Error("lost answer"); });
    await bind(adapter); spawn("first"); await drain();
    expect(tabsSaved(tabs())).toBe(false);
    expect(tabs().persistenceIssue?.reason).toBe("transport");
    tabs().retrySave("reading"); await drain();
    expect(allocate.mock.calls.map((call) => call[2])).toEqual(["first", "first"]);
    expect(tabs().trees.reading!.nodes.first.public_number).toBe(1);
    expect(tabsSaved(tabs())).toBe(true);
  });
  it("suspension keeps drafts and stops follow-up requests until the same owner confirms", async () => {
    const adapter = createInMemoryTabTreeAdapter(); const original = adapter.save;
    const gate = deferred<void>(); const save = vi.spyOn(adapter, "save").mockImplementationOnce(async (...args) => { await gate.promise; return original(...args); });
    const allocate = vi.spyOn(adapter, "allocate");
    await bind(adapter); spawn("first"); await drain();
    suspendTabDispatch(); spawn("second"); gate.resolve(); await drain();
    expect(save).toHaveBeenCalledTimes(1); expect(allocate).toHaveBeenCalledTimes(1);
    expect(tabs().trees.reading!.nodes.second).toBeTruthy(); expect(tabsSaved(tabs())).toBe(false);
    setTabOwner("owner-A"); await drain();
    expect(save).toHaveBeenCalledTimes(2); expect(allocate).toHaveBeenCalledTimes(2);
    expect(tabsSaved(tabs())).toBe(true);
  });
  it.each([null, "owner-B"])("revoking owner to %s discards old pending follow-up before a late response", async (owner) => {
    const adapter = createInMemoryTabTreeAdapter(); const original = adapter.save;
    const gate = deferred<void>(); const save = vi.spyOn(adapter, "save").mockImplementationOnce(async (...args) => { await gate.promise; return original(...args); });
    await bind(adapter); spawn("first"); await drain(); spawn("second");
    setTabOwner(owner); gate.resolve(); await drain();
    expect(save).toHaveBeenCalledTimes(1);
    expect(tabs().trees.reading).toBeNull(); expect(tabs().projectId).toBeNull();
    expect(tabs().pendingOps.reading).toEqual([]);
  });
  it("does not install a project selected by an obsolete owner", async () => {
    const gate = deferred<string | null>(); const adapter = createInMemoryTabTreeAdapter();
    const binding = tabs().bindActiveProject(() => gate.promise, () => adapter);
    setTabOwner("owner-B"); gate.resolve("old-project"); await binding;
    expect(tabs().projectId).toBeNull(); expect(tabs().adapter).not.toBe(adapter);
  });
  it("stops permanent contention after three attempts and exposes a retry that retains the spawn", async () => {
    vi.useFakeTimers();
    const adapter = createInMemoryTabTreeAdapter(); const original = adapter.save;
    const save = vi.spyOn(adapter, "save").mockResolvedValue({ status: "conflict", reason: "version_stale", current: toSnapshot(emptyTabTree("reading")) });
    await bind(adapter); spawn("first"); await vi.advanceTimersByTimeAsync(101); await drain();
    expect(save).toHaveBeenCalledTimes(3); expect(tabs().persistenceIssue?.reason).toBe("conflict");
    expect(tabsSaved(tabs())).toBe(false); expect(tabs().trees.reading!.nodes.first).toBeTruthy();
    save.mockImplementation(original); tabs().retrySave("reading"); await drain();
    expect(tabsSaved(tabs())).toBe(true);
  });
  it("late allocation cannot put an old tab into the next owner's project", async () => {
    const adapter = createInMemoryTabTreeAdapter(); const gate = deferred<{ public_number: number }>();
    vi.spyOn(adapter, "allocate").mockReturnValue(gate.promise); const save = vi.spyOn(adapter, "save");
    await bind(adapter); spawn("oldTab"); await drain(); setTabOwner("owner-B");
    gate.resolve({ public_number: 12 }); await drain();
    expect(save).not.toHaveBeenCalled(); expect(tabs().trees.reading).toBeNull();
  });
});
