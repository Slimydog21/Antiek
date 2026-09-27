/**
 * tabIdCallers.test.tsx — A2b items 1 and 2 at every place that opens a tab:
 *  - every tab the route sync, the cross-pane seam and the Write sync open
 *    carries a legal opaque id (THREAD-CONTRACT §1.6: 1 to 64 of
 *    [A-Za-z0-9_-]), however deep the branch goes;
 *  - finding an open tab (duplicate-open focuses the existing view; the
 *    Write sync re-attaches its sections; the route sync adopts) works by the
 *    tab's fields over a tree whose ids say nothing, as a server tree's do.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

import type { DeliverableDetailResponse } from "../lib/api";
import { openDocumentInLeftPane } from "./crossPane";
import { adoptRoute } from "./routeSync";
import { sectionRefOf } from "./sectionRef";
import {
  closeTab,
  createInMemoryTabTreeAdapter,
  emptyTabTree,
  spawnChild,
  toSnapshot,
  type TabTree,
} from "./tabTree";
import { useTabTrees } from "./tabTreeStore";
import { useWriteTreeSync } from "./writeTreeSync";

const LEGAL = /^[A-Za-z0-9_-]{1,64}$/;
const tabs = () => useTabTrees.getState();
const flush = async (n = 8) => {
  for (let i = 0; i < n; i++) await act(async () => {});
};

function everyId(tree: TabTree): string[] {
  return [...Object.keys(tree.nodes), ...Object.keys(tree.history)];
}

/** Seed the in-memory adapter's row with `tree`, so the store loads it. */
async function serverHolds(tree: TabTree) {
  const adapter = createInMemoryTabTreeAdapter();
  const r = await adapter.save("default", tree.mothership, toSnapshot(tree));
  if (r.status !== "saved") throw new Error(`seed refused: ${JSON.stringify(r)}`);
  tabs().setTabTreeAdapter(adapter);
  await tabs().ensureMothership(tree.mothership);
  return adapter;
}

beforeEach(() => {
  tabs().resetTabTrees();
  window.history.replaceState({}, "", "/");
});
afterEach(() => {
  vi.useRealTimers();
  tabs().resetTabTrees();
});

describe("every opened tab carries a legal opaque id (A2b item 1)", () => {
  it("the route sync: a root and a 12-deep branch chain stay within 1-64 of [A-Za-z0-9_-]", async () => {
    await tabs().ensureMothership("reading");
    adoptRoute("reading", "/read/doc-0");
    for (let depth = 1; depth <= 12; depth++) {
      const parentTabId = tabs().trees.reading!.active_tab_id!;
      adoptRoute("reading", `/read/doc-${depth}-with-a-long-document-identifier`, {
        parentTabId,
        mothership: "reading",
        origin: { document_id: `doc-${depth - 1}`, kind: "reference" },
      });
    }
    const tree = tabs().trees.reading!;
    expect(Object.keys(tree.nodes)).toHaveLength(13);
    for (const id of everyId(tree)) {
      expect(id).toMatch(LEGAL);
      expect(id).not.toContain("doc-");
      expect(id).not.toContain("reader");
    }
  });

  it("the route sync reseeds a closed surface under a new legal id, never a suffix", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    await tabs().ensureMothership("research");
    adoptRoute("research", "/inv/inv-1");
    const first = tabs().trees.research!.active_tab_id!;
    tabs().closeActiveTab("research", "prune");
    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });
    adoptRoute("research", "/inv/inv-1");
    const second = tabs().trees.research!.active_tab_id!;
    expect(second).not.toBe(first);
    expect(second).toMatch(LEGAL);
    expect(second.startsWith(first)).toBe(false);
  });

  it("the cross-pane seam opens its document under a legal id", async () => {
    window.history.replaceState({}, "", "/read/doc-1");
    await tabs().ensureMothership("reading");
    adoptRoute("reading", "/read/doc-1");
    openDocumentInLeftPane("doc-2", { from: "companion" });
    await flush();
    const tree = tabs().trees.reading!;
    expect(Object.keys(tree.nodes)).toHaveLength(2);
    for (const id of everyId(tree)) expect(id).toMatch(LEGAL);
  });

  it("the Write sync opens the piece and its sections under legal ids", async () => {
    await tabs().ensureMothership("writing");
    renderHook(() => useWriteTreeSync(piece("A", ["s1", "s2"])));
    await flush();
    const tree = tabs().trees.writing!;
    expect(Object.keys(tree.nodes)).toHaveLength(3);
    for (const id of everyId(tree)) expect(id).toMatch(LEGAL);
  });
});

function piece(id: string, sections: string[]): DeliverableDetailResponse {
  return {
    deliverable_id: id,
    title: `Piece ${id}`,
    investigation_root_id: null,
    sections: sections.map((s, i) => ({ section_id: s, section_index: i, title: s })),
  } as unknown as DeliverableDetailResponse;
}

/** A writing tree as the server would hand it back: opaque ids. */
function serverWritingTree(opts: { closeS2?: boolean } = {}): TabTree {
  let t = emptyTabTree("writing");
  const add = (parent: string | null, tab_id: string, ref: string) => {
    const r = spawnChild(t, parent, { tab_id, kind: "document", ref, mothership: "writing", activate: false });
    if (!r.ok) throw new Error(r.error.message);
    t = r.tree;
  };
  add(null, "tBODYaaaaaaaaaaaaaaaaaa", "/write/A");
  add("tBODYaaaaaaaaaaaaaaaaaa", "tSECTION1aaaaaaaaaaaaaa", sectionRefOf("s1"));
  add("tBODYaaaaaaaaaaaaaaaaaa", "tSECTION2aaaaaaaaaaaaaa", sectionRefOf("s2"));
  if (opts.closeS2) {
    const c = closeTab(t, "tSECTION2aaaaaaaaaaaaaa", "prune", "2026-09-27T00:00:00Z");
    if (!c.ok) throw new Error(c.error.message);
    t = c.tree;
  }
  return t;
}

describe("lookups go by the tab's fields, never by its id (A2b item 2)", () => {
  it("the Write sync re-attaches a server tree's section tabs instead of opening duplicates", async () => {
    await serverHolds(serverWritingTree());
    renderHook(() => useWriteTreeSync(piece("A", ["s1", "s2"])));
    await flush();
    const tree = tabs().trees.writing!;
    expect(Object.keys(tree.nodes).sort()).toEqual(["tBODYaaaaaaaaaaaaaaaaaa", "tSECTION1aaaaaaaaaaaaaa", "tSECTION2aaaaaaaaaaaaaa"]);
    expect(tree.nodes.tBODYaaaaaaaaaaaaaaaaaa.child_order).toEqual(["tSECTION1aaaaaaaaaaaaaa", "tSECTION2aaaaaaaaaaaaaa"]);
  });

  it("a section the operator closed stays closed, found in history by its fields", async () => {
    await serverHolds(serverWritingTree({ closeS2: true }));
    renderHook(() => useWriteTreeSync(piece("A", ["s1", "s2"])));
    await flush();
    const tree = tabs().trees.writing!;
    expect(tree.nodes.tBODYaaaaaaaaaaaaaaaaaa.child_order).toEqual(["tSECTION1aaaaaaaaaaaaaa"]);
    expect(Object.keys(tree.nodes)).toHaveLength(2);
  });

  it("a new section of a server tree's piece opens under the body it re-attached to", async () => {
    await serverHolds(serverWritingTree());
    renderHook(() => useWriteTreeSync(piece("A", ["s1", "s2", "s3"])));
    await flush();
    const tree = tabs().trees.writing!;
    const body = tree.nodes.tBODYaaaaaaaaaaaaaaaaaa;
    expect(body.child_order).toHaveLength(3);
    const added = tree.nodes[body.child_order[2]];
    expect(added.ref).toBe(sectionRefOf("s3"));
    expect(added.tab_id).toMatch(LEGAL);
  });

  it("the cross-pane seam focuses the open tab for a document already open under the active tab", async () => {
    let t = emptyTabTree("reading");
    const r1 = spawnChild(t, null, { tab_id: "tROOTaaaaaaaaaaaaaaaaaa", kind: "reader", ref: "doc-1", mothership: "reading" });
    if (!r1.ok) throw new Error(r1.error.message);
    t = r1.tree;
    const r2 = spawnChild(t, "tROOTaaaaaaaaaaaaaaaaaa", { tab_id: "tCHILDaaaaaaaaaaaaaaaaa", kind: "reader", ref: "doc-2", mothership: "reading", activate: false });
    if (!r2.ok) throw new Error(r2.error.message);
    window.history.replaceState({}, "", "/read/doc-1");
    await serverHolds(r2.tree);
    openDocumentInLeftPane("doc-2", { from: "companion" });
    await flush();
    const tree = tabs().trees.reading!;
    expect(Object.keys(tree.nodes)).toHaveLength(2);
    expect(tree.active_tab_id).toBe("tCHILDaaaaaaaaaaaaaaaaa");
  });

  it("the route sync adopts the open tab showing the route over a tree of opaque ids", async () => {
    let t = emptyTabTree("reading");
    const r1 = spawnChild(t, null, { tab_id: "tROOTaaaaaaaaaaaaaaaaaa", kind: "reader", ref: "doc-1", mothership: "reading" });
    if (!r1.ok) throw new Error(r1.error.message);
    t = r1.tree;
    const r2 = spawnChild(t, "tROOTaaaaaaaaaaaaaaaaaa", { tab_id: "tCHILDaaaaaaaaaaaaaaaaa", kind: "reader", ref: "doc-2", mothership: "reading", activate: false });
    if (!r2.ok) throw new Error(r2.error.message);
    await serverHolds(r2.tree);
    adoptRoute("reading", "/read/doc-2");
    expect(tabs().trees.reading!.active_tab_id).toBe("tCHILDaaaaaaaaaaaaaaaaa");
    expect(Object.keys(tabs().trees.reading!.nodes)).toHaveLength(2);
  });
});
