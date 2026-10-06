/**
 * newTab.test.ts — the prefix+c picker's spawn seam.
 *
 * Each behaviour here FAILED while tab.new was `notBuiltYet`: the seam did
 * not exist, so no code path from the key could produce any of these
 * trees. The picker test (NewTabPicker.test.tsx) presses the real key; this
 * file pins what the spawn itself must do.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { spawnNewTab } from "./newTab";
import { titleKey, useTabTitles } from "./tabTitles";
import { useTabTrees } from "./tabTreeStore";

const tabs = () => useTabTrees.getState();

beforeEach(() => {
  tabs().resetTabTrees();
});

describe("spawnNewTab", () => {
  it("files a document as the reading tree's active ROOT tab and asks to show it", async () => {
    await spawnNewTab({ kind: "reader", ref: "doc-nt-1", title: "A Modest Proposal" });
    const tree = tabs().trees.reading;
    expect(tree).toBeTruthy();
    const id = "root:reader:doc-nt-1";
    expect(Object.hasOwn(tree!.nodes, id)).toBe(true);
    expect(tree!.nodes[id].parent_tab_id).toBeNull();
    expect(tree!.active_tab_id).toBe(id);
    // A user activation requests the navigation; the strip performs it.
    expect(tabs().navIntent).toMatchObject({ mothership: "reading", tabId: id });
    // The other motherships are untouched.
    expect(tabs().trees.research).toBeNull();
    expect(tabs().trees.writing).toBeNull();
  });

  it("files an investigation under research with the route-ref shape", async () => {
    await spawnNewTab({ kind: "research", ref: "/inv/inv-nt-1", title: "What killed the dodo?" });
    const tree = tabs().trees.research;
    const id = "root:research:/inv/inv-nt-1";
    expect(Object.hasOwn(tree!.nodes, id)).toBe(true);
    expect(tree!.nodes[id].kind).toBe("research");
    expect(tree!.active_tab_id).toBe(id);
  });

  it("a surface already open is ACTIVATED, never duplicated (the cross-pane rule)", async () => {
    await spawnNewTab({ kind: "reader", ref: "doc-nt-2", title: "A Doll's House" });
    const before = Object.keys(tabs().trees.reading!.nodes).length;
    // Wander away, then ask for the same surface again.
    await spawnNewTab({ kind: "reader", ref: "doc-nt-2b", title: "Another Book" });
    expect(tabs().trees.reading!.active_tab_id).not.toBe("root:reader:doc-nt-2");
    await spawnNewTab({ kind: "reader", ref: "doc-nt-2", title: "A Doll's House" });
    const tree = tabs().trees.reading!;
    expect(Object.keys(tree.nodes).length).toBe(before + 1); // only the wander added one
    expect(tree.active_tab_id).toBe("root:reader:doc-nt-2");
  });

  it("a surface only CLOSED takes a fresh id, the closed one staying in history", async () => {
    await spawnNewTab({ kind: "reader", ref: "doc-nt-3", title: "Lyell" });
    tabs().closeTabById("reading", "root:reader:doc-nt-3", "prune");
    // The close is held for the undo window; commit it by force through the
    // model: the tab leaves the open set either way.
    expect(Object.hasOwn(tabs().trees.reading!.nodes, "root:reader:doc-nt-3")).toBe(false);
    await spawnNewTab({ kind: "reader", ref: "doc-nt-3", title: "Lyell" });
    const tree = tabs().trees.reading!;
    expect(Object.hasOwn(tree.nodes, "root:reader:doc-nt-3~2")).toBe(true);
    expect(tree.active_tab_id).toBe("root:reader:doc-nt-3~2");
  });

  it("shows the given title at once (the strip's resolver refines it later)", async () => {
    await spawnNewTab({ kind: "reader", ref: "doc-nt-4", title: "Principles of Geology" });
    expect(useTabTitles.getState().entries[titleKey("reader", "doc-nt-4")]).toEqual({
      state: "known",
      title: "Principles of Geology",
    });
  });
});
