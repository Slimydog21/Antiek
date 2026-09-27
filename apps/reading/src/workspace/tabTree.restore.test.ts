/**
 * tabTree.restore.test.ts — lane A B2-6, the model half of prefix+shift+t:
 * after the undo window a retired tab comes back from history (contract
 * §2.2 "restore from retired"), with its own numbers, without disturbing
 * tabs that moved since.
 */
import { describe, expect, it } from "vitest";

import {
  checkInvariants,
  closeTab,
  emptyTabTree,
  lastRetired,
  numberReuse,
  rebase,
  restoreClosed,
  spawnChild,
  type TabTree,
} from "./tabTree";

function spawn(tree: TabTree, parent: string | null, id: string): TabTree {
  const r = spawnChild(tree, parent, { tab_id: id, kind: "reader", ref: id, mothership: "reading" });
  if (!r.ok) throw new Error(r.error.message);
  return r.tree;
}

function close(tree: TabTree, id: string, mode: "prune" | "lift_children", now: string): TabTree {
  const r = closeTab(tree, id, mode, now);
  if (!r.ok) throw new Error(r.error.message);
  return r.tree;
}

/** R (1) with A (1.1) → A1 (1.1.1), A2 (1.1.2), and B (1.2). */
function base(): TabTree {
  let t = emptyTabTree("reading");
  t = spawn(t, null, "R");
  t = spawn(t, "R", "A");
  t = spawn(t, "A", "A1");
  t = spawn(t, "A", "A2");
  t = spawn(t, "R", "B");
  return t;
}

describe("restoreClosed / lastRetired", () => {
  it("a pruned subtree comes back whole, with its numbers, active, and appended under its parent", () => {
    const before = base();
    const closed = close(before, "A", "prune", "2026-09-26T10:00:00Z");
    expect(lastRetired(closed)).toBe("A");
    const r = restoreClosed(closed, "A");
    if (!r.ok) throw new Error(r.error.message);
    expect(r.tree.nodes["A"].hier_number).toBe("1.1");
    expect(r.tree.nodes["A"].child_order).toEqual(["A1", "A2"]);
    expect(r.tree.nodes["R"].child_order).toEqual(["B", "A"]);
    expect(r.tree.active_tab_id).toBe("A");
    expect(Object.keys(r.tree.history)).toEqual([]);
    expect(checkInvariants(r.tree)).toEqual([]);
    expect(numberReuse(closed, r.tree)).toEqual([]);
    expect(r.op).toEqual({ type: "restore", tab_id: "A", close_id: "A@2026-09-26T10:00:00Z" });
  });

  it("a 'close only this' restores the tab alone; its lifted children stay where they are", () => {
    const closed = close(base(), "A", "lift_children", "2026-09-26T10:00:00Z");
    const r = restoreClosed(closed, "A");
    if (!r.ok) throw new Error(r.error.message);
    expect(r.tree.nodes["A"].child_order).toEqual([]);
    expect(r.tree.nodes["A1"].parent_tab_id).toBe("R");
    expect(checkInvariants(r.tree)).toEqual([]);
  });

  it("the most recent close wins, and a tab whose parent has closed since lands under the nearest open ancestor", () => {
    let t = close(base(), "A1", "prune", "2026-09-26T10:00:00Z");
    t = close(t, "A", "prune", "2026-09-26T10:05:00Z");
    expect(lastRetired(t)).toBe("A");
    const a = restoreClosed(t, "A");
    if (!a.ok) throw new Error(a.error.message);
    // A1 was closed on its own, earlier: it is not part of A's close.
    expect(a.tree.nodes["A"].child_order).toEqual(["A2"]);
    expect(lastRetired(a.tree)).toBe("A1");

    // Now close A again and restore A1: it goes under R, the nearest open.
    const again = close(a.tree, "A", "prune", "2026-09-26T10:10:00Z");
    const a1 = restoreClosed(again, "A1");
    if (!a1.ok) throw new Error(a1.error.message);
    expect(a1.tree.nodes["A1"].parent_tab_id).toBe("R");
    expect(a1.tree.nodes["A1"].hier_number).toBe("1.1.1");
    expect(checkInvariants(a1.tree)).toEqual([]);
  });

  it("refuses an open or unknown tab, and a close_id that is not the one that retired it", () => {
    const closed = close(base(), "A", "prune", "2026-09-26T10:00:00Z");
    expect(restoreClosed(closed, "B").ok).toBe(false);
    expect(restoreClosed(closed, "nope").ok).toBe(false);
    expect(restoreClosed(closed, "A", "A@other").ok).toBe(false);
  });

  it("a restore op replays in a rebase", () => {
    const remote = close(base(), "A", "prune", "2026-09-26T10:00:00Z");
    const r = restoreClosed(remote, "A");
    if (!r.ok) throw new Error(r.error.message);
    const rebased = rebase(remote, [r.op]);
    expect(rebased.dropped).toEqual([]);
    expect(rebased.tree.nodes["A"]).toBeTruthy();
    expect(checkInvariants(rebased.tree)).toEqual([]);
  });
});
