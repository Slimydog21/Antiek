import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "../components/lemon/LemonToast";
import { checkInvariants, closeTab, createInMemoryTabTreeAdapter, emptyTabTree, fromSnapshot, rebase, restoreClosed, spawnChild, toSnapshot, undo, type TabTree, type TabTreeAdapter, type TabTreeResult } from "./tabTree";
import { useTabTrees } from "./tabTreeStore";
function must<T>(result: TabTreeResult<T>): T { if (!result.ok) throw new Error(result.error.message); return result; }
function spawn(tree: TabTree, parent: string | null, id: string): TabTree { return must(spawnChild(tree, parent, { tab_id: id, ref: id, kind: "reader", mothership: "reading" })).tree; }
function base(): TabTree { return spawn(spawn(spawn(emptyTabTree("reading"), null, "R"), "R", "P"), "P", "seen"); }
const tabs = () => useTabTrees.getState();
async function drain(): Promise<void> { for (let i = 0; i < 30; i++) await Promise.resolve(); }
beforeEach(() => { tabs().resetTabTrees(); });
afterEach(() => { tabs().resetTabTrees(); vi.useRealTimers(); vi.restoreAllMocks(); });
describe("signed §2.2 restore and rebase", () => {
  it("keeps each retired node's timestamp and provenance in the restore PUT", () => {
    const closed = must(closeTab(base(), "P", "prune", "2026-09-27T10:00:00Z")).tree;
    const restored = must(restoreClosed(closed, "P"));
    const snapshot = toSnapshot(restored.tree);
    for (const id of ["P", "seen"]) expect(snapshot.tree.nodes[id]).toEqual(closed.history[id].node);
    expect(checkInvariants(restored.tree)).toEqual([]);
  });
  it("the server stand-in accepts a retired timestamp, clears it, and rejects a forged restore", async () => {
    const adapter = createInMemoryTabTreeAdapter();
    const closed = must(closeTab(base(), "P", "prune", "t1")).tree;
    expect((await adapter.save("default", "reading", toSnapshot(closed))).status).toBe("saved");
    const remote = must(fromSnapshot(await adapter.load("default", "reading"))).tree;
    const restored = must(restoreClosed(remote, "P")).tree;
    const forged = toSnapshot(restored);
    forged.tree.nodes.P.ref = "different-document";
    expect((await adapter.save("default", "reading", forged)).status).toBe("rejected");
    expect((await adapter.save("default", "reading", toSnapshot(restored))).status).toBe("saved");
    const saved = await adapter.load("default", "reading");
    expect(saved.tree.nodes.P.pruned_at).toBeUndefined();
    expect(saved.tree.nodes.seen.pruned_at).toBeUndefined();
  });
  it("after the hold expires the store restores with pruned_at once, then stops sending it", async () => {
    vi.useFakeTimers();
    const adapter = createInMemoryTabTreeAdapter();
    await adapter.save("default", "reading", toSnapshot(base()));
    const save = vi.spyOn(adapter, "save");
    tabs().setTabTreeAdapter(adapter);
    await tabs().ensureMothership("reading");
    tabs().closeTabById("reading", "P", "prune");
    await vi.advanceTimersByTimeAsync(10_001); await drain();
    const retired = tabs().trees.reading!.history.P.node;
    save.mockClear();
    expect(tabs().undoLastClose("reading")).toBe(true); await drain();
    expect(save.mock.calls[0][2].tree.nodes.P.pruned_at).toBe(retired.pruned_at);
    expect(tabs().trees.reading!.nodes.P.pruned_at).toBeUndefined();
    tabs().activateTab("reading", "R"); await drain();
    expect(save.mock.calls.at(-1)![2].tree.nodes.P.pruned_at).toBeUndefined();
  });
  it.each(["P", "R"])("pruning %s lifts unseen remote subtrees and preserves their numbers and focus", (target) => {
    const local = must(closeTab(base(), target, "prune", "t1"));
    const remote = spawn(spawn(base(), "seen", "new"), "new", "grandchild");
    const rebased = rebase(remote, [local.op]);
    expect(rebased.tree.nodes.new?.parent_tab_id).toBe(target === "P" ? "R" : null);
    expect(rebased.tree.nodes.new?.hier_number).toBe(remote.nodes.new.hier_number);
    expect(rebased.tree.nodes.grandchild).toEqual(remote.nodes.grandchild);
    expect(rebased.tree.active_tab_id).toBe("grandchild");
    expect(Object.keys(rebased.tree.history).sort()).toEqual(target === "P" ? ["P", "seen"] : ["P", "R", "seen"]);
    expect(checkInvariants(rebased.tree)).toEqual([]);
    const undone = rebase(remote, [local.op, must(undo(local.tree, local.undo)).op]);
    expect(undone.tree.nodes.new.parent_tab_id).toBe(target === "P" ? "R" : null);
    expect(checkInvariants(undone.tree)).toEqual([]);
  });
  async function conflict(local: TabTree, remote: TabTree, action: () => void) {
    const info = vi.spyOn(toast, "info"); let calls = 0;
    const adapter: TabTreeAdapter = {
      load: async () => toSnapshot(local),
      save: async () => ++calls === 1 ? { status: "conflict", current: toSnapshot(remote) } : { status: "saved", version: 2 },
      allocate: async () => ({ public_number: 1 }),
    };
    tabs().setTabTreeAdapter(adapter); await tabs().ensureMothership("reading"); action(); await drain(); return info;
  }
  it("names the actual destination when a spawn's parent closed remotely", async () => {
    const remote = must(closeTab(base(), "P", "prune", "t1")).tree;
    const info = await conflict(base(), remote, () => tabs().spawnTab("reading", "P", { tab_id: "local", ref: "local", kind: "reader", mothership: "reading" }));
    expect(info).toHaveBeenCalledWith("Moved under 1: its parent was closed on another device");
  });
  it("a duplicate spawn is not reported as a remote close", async () => {
    const info = await conflict(base(), spawn(base(), "R", "duplicate"), () => tabs().spawnTab("reading", "R", { tab_id: "duplicate", ref: "duplicate", kind: "reader", mothership: "reading" }));
    expect(info).toHaveBeenCalledWith("A tab already exists on another device; your other changes were kept.");
    expect(info).not.toHaveBeenCalledWith("A tab was closed on another device; your other changes were kept.");
  });
  it("undoing a superseded close that has not reached the server sends no restore marker", async () => {
    vi.useFakeTimers();
    const adapter = createInMemoryTabTreeAdapter();
    await adapter.save("default", "reading", toSnapshot(base()));
    const save = vi.spyOn(adapter, "save");
    tabs().setTabTreeAdapter(adapter); await tabs().ensureMothership("reading");
    tabs().closeTabById("reading", "seen", "prune");
    const closeId = tabs().heldClose!.token.close_id;
    tabs().closeTabById("reading", "P", "lift_children");
    tabs().undoClose(closeId);
    await vi.advanceTimersByTimeAsync(10_001); await drain();
    expect(save.mock.calls.at(-1)![2].tree.nodes.seen.pruned_at).toBeUndefined();
    expect((await adapter.load("default", "reading")).tree.nodes.seen).toBeTruthy();
    expect(tabs().pendingOps.reading).toEqual([]);
  });

  it("an old save acknowledgment cannot change a reset context", async () => {
    let finish!: (value: { status: "saved"; version: number }) => void;
    const adapter: TabTreeAdapter = {
      load: async () => toSnapshot(base()),
      save: () => new Promise((resolve) => { finish = resolve; }),
      allocate: async () => ({ public_number: 1 }),
    };
    tabs().setTabTreeAdapter(adapter); await tabs().ensureMothership("reading");
    tabs().activateTab("reading", "R"); await drain();
    tabs().setTabTreeAdapter(adapter); await tabs().ensureMothership("reading");
    finish({ status: "saved", version: 99 }); await drain();
    expect(tabs().trees.reading!.version).toBe(0);
  });

  it("saves a restore after two conflicts with no follow-up trigger (CR-F3 bounded retry)", async () => {
    const closed = must(closeTab(base(), "P", "prune", "t1")).tree;
    let calls = 0;
    const adapter: TabTreeAdapter = {
      load: async () => toSnapshot(closed),
      save: async () => ++calls <= 2
        ? { status: "conflict", current: toSnapshot(closed) }
        : { status: "saved", version: 1 },
      allocate: async () => ({ public_number: 1 }),
    };
    const save = vi.spyOn(adapter, "save");
    tabs().setTabTreeAdapter(adapter); await tabs().ensureMothership("reading");
    tabs().undoLastClose("reading"); await drain();
    // Two conflicts, then the bounded third attempt succeeds — WITHOUT the
    // old follow-up trigger (activateTab) the base needed to force a save.
    expect(save.mock.calls.length).toBeGreaterThanOrEqual(3);
    expect(tabs().pendingOps.reading).toEqual([]);
    expect(tabs().trees.reading!.nodes.P.pruned_at).toBeUndefined();
  });

  it("retains restore intent and reports honestly when every conflict attempt is refused (CR-F3)", async () => {
    const closed = must(closeTab(base(), "P", "prune", "t1")).tree;
    const warn = vi.spyOn(toast, "warn");
    let calls = 0;
    const adapter: TabTreeAdapter = {
      load: async () => toSnapshot(closed),
      save: async () => ++calls <= 3
        ? { status: "conflict", current: toSnapshot(closed) }
        : { status: "saved", version: 2 },
      allocate: async () => ({ public_number: 1 }),
    };
    const save = vi.spyOn(adapter, "save");
    tabs().setTabTreeAdapter(adapter); await tabs().ensureMothership("reading");
    tabs().undoLastClose("reading"); await drain();
    // The bound is spent (1 initial + MAX_CONFLICT_RETRIES) and the intent
    // is NOT dropped: it stays pending, and the operator is told honestly.
    expect(save.mock.calls.length).toBe(3);
    expect(tabs().pendingOps.reading).toEqual([{ type: "restore", tab_id: "P", close_id: "P@t1" }]);
    expect(tabs().trees.reading!.nodes.P.pruned_at).toBe("t1");
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("kept here"));
    // The next operator action retries and lands it.
    tabs().activateTab("reading", "R"); await drain();
    expect(tabs().pendingOps.reading).toEqual([]);
    expect(tabs().trees.reading!.nodes.P.pruned_at).toBeUndefined();
  });

  it("a close held across a 409 preserves and reports a remote child", async () => {
    vi.useFakeTimers();
    let respond!: (value: { status: "conflict"; current: ReturnType<typeof toSnapshot> }) => void;
    let calls = 0;
    const remote = spawn(base(), "P", "new");
    const adapter: TabTreeAdapter = {
      load: async () => toSnapshot(base()),
      save: () => ++calls === 1
        ? new Promise((resolve) => { respond = resolve; })
        : Promise.resolve({ status: "saved", version: calls }),
      allocate: async () => ({ public_number: 1 }),
    };
    const save = vi.spyOn(adapter, "save");
    const info = vi.spyOn(toast, "info");
    tabs().setTabTreeAdapter(adapter); await tabs().ensureMothership("reading");
    tabs().activateTab("reading", "R"); await drain();
    tabs().closeTabById("reading", "P", "prune");
    respond({ status: "conflict", current: toSnapshot(remote) }); await drain();
    expect(tabs().trees.reading!.nodes.new.parent_tab_id).toBe("R");
    expect(info).toHaveBeenCalledWith("Moved under 1: kept a tab added on another device");
    expect(save.mock.calls[1][2].tree.nodes.P).toBeTruthy();
    await vi.advanceTimersByTimeAsync(10_001); await drain();
    expect(save.mock.calls.at(-1)![2].tree.nodes.new.parent_tab_id).toBe("R");
    expect(save.mock.calls.at(-1)![2].tree.nodes.P).toBeUndefined();
  });

});
