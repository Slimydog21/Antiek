/**
 * tabTree.sides.test.ts — A2a item 1: the tab node carries the THREAD-CONTRACT
 * §1.6 rev 7/8.8 fields (`side`, `title`, `opened_by?`, `pane?`), and the
 * branch origins `agent` and `derivation` (Part 2 §2.2).
 *
 *  - every spawn the client makes today is a left tab;
 *  - a child inherits its parent's side, except `agent` and `derivation`
 *    children, which are always left;
 *  - an `agent` origin without `opened_by` is refused (`invalid_origin`),
 *    mirroring the server's `422 tab_origin_invalid`;
 *  - a kind the node's side does not admit is refused (§1.6 kinds by side).
 */
import { describe, expect, it } from "vitest";

import {
  checkInvariants,
  emptyTabTree,
  fromSnapshot,
  spawnChild,
  toSnapshot,
  type SpawnInput,
  type TabTree,
} from "./tabTree";

function spawn(tree: TabTree, parent: string | null, input: Partial<SpawnInput> & { tab_id: string }): TabTree {
  const r = spawnChild(tree, parent, { kind: "reader", ref: `doc-${input.tab_id}`, mothership: "research", ...input });
  if (!r.ok) throw new Error(`${r.error.code}: ${r.error.message}`);
  return r.tree;
}

describe("tab node fields (contract §1.6 rev 7, Part 2 §2.2)", () => {
  it("an ordinary spawn is a left tab with an empty title unless one is given", () => {
    let t = spawn(emptyTabTree("research"), null, { tab_id: "a" });
    t = spawn(t, "a", { tab_id: "b", title: "Load tables, 1998" });
    expect(t.nodes.a.side).toBe("left");
    expect(t.nodes.a.title).toBe("");
    expect(t.nodes.b.side).toBe("left");
    expect(t.nodes.b.title).toBe("Load tables, 1998");
    expect(checkInvariants(t)).toEqual([]);
  });

  it("a child inherits a right parent's side; agent and derivation children are always left", () => {
    let t = spawn(emptyTabTree("research"), null, { tab_id: "agent", kind: "research", ref: "inv-1", side: "right" });
    t = spawn(t, "agent", { tab_id: "same-side", kind: "dialogue", ref: "dlg-1" });
    t = spawn(t, "agent", {
      tab_id: "opened",
      kind: "reader",
      ref: "doc-2",
      origin: { document_id: "doc-2", kind: "agent" },
      opened_by: { thread_id: "inv-1", agent_kind: "research" },
    });
    t = spawn(t, "agent", {
      tab_id: "derived",
      kind: "document",
      ref: "/write/d-1",
      origin: { document_id: "doc-2", kind: "derivation" },
    });
    expect(t.nodes.agent.side).toBe("right");
    expect(t.nodes["same-side"].side).toBe("right");
    expect(t.nodes.opened.side).toBe("left");
    expect(t.nodes.opened.opened_by).toEqual({ thread_id: "inv-1", agent_kind: "research" });
    expect(t.nodes.derived.side).toBe("left");
    expect(checkInvariants(t)).toEqual([]);
  });

  it("a left parent's children stay left whatever side the input asks for", () => {
    let t = spawn(emptyTabTree("research"), null, { tab_id: "p" });
    t = spawn(t, "p", { tab_id: "c", side: "right" });
    expect(t.nodes.c.side).toBe("left");
  });

  it("refuses an agent origin without opened_by (the server's 422 tab_origin_invalid)", () => {
    const t = spawn(emptyTabTree("research"), null, { tab_id: "p" });
    const r = spawnChild(t, "p", {
      tab_id: "orphan",
      kind: "reader",
      ref: "doc-3",
      mothership: "research",
      origin: { document_id: "doc-3", kind: "agent" },
    });
    expect(r.ok ? "ok" : r.error.code).toBe("tab_origin_invalid");
  });

  it("refuses a kind the node's side does not admit", () => {
    const left = spawnChild(emptyTabTree("research"), null, { tab_id: "i", kind: "island", ref: "inv-9", mothership: "research" });
    expect(left.ok ? "ok" : left.error.code).toBe("kind_side_mismatch");
    const right = spawnChild(emptyTabTree("research"), null, {
      tab_id: "r",
      kind: "reader",
      ref: "doc-1",
      mothership: "research",
      side: "right",
    });
    expect(right.ok ? "ok" : right.error.code).toBe("kind_side_mismatch");
  });

  it("research is admitted on both sides (rev 8.8)", () => {
    const left = spawn(emptyTabTree("research"), null, { tab_id: "l", kind: "research", ref: "inv-1" });
    const right = spawn(left, null, { tab_id: "r", kind: "research", ref: "inv-2", side: "right" });
    expect(right.nodes.l.side).toBe("left");
    expect(right.nodes.r.side).toBe("right");
  });

  it("pane and opened_by survive the model's own snapshot round trip", () => {
    let t = spawn(emptyTabTree("research"), null, { tab_id: "p", pane: { docked_kind: "findings", docked_ref: "fld-1" } });
    t = spawn(t, "p", {
      tab_id: "a",
      origin: { document_id: "doc-a", kind: "agent" },
      opened_by: { thread_id: "inv-1", agent_kind: "dialogue" },
    });
    const back = fromSnapshot(JSON.parse(JSON.stringify(toSnapshot(t))));
    if (!back.ok) throw new Error(back.error.message);
    expect(back.tree).toStrictEqual(t);
    expect(back.tree.nodes.p.pane).toEqual({ docked_kind: "findings", docked_ref: "fld-1" });
  });

  it("fromSnapshot refuses an agent node without opened_by", () => {
    const t = spawn(emptyTabTree("research"), null, { tab_id: "p" });
    const snap = toSnapshot(t);
    snap.tree.nodes.p = { ...snap.tree.nodes.p, branch_origin: { document_id: "d", kind: "agent" } };
    const r = fromSnapshot(snap);
    expect(r.ok ? "ok" : r.error.code).toBe("invalid_snapshot");
  });
});
