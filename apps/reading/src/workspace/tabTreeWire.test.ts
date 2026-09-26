/**
 * tabTreeWire.test.ts — A2a items 2 and 3: the model ↔ THREAD-CONTRACT §1.6
 * wire mapping, proved against lane B's shared fixture (the same file
 * tests/test_project_routes.py replays against the real routes).
 *
 * The load-bearing test: `fromWire` then `toWire`/`toWireSnapshot` gives back
 * the fixture's `expected` GET answer exactly: tree, active, version,
 * counters, and `retired[]` carried through the model's `history` and back.
 */
import { describe, expect, it } from "vitest";

import fixture from "../lib/api/__fixtures__/projectTabs.snapshot.json";
import type { TabsSnapshot } from "../lib/api/projectTabs";
import {
  checkInvariants,
  closeTab,
  emptyTabTree,
  restoreClosed,
  spawnChild,
  type SpawnInput,
  type TabTree,
} from "./tabTree";
import { fromWire, toWire, toWireSnapshot } from "./tabTreeWire";

const expected = fixture.expected as unknown as TabsSnapshot;
const clone = <T>(v: T): T => JSON.parse(JSON.stringify(v)) as T;

function spawn(tree: TabTree, parent: string | null, input: Partial<SpawnInput> & { tab_id: string }): TabTree {
  const r = spawnChild(tree, parent, { kind: "reader", ref: `doc-${input.tab_id}`, mothership: tree.mothership, ...input });
  if (!r.ok) throw new Error(`${r.error.code}: ${r.error.message}`);
  return r.tree;
}

describe("the shared fixture round trips byte-exact (contract §1.6)", () => {
  it("toWire(fromWire(expected)) is the fixture's tree, active and version", () => {
    const tree = fromWire(clone(expected), "research");
    expect(checkInvariants(tree)).toEqual([]);
    expect(toWire(tree)).toStrictEqual({
      tree: expected.tree,
      active: expected.active,
      expected_version: expected.version,
    });
  });

  it("retired[] is carried through history and back, with the counters", () => {
    const tree = fromWire(clone(expected), "research");
    expect(Object.keys(tree.history)).toEqual(["t-dialogue"]);
    expect(tree.history["t-dialogue"].closed_at).toBe("2026-09-27T00:00:00.000000Z");
    expect(tree.history["t-dialogue"].close_mode).toBe("close");
    expect(tree.next_root_index).toBe(4);
    expect(tree.next_child_index).toEqual({ "t-thread": 2 });
    expect(toWireSnapshot(tree)).toStrictEqual(expected);
  });

  it("holds both sides, the agent-opened tab and the right pane's active tab", () => {
    const tree = fromWire(clone(expected), "research");
    expect(tree.nodes["t-thread"].side).toBe("right");
    expect(tree.nodes["t-agent-doc"].side).toBe("left");
    expect(tree.nodes["t-agent-doc"].branch_origin?.kind).toBe("agent");
    expect(tree.nodes["t-agent-doc"].opened_by).toEqual({ thread_id: "inv-fixture-1", agent_kind: "research" });
    expect(tree.active_tab_id).toBe("t-agent-doc");
    expect(tree.active_right).toBe("t-thread");
  });
});

describe("the model → wire mapping", () => {
  it("closed tabs are not sent: the server holds them in retired[]", () => {
    let t = spawn(emptyTabTree("reading"), null, { tab_id: "a" });
    t = spawn(t, null, { tab_id: "b" });
    const closed = closeTab(t, "b", "prune", "2026-09-27T01:00:00Z");
    if (!closed.ok) throw new Error(closed.error.message);
    const body = toWire(closed.tree);
    expect(Object.keys(body.tree.nodes)).toEqual(["a"]);
    expect(body.tree.root_order).toEqual(["a"]);
    expect(JSON.stringify(body)).not.toContain('"b"');
  });

  it("the PUT body carries exactly {tree, active, expected_version}: no counters, no history", () => {
    const t = spawn(emptyTabTree("reading"), null, { tab_id: "a" });
    expect(Object.keys(toWire(t)).sort()).toEqual(["active", "expected_version", "tree"]);
    expect(Object.keys(toWire(t).tree).sort()).toEqual(["nodes", "root_order"]);
  });

  it("island goes on the wire as selection and comes back as island", () => {
    let t = spawn(emptyTabTree("reading"), null, { tab_id: "a" });
    t = spawn(t, "a", { tab_id: "i", origin: { document_id: "doc-a", kind: "island" } });
    const body = toWire(t);
    expect(body.tree.nodes.i.branch_origin?.kind).toBe("selection");
    expect(JSON.stringify(body)).not.toContain('"island"');
    const back = fromWire(
      { tree: body.tree, active: body.active, version: 3, next_child_index: { root: 2, a: 2 }, retired: [] },
      "reading",
    );
    expect(back.nodes.i.branch_origin?.kind).toBe("island");
  });

  it("a node carries only the Part 2 §2.2 fields", () => {
    const allowed = new Set([
      "tab_id", "parent_tab_id", "side", "kind", "ref", "title", "mothership", "pane", "public_number",
      "hier_number", "branch_origin", "opened_by", "child_order", "last_visited_child_id", "pruned_at",
    ]);
    let t = spawn(emptyTabTree("research"), null, { tab_id: "p", pane: { docked_kind: "findings" } });
    t = spawn(t, "p", { tab_id: "c", origin: { document_id: "d", kind: "agent" }, opened_by: { thread_id: "i", agent_kind: "research" } });
    for (const node of Object.values(toWire(t).tree.nodes)) {
      for (const key of Object.keys(node)) expect(allowed.has(key), key).toBe(true);
    }
  });

  it("active: left is the focused left tab, right the server's until agent tabs move into the tree", () => {
    const t = spawn(emptyTabTree("reading"), null, { tab_id: "a" });
    expect(toWire(t).active).toEqual({ left: "a", right: null });
    const server = fromWire(clone(expected), "research");
    expect(toWire(server).active).toEqual({ left: "t-agent-doc", right: "t-thread" });
  });

  it("closing the right pane's active tab clears active.right", () => {
    const server = fromWire(clone(expected), "research");
    const closed = closeTab(server, "t-thread", "lift_children", "2026-09-27T02:00:00Z");
    if (!closed.ok) throw new Error(closed.error.message);
    expect(toWire(closed.tree).active.right).toBeNull();
    expect(checkInvariants(closed.tree)).toEqual([]);
  });

  it("the client's close_mode is the one the server reads off the diff", () => {
    let t = spawn(emptyTabTree("reading"), null, { tab_id: "leaf" });
    t = spawn(t, null, { tab_id: "p" });
    t = spawn(t, "p", { tab_id: "k" });
    t = spawn(t, null, { tab_id: "q" });
    t = spawn(t, "q", { tab_id: "q1" });
    const at = (tree: TabTree, id: string, mode: "prune" | "lift_children") => {
      const r = closeTab(tree, id, mode, "2026-09-27T03:00:00Z");
      if (!r.ok) throw new Error(r.error.message);
      return r.tree;
    };
    expect(at(t, "leaf", "prune").history.leaf.close_mode).toBe("close");
    expect(at(t, "leaf", "lift_children").history.leaf.close_mode).toBe("close");
    const pruned = at(t, "p", "prune");
    expect(pruned.history.p.close_mode).toBe("prune");
    expect(pruned.history.k.close_mode).toBe("prune");
    expect(at(t, "q", "lift_children").history.q.close_mode).toBe("lift_children");
  });

  it("a pruned subtree from the server restores whole: its rows share one close", () => {
    const snap: TabsSnapshot = {
      tree: {
        nodes: { r: { tab_id: "r", parent_tab_id: null, side: "left", kind: "reader", ref: "d-r", title: "", mothership: "reading", public_number: 1, hier_number: "1", child_order: [] } },
        root_order: ["r"],
      },
      active: { left: "r", right: null },
      version: 4,
      next_child_index: { root: 2, r: 2, p: 2 },
      retired: [
        {
          closed_at: "2026-09-27T00:00:00.000002Z",
          close_mode: "prune",
          node: { tab_id: "k", parent_tab_id: "p", side: "left", kind: "reader", ref: "d-k", title: "", mothership: "reading", public_number: 3, hier_number: "1.1.1", child_order: [], pruned_at: "2026-09-27T00:00:00.000002Z" },
        },
        {
          closed_at: "2026-09-27T00:00:00.000001Z",
          close_mode: "prune",
          node: { tab_id: "p", parent_tab_id: "r", side: "left", kind: "reader", ref: "d-p", title: "", mothership: "reading", public_number: 2, hier_number: "1.1", child_order: ["k"], pruned_at: "2026-09-27T00:00:00.000001Z" },
        },
      ],
    };
    const tree = fromWire(clone(snap), "reading");
    expect(checkInvariants(tree)).toEqual([]);
    expect(tree.history.p.close_id).toBe(tree.history.k.close_id);
    const r = restoreClosed(tree, "p");
    if (!r.ok) throw new Error(r.error.message);
    expect(Object.keys(r.tree.history)).toEqual([]);
    expect(toWireSnapshot(tree)).toStrictEqual(snap);
  });
});
