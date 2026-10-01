/**
 * Property proof for the stage-2 document-tab rules (seeded, mulberry32 from
 * src/scene/rng.ts; each case i runs on SEED + i so a failure replays alone).
 *
 *  (P1) Adoption: a tab that shows the route is never orphaned. After any
 *       tab is activated, the route change its activation causes adopts it
 *       (no root is seeded beside it); a route change to a path an open tab
 *       shows ACTIVATES an open tab showing it, never seeds, and prefers the
 *       active tab's nearest ancestor; only a path no open tab shows seeds.
 *  (P2) Depth-first: with three roots and random nesting, the tree panel's
 *       rows are the pre-order concatenation of the roots' subtrees; every
 *       row's parent precedes it; each subtree is contiguous; aria-level is
 *       the depth, posinset/setsize match the sibling order.
 *  (P3) Labels: a known title always wins over the ref and never contains
 *       it; with no title (unknown, loading, failed, or known-null) the label
 *       is a readable noun that contains no part of the raw ref.
 */
import { describe, expect, it } from "vitest";

import { makeRng, type Rng } from "../scene/rng";
import { adoptTabForRoute, routeForTab, tabShowsPath } from "./documentSpace";
import { flattenTabRows } from "./tabRows";
import { labelForTab } from "./tabLabels";
import type { TitleEntry } from "./tabTitles";
import {
  depthOf,
  emptyTabTree,
  pathTo,
  setActive,
  spawnChild,
  subtreeIds,
  type Mothership,
  type TabKind,
  type TabNode,
  type TabTree,
} from "./tabTree";

export const SEED = 0x57a6e2;
const CASES = 300;

const KINDS: TabKind[] = ["reader", "research", "document", "thread"];
const MOTHERSHIPS: Mothership[] = ["research", "writing", "reading"];

function refFor(rng: Rng, kind: TabKind, pool: number): string {
  const n = rng.int(0, pool - 1);
  switch (kind) {
    case "reader":
      return `doc-${n}`;
    case "research":
    case "thread":
      return `/inv/inv-${n}`;
    case "document":
      return rng.next() < 0.5 ? `/write/d-${n}` : `section:s-${n}`;
    default:
      return `x-${n}`;
  }
}

/** A random forest: `roots` roots, then `extra` spawns under random parents. */
function randomForest(rng: Rng, opts: { roots: number; extra: number; pool?: number }): TabTree {
  const mothership = MOTHERSHIPS[rng.int(0, 2)];
  let tree = emptyTabTree(mothership);
  const ids: string[] = [];
  const spawn = (parent: string | null) => {
    const kind = KINDS[rng.int(0, KINDS.length - 1)];
    const id = `t${ids.length}`;
    const r = spawnChild(tree, parent, {
      tab_id: id,
      kind,
      ref: refFor(rng, kind, opts.pool ?? 6),
      mothership,
      activate: false,
    });
    if (!r.ok) throw new Error(r.error.message);
    tree = r.tree;
    ids.push(id);
  };
  for (let i = 0; i < opts.roots; i++) spawn(null);
  for (let i = 0; i < opts.extra; i++) {
    // Bias toward the newest tabs so real depth appears.
    const pick = rng.next() < 0.6 ? ids[ids.length - 1 - rng.int(0, Math.min(3, ids.length - 1))] : ids[rng.int(0, ids.length - 1)];
    spawn(pick);
  }
  return tree;
}

function activate(tree: TabTree, id: string): TabTree {
  const r = setActive(tree, id);
  if (!r.ok) throw new Error(r.error.message);
  return r.tree;
}

/** The pathname part of a tab's route (the ?m= is the router's business). */
function pathOf(tab: TabNode): string | null {
  const route = routeForTab(tab);
  return route === null ? null : route.split("?")[0];
}

describe("(P1) route adoption never orphans a tab", () => {
  it(`${CASES} random forests: activation → its route adopts it; a shown path never seeds`, () => {
    let checked = 0;
    for (let i = 0; i < CASES; i++) {
      const rng = makeRng(SEED + i);
      let tree = randomForest(rng, { roots: rng.int(1, 3), extra: rng.int(0, 40) });
      const ids = Object.keys(tree.nodes);
      const target = ids[rng.int(0, ids.length - 1)];
      const path = pathOf(tree.nodes[target]);
      if (path === null) continue; // a section tab has no route of its own
      // (a) activating the tab and landing on its route adopts it in place.
      const activated = activate(tree, target);
      expect(adoptTabForRoute(activated, path), `case ${i}`).toEqual({ action: "none" });
      // (b) from any other active tab, the route adopts an open tab showing it.
      const other = ids[rng.int(0, ids.length - 1)];
      tree = activate(tree, other);
      const a = adoptTabForRoute(tree, path);
      if (a.action === "activate") {
        expect(tabShowsPath(tree.nodes[a.tabId], path), `case ${i}`).toBe(true);
        // The nearest ancestor of the active tab that shows it, when there is one.
        const ancestry = pathTo(tree, other).slice(0, -1);
        const nearest = [...ancestry].reverse().find((id) => tabShowsPath(tree.nodes[id], path));
        if (nearest) expect(a.tabId, `case ${i}`).toBe(nearest);
      } else {
        // "none" only when the active tab already shows it (or a routeless
        // section scoped under an ancestor that does).
        expect(a.action, `case ${i}`).toBe("none");
        const act = tree.nodes[other];
        const shown =
          tabShowsPath(act, path) ||
          (pathOf(act) === null && pathTo(tree, other).some((id) => tabShowsPath(tree.nodes[id], path)));
        expect(shown, `case ${i}`).toBe(true);
      }
      // (c) a path nothing shows is the only thing that seeds a root.
      expect(adoptTabForRoute(tree, "/read/never-opened").action).toBe("seed");
      checked++;
    }
    expect(checked).toBeGreaterThan(CASES / 2);
  });

  it("scenario: a research tree's reader child stays a child across route changes", () => {
    let tree = emptyTabTree("research");
    const step = (r: ReturnType<typeof spawnChild>) => {
      if (!r.ok) throw new Error(r.error.message);
      tree = r.tree;
    };
    step(spawnChild(tree, null, { tab_id: "root", kind: "research", ref: "/inv/inv-1", mothership: "research" }));
    step(
      spawnChild(tree, "root", {
        tab_id: "child",
        kind: "reader",
        ref: "doc-9",
        mothership: "research",
        origin: { document_id: "doc-9", kind: "reference" },
      }),
    );
    // Its route keeps the tree it belongs to.
    expect(routeForTab(tree.nodes.child)).toBe("/read/doc-9?m=research");
    expect(adoptTabForRoute(tree, "/read/doc-9")).toEqual({ action: "none" });
    // Back to the investigation: its root is adopted, the child untouched.
    expect(adoptTabForRoute(tree, "/inv/inv-1")).toEqual({ action: "activate", tabId: "root" });
    tree = activate(tree, "root");
    // Forward again: the child is adopted, not a new root.
    expect(adoptTabForRoute(tree, "/read/doc-9")).toEqual({ action: "activate", tabId: "child" });
    tree = activate(tree, "child");
    expect(tree.nodes.child.parent_tab_id).toBe("root");
    expect(tree.root_order).toEqual(["root"]);
  });

  it("meta-reading routes never adopt or seed", () => {
    const tree = randomForest(makeRng(SEED), { roots: 2, extra: 10 });
    expect(adoptTabForRoute(tree, "/read/meta-reading")).toEqual({ action: "none" });
    expect(adoptTabForRoute(tree, "/read/meta-reading/asset-1")).toEqual({ action: "none" });
  });
});

describe("(P2) the tree panel is depth-first", () => {
  it(`${CASES} random three-root forests`, () => {
    for (let i = 0; i < CASES; i++) {
      const rng = makeRng(SEED + 10_000 + i);
      const tree = randomForest(rng, { roots: 3, extra: rng.int(0, 60) });
      const rows = flattenTabRows(tree);
      const expected = tree.root_order.flatMap((r) => subtreeIds(tree, r));
      expect(rows.map((r) => r.id), `case ${i}`).toEqual(expected);
      const at = new Map(rows.map((r, idx) => [r.id, idx]));
      for (const [idx, row] of rows.entries()) {
        const node = tree.nodes[row.id];
        expect(row.level, `case ${i}`).toBe(depthOf(tree, row.id));
        const siblings = node.parent_tab_id === null ? tree.root_order : tree.nodes[node.parent_tab_id].child_order;
        expect(row.posinset).toBe(siblings.indexOf(row.id) + 1);
        expect(row.setsize).toBe(siblings.length);
        if (node.parent_tab_id !== null) expect(at.get(node.parent_tab_id)!).toBeLessThan(idx);
        // Contiguous subtree: the next `size - 1` rows are exactly its descendants.
        const sub = subtreeIds(tree, row.id);
        expect(rows.slice(idx, idx + sub.length).map((r) => r.id)).toEqual(sub);
        expect(row.indent).toBe(Math.min(row.level, 6) - 1);
      }
    }
  });

  it("a collapsed branch hides exactly its descendants; a focused subtree re-roots at level 1", () => {
    const rng = makeRng(SEED + 99);
    const tree = randomForest(rng, { roots: 3, extra: 50 });
    const parent = Object.keys(tree.nodes).find((id) => tree.nodes[id].child_order.length > 0)!;
    const hidden = new Set(subtreeIds(tree, parent).slice(1));
    const rows = flattenTabRows(tree, { collapsed: new Set([parent]) });
    expect(rows.some((r) => hidden.has(r.id))).toBe(false);
    expect(rows.find((r) => r.id === parent)!.expanded).toBe(false);
    const focused = flattenTabRows(tree, { focusId: parent });
    expect(focused[0]).toMatchObject({ id: parent, level: 1, posinset: 1, setsize: 1, depth: depthOf(tree, parent) });
    expect(focused.map((r) => r.id)).toEqual(subtreeIds(tree, parent));
  });
});

describe("(P3) labels never show a raw ref", () => {
  const entries = (rng: Rng): (TitleEntry | undefined)[] => [
    undefined,
    { state: "loading" },
    { state: "failed" },
    { state: "known", title: null },
    { state: "known", title: `  Title ${rng.int(0, 999)}  ` },
  ];
  it(`${CASES} random tabs × every title state`, () => {
    for (let i = 0; i < CASES; i++) {
      const rng = makeRng(SEED + 20_000 + i);
      const tree = randomForest(rng, { roots: 1, extra: rng.int(0, 8), pool: 1_000_000 });
      for (const id of Object.keys(tree.nodes)) {
        const tab = tree.nodes[id];
        const parent = tab.parent_tab_id ? tree.nodes[tab.parent_tab_id] : null;
        const rawId = tab.ref.replace(/^\/(inv|write)\//, "").replace(/^section:/, "");
        for (const entry of entries(rng)) {
          const label = labelForTab(tab, parent, entry);
          expect(label.text.trim().length, `case ${i}`).toBeGreaterThan(0);
          expect(label.text, `case ${i}`).not.toContain(rawId);
          expect(label.text).not.toContain("/inv/");
          expect(label.text).not.toContain("section:");
          if (entry?.state === "known" && entry.title) {
            expect(label).toMatchObject({ text: entry.title.trim(), source: "title" });
          } else {
            expect(label.source).toBe("fallback");
            expect(label.text).toMatch(/^(Untitled )?(document|research|draft|section|thread|Document|Research|Draft|Section|Thread)$/);
          }
        }
      }
    }
  });

  it("a passage names a same-surface branch; a title names a different surface", () => {
    let tree = emptyTabTree("reading");
    const step = (r: ReturnType<typeof spawnChild>) => {
      if (!r.ok) throw new Error(r.error.message);
      tree = r.tree;
    };
    step(spawnChild(tree, null, { tab_id: "r", kind: "reader", ref: "doc-1", mothership: "reading" }));
    const anchor = (q: string) => ({ document_id: "doc-1", kind: "footnote" as const, anchor: { document_id: "doc-1", quote: q } });
    step(spawnChild(tree, "r", { tab_id: "fn", kind: "reader", ref: "doc-1", mothership: "reading", origin: anchor("ch. 3, n. 12") }));
    step(spawnChild(tree, "r", { tab_id: "ref", kind: "reader", ref: "doc-2", mothership: "reading", origin: anchor("see Lyell") }));
    const known = (title: string): TitleEntry => ({ state: "known", title });
    expect(labelForTab(tree.nodes.fn, tree.nodes.r, known("Origin of Species")).text).toBe("ch. 3, n. 12");
    expect(labelForTab(tree.nodes.ref, tree.nodes.r, known("Principles of Geology")).text).toBe("Principles of Geology");
    expect(labelForTab(tree.nodes.ref, tree.nodes.r, undefined).text).toBe("see Lyell");
  });
});
