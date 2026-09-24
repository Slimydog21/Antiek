/**
 * Scenario tests for the branch tab tree (MS-04 milestone 1).
 *
 * The invariants I1–I9 are enumerated, and proved exhaustively and by seeded
 * random sequences, in tabTree.property.test.ts. This file pins the named
 * scenarios from the task and the rigor card: the island/selection mapping,
 * public-number refusal (open and history), exact undo, lift keeping numbers,
 * the active-tab rule, depth 200 and 5,000, 174 siblings, the operator's
 * 252-tab herdr scale, the two rebase cases, the adapter (no web storage),
 * and negative controls showing checkInvariants is not vacuous.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  assignPublicNumber,
  checkInvariants,
  closeTab,
  createInMemoryTabTreeAdapter,
  depthOf,
  emptyTabTree,
  findByHierNumber,
  fromSnapshot,
  fromWireKind,
  lastVisitedChild,
  numberReuse,
  pathTo,
  rebase,
  setActive,
  spawnChild,
  toSnapshot,
  toWireKind,
  undo,
  visitChild,
  withVersion,
  type BranchKind,
  type Mothership,
  type SpawnInput,
  type TabNode,
  type TabOp,
  type TabTree,
  type TabTreeResult,
  type TabTreeSnapshot,
  type WireBranchKind,
} from "./tabTree";

const M: Mothership = "research";

function must<T>(r: TabTreeResult<T>): { ok: true } & T {
  if (!r.ok) throw new Error(`${r.error.code}: ${r.error.message}`);
  return r;
}

function spawn(t: TabTree, parent: string | null, id: string, extra: Partial<SpawnInput> = {}): TabTree {
  return must(spawnChild(t, parent, { tab_id: id, kind: "reader", ref: `doc-${id}`, mothership: M, ...extra })).tree;
}

function nodeOf(t: TabTree, id: string): TabNode {
  if (Object.hasOwn(t.nodes, id)) return t.nodes[id];
  if (Object.hasOwn(t.history, id)) return t.history[id].node;
  throw new Error(`no tab ${id}`);
}

const hier = (t: TabTree, id: string) => nodeOf(t, id).hier_number;

/** Roots r1..r3; r3 has a, b, c; b has b1, b2. */
function sampleTree(): TabTree {
  let t = emptyTabTree(M);
  t = spawn(t, null, "r1");
  t = spawn(t, null, "r2");
  t = spawn(t, null, "r3");
  t = spawn(t, "r3", "a");
  t = spawn(t, "r3", "b", { origin: { document_id: "doc-r3", kind: "island", anchor: { document_id: "doc-r3", quote: "q", source_locator: { start: 1, end: 9, text_sha256: "ab" } } } });
  t = spawn(t, "b", "b1");
  t = spawn(t, "b", "b2");
  t = spawn(t, "r3", "c");
  return t;
}

function chain(depth: number, activate = true): TabTree {
  let t = emptyTabTree(M);
  let parent: string | null = null;
  for (let i = 1; i <= depth; i++) {
    const id = `d${i}`;
    t = spawn(t, parent, id, { activate });
    parent = id;
  }
  return t;
}

describe("branch kinds: island <-> selection (contract §1.0, R2-1)", () => {
  const pairs: Array<[BranchKind, WireBranchKind]> = [
    ["footnote", "footnote"],
    ["reference", "reference"],
    ["citation", "citation"],
    ["island", "selection"],
    ["research", "research"],
    ["manual", "manual"],
  ];

  it("maps every UI kind to its wire kind and back", () => {
    for (const [ui, wire] of pairs) {
      expect(toWireKind(ui)).toBe(wire);
      expect(fromWireKind(wire)).toBe(ui);
      expect(fromWireKind(toWireKind(ui))).toBe(ui);
    }
    expect(pairs.map(([ui]) => toWireKind(ui))).not.toContain("island");
  });

  it("puts 'selection' on the wire and 'island' back in the UI tree", () => {
    const t = sampleTree();
    const json = JSON.stringify(toSnapshot(t));
    expect(json.includes('"island"')).toBe(false);
    expect(json.includes('"selection"')).toBe(true);
    const back = must(fromSnapshot(JSON.parse(json)));
    expect(back.tree.nodes.b.branch_origin?.kind).toBe("island");
    expect(back.tree).toStrictEqual(t);
  });

  it("refuses a snapshot that says 'island' on the wire", () => {
    const wire = toSnapshot(sampleTree());
    const node = wire.tree.nodes.b;
    const bad = { ...wire, tree: { ...wire.tree, nodes: { ...wire.tree.nodes, b: { ...node, branch_origin: { ...node.branch_origin!, kind: "island" as WireBranchKind } } } } };
    const r = fromSnapshot(bad);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("invalid_snapshot");
  });
});

describe("hierarchical numbers", () => {
  it("numbers roots 1, 2, 3 and children <parent>.<n>", () => {
    const t = sampleTree();
    expect(["r1", "r2", "r3", "a", "b", "b1", "b2", "c"].map((id) => hier(t, id))).toEqual(["1", "2", "3", "3.1", "3.2", "3.2.1", "3.2.2", "3.3"]);
    expect(checkInvariants(t)).toEqual([]);
  });

  it("never reuses an index under the same parent, even after the child with it closed", () => {
    let t = sampleTree();
    t = must(closeTab(t, "c", "prune", "t1")).tree; // 3.3 retires
    t = must(closeTab(t, "b2", "prune", "t2")).tree; // 3.2.2 retires
    t = spawn(t, "r3", "d");
    t = spawn(t, "b", "b3");
    t = must(closeTab(t, "r3", "prune", "t3")).tree; // root 3 retires
    t = spawn(t, null, "r4");
    expect(hier(t, "d")).toBe("3.4");
    expect(hier(t, "b3")).toBe("3.2.3");
    expect(hier(t, "r4")).toBe("4");
    expect(checkInvariants(t)).toEqual([]);
  });

  it("starts public_number null: the model never invents one", () => {
    const t = sampleTree();
    for (const id of Object.keys(t.nodes)) expect(t.nodes[id].public_number).toBeNull();
  });

  it("resolves a hierarchical number to its tab (numbers as addresses)", () => {
    const t = sampleTree();
    expect(findByHierNumber(t, "3.2.1")).toBe("b1");
    expect(findByHierNumber(t, "9")).toBeNull();
  });
});

describe("assignPublicNumber", () => {
  it("records an allocated number and is idempotent for the same number", () => {
    let t = sampleTree();
    t = must(assignPublicNumber(t, "a", 7)).tree;
    expect(t.nodes.a.public_number).toBe(7);
    const again = must(assignPublicNumber(t, "a", 7));
    expect(again.tree).toBe(t);
  });

  it("refuses a number held by another open tab", () => {
    let t = sampleTree();
    t = must(assignPublicNumber(t, "a", 7)).tree;
    const r = assignPublicNumber(t, "b", 7);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("public_number_taken");
  });

  it("refuses a number held by a tab in history (retired numbers are never reused)", () => {
    let t = sampleTree();
    t = must(assignPublicNumber(t, "b1", 11)).tree;
    t = must(closeTab(t, "b", "prune", "t1")).tree; // b1 moves to history with 11
    expect(t.history.b1.node.public_number).toBe(11);
    const r = assignPublicNumber(t, "a", 11);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("public_number_taken");
  });

  it("refuses to renumber a numbered tab, a bad number, and an unknown tab", () => {
    let t = sampleTree();
    t = must(assignPublicNumber(t, "a", 3)).tree;
    const renumber = assignPublicNumber(t, "a", 4);
    expect(renumber.ok ? "ok" : renumber.error.code).toBe("already_numbered");
    for (const bad of [0, -1, 1.5, Number.NaN]) {
      const r = assignPublicNumber(t, "b", bad);
      expect(r.ok ? "ok" : r.error.code).toBe("public_number_invalid");
    }
    const unknown = assignPublicNumber(t, "nope", 9);
    expect(unknown.ok ? "ok" : unknown.error.code).toBe("unknown_tab");
  });

  it("numbers a tab that closed while its allocate was in flight", () => {
    let t = sampleTree();
    t = must(closeTab(t, "c", "prune", "t1")).tree;
    t = must(assignPublicNumber(t, "c", 5)).tree;
    expect(t.history.c.node.public_number).toBe(5);
    expect(checkInvariants(t)).toEqual([]);
  });
});

describe("close and undo", () => {
  it("prune moves the subtree to history with pruned_at, and undo restores it exactly", () => {
    const t = must(assignPublicNumber(sampleTree(), "b1", 4)).tree;
    const c = must(closeTab(t, "b", "prune", "2026-09-24T10:00:00Z"));
    expect(Object.keys(c.tree.nodes).sort()).toEqual(["a", "c", "r1", "r2", "r3"]);
    for (const id of ["b", "b1", "b2"]) expect(c.tree.history[id].node.pruned_at).toBe("2026-09-24T10:00:00Z");
    expect(c.tree.nodes.r3.child_order).toEqual(["a", "c"]);
    const u = must(undo(c.tree, c.undo));
    expect(u.tree).toStrictEqual(t);
    expect(numberReuse(t, u.tree)).toEqual([]);
  });

  it("lift keeps the children's numbers: a lifted 3.2.1 stays 3.2.1 under 3", () => {
    const t = sampleTree();
    const c = must(closeTab(t, "b", "lift_children", "t1"));
    expect(c.tree.nodes.r3.child_order).toEqual(["a", "b1", "b2", "c"]);
    expect(c.tree.nodes.b1.parent_tab_id).toBe("r3");
    expect(c.tree.nodes.b1.hier_number).toBe("3.2.1");
    expect(c.tree.nodes.b2.hier_number).toBe("3.2.2");
    expect(c.tree.history.b.node.pruned_at).toBe("t1");
    expect(checkInvariants(c.tree)).toEqual([]);
    expect(must(undo(c.tree, c.undo)).tree).toStrictEqual(t);
  });

  it("lifting a root makes its children roots at its position, numbers unchanged", () => {
    const t = sampleTree();
    const c = must(closeTab(t, "r3", "lift_children", "t1"));
    expect(c.tree.root_order).toEqual(["r1", "r2", "a", "b", "c"]);
    expect(c.tree.nodes.b.parent_tab_id).toBeNull();
    expect(c.tree.nodes.b.hier_number).toBe("3.2");
    expect(checkInvariants(c.tree)).toEqual([]);
    expect(must(undo(c.tree, c.undo)).tree).toStrictEqual(t);
  });

  it("a spawn under a lifted child continues its own number space", () => {
    let t = must(closeTab(sampleTree(), "b", "lift_children", "t1")).tree;
    t = spawn(t, "b1", "x");
    t = spawn(t, "r3", "y");
    expect(hier(t, "x")).toBe("3.2.1.1");
    expect(hier(t, "y")).toBe("3.4");
    expect(checkInvariants(t)).toEqual([]);
  });

  it("refuses a token that was already undone, leaving the tree alone", () => {
    const c = must(closeTab(sampleTree(), "b", "prune", "t1"));
    const u = must(undo(c.tree, c.undo));
    const again = undo(u.tree, c.undo);
    expect(again.ok ? "ok" : again.error.code).toBe("not_closed_by_token");
  });

  it("refuses an old token once the tab was closed again by a later close", () => {
    const t = sampleTree();
    const first = must(closeTab(t, "c", "prune", "t1"));
    const reopened = must(undo(first.tree, first.undo)).tree;
    const second = must(closeTab(reopened, "c", "prune", "t2"));
    const stale = undo(second.tree, first.undo);
    expect(stale.ok ? "ok" : stale.error.code).toBe("not_closed_by_token");
  });

  it("an undo after the parent closed re-homes the tab under the nearest open ancestor, numbers kept", () => {
    const t = sampleTree();
    const c1 = must(closeTab(t, "b1", "prune", "t1"));
    const c2 = must(closeTab(c1.tree, "b", "prune", "t2"));
    const u = must(undo(c2.tree, c1.undo));
    expect(u.tree.nodes.b1.parent_tab_id).toBe("r3");
    expect(u.tree.nodes.r3.child_order).toEqual(["a", "c", "b1"]);
    expect(u.tree.nodes.b1.hier_number).toBe("3.2.1");
    expect(checkInvariants(u.tree)).toEqual([]);
  });

  it("undoing a lift takes back the original children that are still open", () => {
    const t = sampleTree();
    const lift = must(closeTab(t, "b", "lift_children", "t1"));
    const gone = must(closeTab(lift.tree, "b2", "prune", "t2"));
    const u = must(undo(gone.tree, lift.undo));
    expect(u.tree.nodes.b.child_order).toEqual(["b1"]);
    expect(u.tree.nodes.b1.parent_tab_id).toBe("b");
    expect(u.tree.nodes.r3.child_order).toEqual(["a", "b", "c"]);
    expect(Object.hasOwn(u.tree.history, "b2")).toBe(true);
    expect(checkInvariants(u.tree)).toEqual([]);
  });

  it("refuses to close a tab that is not open", () => {
    const r = closeTab(sampleTree(), "zz", "prune", "t");
    expect(r.ok ? "ok" : r.error.code).toBe("tab_not_open");
  });
});

describe("active tab after close (parent, else previous root, else next root, else null)", () => {
  it("moves to the parent", () => {
    const t = must(setActive(sampleTree(), "b1")).tree;
    expect(must(closeTab(t, "b", "prune", "t")).tree.active_tab_id).toBe("r3");
  });

  it("does not move when the active tab survives (lift keeps an active child open)", () => {
    const t = must(setActive(sampleTree(), "b1")).tree;
    expect(must(closeTab(t, "b", "lift_children", "t")).tree.active_tab_id).toBe("b1");
    expect(must(closeTab(t, "a", "prune", "t")).tree.active_tab_id).toBe("b1");
  });

  it("moves to the previous root, else the next root, else null", () => {
    const t = must(setActive(sampleTree(), "r2")).tree;
    expect(must(closeTab(t, "r2", "prune", "t")).tree.active_tab_id).toBe("r1");
    const first = must(setActive(sampleTree(), "r1")).tree;
    expect(must(closeTab(first, "r1", "prune", "t")).tree.active_tab_id).toBe("r2");
    const only = spawn(emptyTabTree(M), null, "solo");
    expect(must(closeTab(only, "solo", "prune", "t")).tree.active_tab_id).toBeNull();
  });

  it("lifting the first active root focuses its first lifted child", () => {
    let t = spawn(emptyTabTree(M), null, "p");
    t = spawn(t, "p", "k1");
    t = must(setActive(t, "p")).tree;
    expect(must(closeTab(t, "p", "lift_children", "t")).tree.active_tab_id).toBe("k1");
  });

  it("undo restores the tab that was active", () => {
    const t = must(setActive(sampleTree(), "b2")).tree;
    const c = must(closeTab(t, "b", "prune", "t"));
    expect(must(undo(c.tree, c.undo)).tree.active_tab_id).toBe("b2");
  });
});

describe("last_visited_child_id (prefix+o)", () => {
  it("setActive points every ancestor down the path, and visitChild follows it", () => {
    let t = sampleTree();
    t = must(setActive(t, "b2")).tree;
    expect(t.nodes.r3.last_visited_child_id).toBe("b");
    expect(t.nodes.b.last_visited_child_id).toBe("b2");
    t = must(setActive(t, "r3")).tree;
    t = must(visitChild(t, "r3")).tree;
    expect(t.active_tab_id).toBe("b");
    t = must(visitChild(t, "b")).tree;
    expect(t.active_tab_id).toBe("b2");
  });

  it("falls back to the first child, and refuses a leaf", () => {
    const t = spawn(spawn(spawn(emptyTabTree(M), null, "p", { activate: false }), "p", "k1", { activate: false }), "p", "k2", { activate: false });
    expect(lastVisitedChild(t, "p")).toBe("k1");
    const r = visitChild(t, "k2");
    expect(r.ok ? "ok" : r.error.code).toBe("no_children");
  });

  it("a background spawn does not steal focus", () => {
    const t = spawn(spawn(emptyTabTree(M), null, "p"), "p", "agent-branch", { activate: false });
    expect(t.active_tab_id).toBe("p");
    expect(t.nodes.p.last_visited_child_id).toBeUndefined();
  });

  it("closing the remembered child clears the pointer, and undo restores it", () => {
    const t = must(setActive(sampleTree(), "b")).tree;
    const c = must(closeTab(t, "b", "prune", "t"));
    expect(c.tree.nodes.r3.last_visited_child_id).toBeUndefined();
    expect(must(undo(c.tree, c.undo)).tree).toStrictEqual(t);
  });
});

describe("depth (D6: 'infinitely layered')", () => {
  it("holds every invariant at depth 200, with prune/lift + exact undo in the middle", () => {
    const t = chain(200);
    expect(depthOf(t, "d200")).toBe(200);
    expect(pathTo(t, "d200")).toHaveLength(200);
    expect(hier(t, "d200").split(".")).toHaveLength(200);
    expect(checkInvariants(t)).toEqual([]);
    const pruned = must(closeTab(t, "d100", "prune", "t"));
    expect(Object.keys(pruned.tree.nodes)).toHaveLength(99);
    expect(pruned.tree.active_tab_id).toBe("d99");
    expect(must(undo(pruned.tree, pruned.undo)).tree).toStrictEqual(t);
    const lifted = must(closeTab(t, "d100", "lift_children", "t"));
    expect(lifted.tree.nodes.d101.parent_tab_id).toBe("d99");
    expect(lifted.tree.nodes.d101.hier_number).toBe(hier(t, "d101"));
    expect(checkInvariants(lifted.tree)).toEqual([]);
    expect(must(undo(lifted.tree, lifted.undo)).tree).toStrictEqual(t);
    expect(must(fromSnapshot(JSON.parse(JSON.stringify(toSnapshot(t))))).tree).toStrictEqual(t);
  });

  /** A chain as the server would return it. Building 5,000 tabs through
   *  spawnChild costs O(n^2) record copies (measured ~8 s: each op copies the
   *  nodes record, ~1.4 ms per spawn at 5,000 tabs), so this test starts from
   *  a snapshot, which is O(n), and then drives every traversal at depth. */
  function chainSnapshot(depth: number): TabTreeSnapshot {
    const nodes: Record<string, TabNode<WireBranchKind>> = {};
    const next_child_index: Record<string, number> = {};
    let h = "";
    for (let i = 1; i <= depth; i++) {
      h = i === 1 ? "1" : `${h}.1`;
      nodes[`d${i}`] = {
        tab_id: `d${i}`,
        parent_tab_id: i === 1 ? null : `d${i - 1}`,
        hier_number: h,
        child_order: i < depth ? [`d${i + 1}`] : [],
        ...(i < depth ? { last_visited_child_id: `d${i + 1}` } : {}),
        kind: "reader",
        ref: `doc-d${i}`,
        mothership: M,
        public_number: null,
      };
      if (i < depth) next_child_index[`d${i}`] = 2;
    }
    return {
      tree: { mothership: M, nodes, root_order: ["d1"], history: {}, next_root_index: 2, next_child_index },
      active_tab_id: `d${depth}`,
      retired_numbers: [],
      version: 0,
    };
  }

  it("operates on a depth-5,000 chain without a stack overflow", () => {
    const started = performance.now();
    const t = must(fromSnapshot(chainSnapshot(5_000))).tree; // runs checkInvariants at depth
    expect(depthOf(t, "d5000")).toBe(5_000);
    expect(pathTo(t, "d5000")).toHaveLength(5_000);
    // spawn at depth 5,001 (with the activation walk up 5,000 ancestors)
    const deeper = spawn(t, "d5000", "d5001");
    expect(hier(deeper, "d5001").split(".")).toHaveLength(5_001);
    expect(deeper.active_tab_id).toBe("d5001");
    // prune the whole chain below the root, then undo it exactly
    const pruned = must(closeTab(t, "d2", "prune", "t"));
    expect(Object.keys(pruned.tree.history)).toHaveLength(4_999);
    expect(pruned.tree.active_tab_id).toBe("d1");
    expect(must(undo(pruned.tree, pruned.undo)).tree).toStrictEqual(t);
    // lift in the middle keeps numbers
    const lifted = must(closeTab(t, "d2500", "lift_children", "t"));
    expect(lifted.tree.nodes.d2501.hier_number).toBe(t.nodes.d2501.hier_number);
    expect(lifted.tree.nodes.d2501.parent_tab_id).toBe("d2499");
    expect(must(undo(lifted.tree, lifted.undo)).tree).toStrictEqual(t);
    // prefix+o from the root retraces the whole path down
    let walk = must(setActive(t, "d1")).tree;
    for (let i = 2; i <= 5_000; i++) walk = must(visitChild(walk, walk.active_tab_id as string)).tree;
    expect(walk.active_tab_id).toBe("d5000");
    const wire = JSON.stringify(toSnapshot(t));
    expect(must(fromSnapshot(JSON.parse(wire))).tree).toStrictEqual(t);
    console.info(
      `[tabTree depth] 5000-deep chain: ${(performance.now() - started).toFixed(0)} ms; wire snapshot ${(wire.length / 1e6).toFixed(1)} MB (hier_number strings are O(depth) each)`,
    );
  }, 120_000);
});

describe("scale", () => {
  it("174 siblings: numbers 1..174, monotonic after closes, kept by lift", () => {
    let t = spawn(emptyTabTree(M), null, "p");
    for (let i = 1; i <= 174; i++) t = spawn(t, "p", `s${i}`, { activate: false });
    expect(t.nodes.p.child_order).toHaveLength(174);
    expect(hier(t, "s174")).toBe("1.174");
    for (let i = 2; i <= 174; i += 2) t = must(closeTab(t, `s${i}`, "prune", `t${i}`)).tree;
    for (let i = 175; i <= 184; i++) t = spawn(t, "p", `s${i}`, { activate: false });
    expect(hier(t, "s175")).toBe("1.175");
    expect(hier(t, "s184")).toBe("1.184");
    const lifted = must(closeTab(t, "p", "lift_children", "tl")).tree;
    expect(lifted.root_order).toHaveLength(97);
    expect(lifted.nodes.s173.hier_number).toBe("1.173");
    expect(checkInvariants(lifted)).toEqual([]);
  });

  it("the operator's herdr scale: 20 workstations, 252 tabs, one 174-tab tree deeper than 12", async () => {
    const server = createInMemoryTabTreeAdapter();
    const sizes = [174, ...Array.from({ length: 19 }, (_, i) => (i < 2 ? 5 : 4))];
    expect(sizes.reduce((a, b) => a + b, 0)).toBe(252);
    const trees: TabTree[] = [];
    for (let w = 0; w < 20; w++) {
      const project = `ws${w}`;
      let t = emptyTabTree(M);
      for (let i = 1; i <= sizes[w]; i++) {
        const id = `${project}-t${i}`;
        // First 16 tabs form a chain (depth 16 > 12); then fan out.
        const parent = i === 1 ? null : i <= 16 ? `${project}-t${i - 1}` : `${project}-t${1 + ((i * 7) % Math.min(i - 1, 40))}`;
        t = spawn(t, parent, id, { activate: i <= 16 });
        const { public_number } = await server.allocate(project, M);
        t = must(assignPublicNumber(t, id, public_number)).tree;
      }
      expect((await server.save(project, M, toSnapshot(t))).status).toBe("saved");
      trees.push(t);
    }
    let total = 0;
    for (let w = 0; w < 20; w++) {
      const loaded = must(fromSnapshot(await server.load(`ws${w}`, M))).tree;
      expect(checkInvariants(loaded)).toEqual([]);
      expect(loaded).toStrictEqual(withVersion(trees[w], 1));
      for (const id of Object.keys(loaded.nodes)) expect(findByHierNumber(loaded, loaded.nodes[id].hier_number)).toBe(id);
      total += Object.keys(loaded.nodes).length;
    }
    expect(total).toBe(252);
    const big = trees[0];
    expect(Object.keys(big.nodes)).toHaveLength(174);
    expect(Math.max(...Object.keys(big.nodes).map((id) => depthOf(big, id)))).toBeGreaterThan(12);
    const publics = Object.keys(big.nodes).map((id) => big.nodes[id].public_number);
    expect(new Set(publics).size).toBe(174);
  });
});

describe("rebase after a 409", () => {
  async function twoDevices() {
    const server = createInMemoryTabTreeAdapter();
    let base = spawn(emptyTabTree(M), null, "root");
    base = spawn(base, "root", "mid");
    expect((await server.save("ws", M, toSnapshot(base))).status).toBe("saved");
    const load = async () => must(fromSnapshot(await server.load("ws", M))).tree;
    return { server, a: await load(), b: await load() };
  }

  it("two devices spawn under the same parent: the loser is renumbered, all numbers unique", async () => {
    const { server, a, b } = await twoDevices();
    const aSpawn = must(spawnChild(a, "root", { tab_id: "from-a", kind: "reader", ref: "x", mothership: M }));
    const bSpawn = must(spawnChild(b, "root", { tab_id: "from-b", kind: "reader", ref: "y", mothership: M }));
    expect(hier(aSpawn.tree, "from-a")).toBe("1.2");
    expect(hier(bSpawn.tree, "from-b")).toBe("1.2");
    expect((await server.save("ws", M, toSnapshot(aSpawn.tree))).status).toBe("saved");
    const conflict = await server.save("ws", M, toSnapshot(bSpawn.tree));
    expect(conflict.status).toBe("conflict");
    if (conflict.status !== "conflict") return;
    const remote = must(fromSnapshot(conflict.current)).tree;
    const r = rebase(remote, [bSpawn.op]);
    expect(r.dropped).toEqual([]);
    expect(hier(r.tree, "from-a")).toBe("1.2");
    expect(hier(r.tree, "from-b")).toBe("1.3");
    expect(r.renumbered).toEqual([{ tab_id: "from-b", from: "1.2", to: "1.3" }]);
    expect(r.tree.version).toBe(remote.version);
    expect(checkInvariants(r.tree)).toEqual([]);
    expect((await server.save("ws", M, toSnapshot(r.tree))).status).toBe("saved");
  });

  it("the server refuses the un-rebased snapshot as number reuse", async () => {
    const { server, a, b } = await twoDevices();
    const aTree = spawn(a, "root", "from-a");
    const bTree = spawn(b, "root", "from-b");
    expect((await server.save("ws", M, toSnapshot(aTree))).status).toBe("saved");
    // A buggy client that skips rebase and just bumps the version:
    const r = await server.save("ws", M, toSnapshot(withVersion(bTree, 2)));
    expect(r.status).toBe("rejected");
    if (r.status === "rejected") expect(r.reasons.join(" ")).toContain("hier_number 1.2 belongs to from-a");
  });

  it("a spawn whose parent another device closed is re-homed, not lost; ops on the closed tab drop", async () => {
    const { server, a, b } = await twoDevices();
    // Device A prunes "mid" (and its subtree).
    const aTree = must(closeTab(a, "mid", "prune", "t1")).tree;
    expect((await server.save("ws", M, toSnapshot(aTree))).status).toBe("saved");
    // Device B, offline, spawns under "mid", then focuses "mid".
    const pending: TabOp[] = [];
    const s1 = must(spawnChild(b, "mid", { tab_id: "deep", kind: "research", ref: "thread-1", mothership: M }));
    pending.push(s1.op);
    const s2 = must(spawnChild(s1.tree, "deep", { tab_id: "deeper", kind: "reader", ref: "doc", mothership: M }));
    pending.push(s2.op);
    const f = must(setActive(s2.tree, "mid"));
    pending.push(f.op);
    const conflict = await server.save("ws", M, toSnapshot(f.tree));
    expect(conflict.status).toBe("conflict");
    if (conflict.status !== "conflict") return;
    const r = rebase(must(fromSnapshot(conflict.current)).tree, pending);
    expect(r.tree.nodes.deep.parent_tab_id).toBe("root");
    expect(r.tree.nodes.deep.hier_number).toBe("1.2");
    expect(r.tree.nodes.deeper.parent_tab_id).toBe("deep");
    expect(r.tree.nodes.deeper.hier_number).toBe("1.2.1");
    expect(r.dropped.map((d) => [d.op.type, d.reason])).toEqual([["set_active", "tab_not_open"]]);
    expect(Object.hasOwn(r.tree.history, "mid")).toBe(true);
    expect(checkInvariants(r.tree)).toEqual([]);
    expect((await server.save("ws", M, toSnapshot(r.tree))).status).toBe("saved");
  });

  it("a spawn whose whole ancestry closed remotely becomes a root", () => {
    let remote = spawn(emptyTabTree(M), null, "root");
    remote = spawn(remote, "root", "mid");
    const local = spawnChild(remote, "mid", { tab_id: "kept", kind: "reader", ref: "x", mothership: M });
    const closed = must(closeTab(remote, "root", "prune", "t")).tree;
    const r = rebase(closed, [must(local).op]);
    expect(r.tree.nodes.kept.parent_tab_id).toBeNull();
    expect(r.tree.root_order).toEqual(["kept"]);
    expect(r.tree.nodes.kept.hier_number).toBe("2");
    expect(checkInvariants(r.tree)).toEqual([]);
  });

  it("replays a pending close and its undo, and drops an undo whose close was dropped", () => {
    const base = sampleTree();
    const c = must(closeTab(base, "b", "prune", "t1", "local-close"));
    const u = must(undo(c.tree, c.undo));
    const replayed = rebase(base, [c.op, u.op]);
    expect(replayed.dropped).toEqual([]);
    expect(replayed.tree).toStrictEqual(base);
    const remoteClosedB = must(closeTab(base, "b", "prune", "t0", "remote-close")).tree;
    const r = rebase(remoteClosedB, [c.op, u.op]);
    expect(r.dropped.map((d) => [d.op.type, d.reason])).toEqual([
      ["close", "tab_not_open"],
      ["undo", "not_closed_by_token"],
    ]);
    expect(r.tree).toStrictEqual(remoteClosedB);
  });
});

describe("persistence adapter (contract §1.6)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("never touches localStorage or sessionStorage", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const getItem = vi.spyOn(Storage.prototype, "getItem");
    const server = createInMemoryTabTreeAdapter();
    let t = sampleTree();
    t = must(assignPublicNumber(t, "a", (await server.allocate("ws", M)).public_number)).tree;
    expect((await server.save("ws", M, toSnapshot(t))).status).toBe("saved");
    must(fromSnapshot(await server.load("ws", M)));
    rebase(t, []);
    expect(setItem).not.toHaveBeenCalled();
    expect(getItem).not.toHaveBeenCalled();
  });

  it("allocates public numbers workstation-wide, across motherships", async () => {
    const server = createInMemoryTabTreeAdapter();
    const got = [
      (await server.allocate("ws", "research")).public_number,
      (await server.allocate("ws", "reading")).public_number,
      (await server.allocate("ws", "writing")).public_number,
      (await server.allocate("other", "research")).public_number,
    ];
    expect(got).toEqual([1, 2, 3, 1]);
  });

  it("answers a stale version with 409 {current}", async () => {
    const server = createInMemoryTabTreeAdapter();
    const t = sampleTree();
    expect(await server.save("ws", M, toSnapshot(t))).toEqual({ status: "saved", version: 1 });
    const stale = await server.save("ws", M, toSnapshot(t));
    expect(stale.status).toBe("conflict");
    if (stale.status === "conflict") expect(stale.current.version).toBe(1);
  });

  it("refuses a public number it never allocated, and a different tab taking a retired number", async () => {
    const server = createInMemoryTabTreeAdapter();
    const invented = must(assignPublicNumber(sampleTree(), "a", 99)).tree;
    const r1 = await server.save("ws", M, toSnapshot(invented));
    expect(r1.status).toBe("rejected");
    if (r1.status === "rejected") expect(r1.reasons.join(" ")).toContain("never allocated");

    let t = sampleTree();
    expect((await server.save("ws", M, toSnapshot(t))).status).toBe("saved");
    t = must(closeTab(t, "c", "prune", "t1")).tree; // 3.3 retires with tab c
    expect((await server.save("ws", M, toSnapshot(withVersion(t, 1)))).status).toBe("saved");
    // Forge a tree where a different tab holds the retired 3.3.
    const forged: TabTree = {
      ...t,
      version: 2,
      history: {},
      nodes: { ...t.nodes, imposter: { ...t.history.c.node, tab_id: "imposter", pruned_at: undefined } },
    };
    delete (forged.nodes.imposter as { pruned_at?: string }).pruned_at;
    (forged.nodes as Record<string, TabNode>).r3 = { ...t.nodes.r3, child_order: [...t.nodes.r3.child_order, "imposter"] };
    const r2 = await server.save("ws", M, toSnapshot(forged));
    expect(r2.status).toBe("rejected");
    if (r2.status === "rejected") expect(r2.reasons.join(" ")).toContain("hier_number 3.3 belongs to c");
  });
});

describe("reuse (contract R3-1) and the invariant checker's negative controls", () => {
  it("the same tab_id getting its number back is not reuse; a different tab_id is", () => {
    const t = sampleTree();
    const c = must(closeTab(t, "c", "prune", "t1"));
    expect(numberReuse(t, must(undo(c.tree, c.undo)).tree)).toEqual([]);
    const imposter = { ...c.tree.history.c.node, tab_id: "imposter" };
    delete (imposter as { pruned_at?: string }).pruned_at;
    const forged: TabTree = {
      ...c.tree,
      history: {},
      nodes: { ...c.tree.nodes, imposter, r3: { ...c.tree.nodes.r3, child_order: [...c.tree.nodes.r3.child_order, "imposter"] } },
    };
    expect(numberReuse(t, forged)).toEqual(["hier_number 3.3 moved from c to imposter"]);
  });

  /** Each fault must be named by the invariant it breaks. */
  const faults: Array<[string, string, (t: TabTree) => TabTree]> = [
    ["I1", "duplicate hier_number", (t) => ({ ...t, nodes: { ...t.nodes, c: { ...t.nodes.c, hier_number: "3.1" } } })],
    ["I1", "a number reused from history", (t) => {
      const c = must(closeTab(t, "c", "prune", "x")).tree;
      return { ...c, nodes: { ...c.nodes, a: { ...c.nodes.a, hier_number: "3.3" } } };
    }],
    ["I2", "duplicate public_number", (t) => ({ ...t, nodes: { ...t.nodes, a: { ...t.nodes.a, public_number: 5 }, c: { ...t.nodes.c, public_number: 5 } } })],
    ["I4", "a counter at or below an issued index", (t) => ({ ...t, next_child_index: { ...t.next_child_index, r3: 3 } })],
    ["I4", "a root counter at or below an issued index", (t) => ({ ...t, next_root_index: 2 })],
    ["I5", "a child_order naming a tab whose parent differs", (t) => ({ ...t, nodes: { ...t.nodes, r1: { ...t.nodes.r1, child_order: ["a"] } } })],
    ["I5", "a dangling child id", (t) => ({ ...t, nodes: { ...t.nodes, a: { ...t.nodes.a, child_order: ["ghost"] } } })],
    ["I5", "a root missing from root_order", (t) => ({ ...t, root_order: ["r1", "r2"] })],
    ["I5", "a cycle", (t) => ({
      ...t,
      root_order: ["r1", "r2"],
      nodes: { ...t.nodes, r3: { ...t.nodes.r3, parent_tab_id: "b1" }, b1: { ...t.nodes.b1, child_order: ["r3"] } },
    })],
    ["I5", "last_visited_child_id that is not a child", (t) => ({ ...t, nodes: { ...t.nodes, r3: { ...t.nodes.r3, last_visited_child_id: "b1" } } })],
    ["I5", "an open tab with pruned_at", (t) => ({ ...t, nodes: { ...t.nodes, a: { ...t.nodes.a, pruned_at: "x" } } })],
    ["I5", "a tab both open and closed", (t) => ({ ...t, history: { a: { node: { ...t.nodes.a, pruned_at: "x" }, close_id: "x" } } })],
    ["I8", "an active tab that is closed", (t) => ({ ...t, active_tab_id: "ghost" })],
    ["I9", "a parent that is not a spawn-ancestor", (t) => ({
      ...t,
      nodes: { ...t.nodes, a: { ...t.nodes.a, parent_tab_id: "r1" }, r1: { ...t.nodes.r1, child_order: ["a"] }, r3: { ...t.nodes.r3, child_order: ["b", "c"] } },
    })],
  ];

  for (const [inv, what, fault] of faults) {
    it(`${inv} catches ${what}`, () => {
      const t = sampleTree();
      expect(checkInvariants(t)).toEqual([]);
      const v = checkInvariants(fault(t));
      expect(v.some((x) => x.startsWith(`${inv}:`))).toBe(true);
    });
  }

  it("fromSnapshot refuses a snapshot that breaks an invariant or misreports retired numbers", () => {
    const good = toSnapshot(must(closeTab(sampleTree(), "c", "prune", "t")).tree);
    expect(fromSnapshot({ ...good, active_tab_id: "ghost" }).ok).toBe(false);
    expect(fromSnapshot({ ...good, retired_numbers: [] }).ok).toBe(false);
    expect(fromSnapshot({ ...good, tree: null as unknown as typeof good.tree }).ok).toBe(false);
    expect(fromSnapshot(good).ok).toBe(true);
  });
});

describe("input validation and purity", () => {
  it("refuses a closed parent, a duplicate tab_id (open or closed), a wrong mothership and '__proto__'", () => {
    const t = must(closeTab(sampleTree(), "c", "prune", "t")).tree;
    const input = (id: string, extra: Partial<SpawnInput> = {}): SpawnInput => ({ tab_id: id, kind: "reader", ref: "x", mothership: M, ...extra });
    const code = (r: TabTreeResult<unknown>) => (r.ok ? "ok" : r.error.code);
    expect(code(spawnChild(t, "c", input("n1")))).toBe("tab_not_open");
    expect(code(spawnChild(t, null, input("a")))).toBe("duplicate_tab_id");
    expect(code(spawnChild(t, null, input("c")))).toBe("duplicate_tab_id");
    expect(code(spawnChild(t, null, input("n2", { mothership: "writing" })))).toBe("wrong_mothership");
    expect(code(spawnChild(t, null, input("__proto__")))).toBe("invalid_tab_id");
    expect(code(spawnChild(t, null, input("")))).toBe("invalid_tab_id");
    expect(code(setActive(t, "c"))).toBe("tab_not_open");
  });

  it("treats prototype names such as 'constructor' as ordinary tab ids", () => {
    let t = spawn(emptyTabTree(M), null, "constructor");
    t = spawn(t, "constructor", "toString");
    expect(hier(t, "toString")).toBe("1.1");
    expect(checkInvariants(t)).toEqual([]);
    expect(spawnChild(t, "hasOwnProperty", { tab_id: "x", kind: "reader", ref: "x", mothership: M }).ok).toBe(false);
    // toEqual, not toStrictEqual: vitest's strict type check reads
    // `nodes.constructor`, which here is a tab, so it would fail on equal data.
    expect(must(fromSnapshot(JSON.parse(JSON.stringify(toSnapshot(t))))).tree).toEqual(t);
  });

  it("never mutates its input (every op on a frozen tree)", () => {
    const freeze = <T,>(v: T): T => {
      if (v && typeof v === "object" && !Object.isFrozen(v)) {
        Object.freeze(v);
        for (const k of Object.keys(v)) freeze((v as Record<string, unknown>)[k]);
      }
      return v;
    };
    const t = freeze(must(setActive(sampleTree(), "b1")).tree);
    const before = JSON.stringify(t);
    const c = must(closeTab(t, "b", "lift_children", "t"));
    freeze(c.tree);
    must(undo(c.tree, c.undo));
    must(closeTab(t, "r3", "prune", "t"));
    must(assignPublicNumber(t, "a", 1));
    must(visitChild(t, "r3"));
    spawn(t, "b1", "z");
    rebase(t, [c.op]);
    toSnapshot(t);
    expect(JSON.stringify(t)).toBe(before);
  });
});
