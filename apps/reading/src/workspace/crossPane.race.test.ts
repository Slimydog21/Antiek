import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { waitFor } from "@testing-library/react";

import { toast } from "../components/lemon/LemonToast";
import { openDocumentInLeftPane, setOpenDocumentHandler } from "./crossPane";
import { adoptRoute } from "./routeSync";
import {
  createInMemoryTabTreeAdapter,
  emptyTabTree,
  spawnChild,
  toSnapshot,
  type TabTreeSnapshot,
} from "./tabTree";
import { useTabTrees } from "./tabTreeStore";

const tabs = () => useTabTrees.getState();
const origin = { from: "companion", investigationId: "agent-1", agentKind: "research" };

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

function go(path: string) {
  window.history.pushState({ key: path }, "", path);
}

function holdLoad() {
  const response = deferred<TabTreeSnapshot>();
  const backing = createInMemoryTabTreeAdapter();
  const adapter = { ...backing, load: vi.fn(() => response.promise) };
  tabs().setTabTreeAdapter(adapter);
  return { response, adapter };
}

function twoParents() {
  const a = spawnChild(emptyTabTree("research"), null, {
    tab_id: "parent-a", kind: "research", ref: "A", mothership: "research", activate: true,
  });
  if (!a.ok) throw new Error(a.error.message);
  const b = spawnChild(a.tree, null, {
    tab_id: "parent-b", kind: "research", ref: "B", mothership: "research", activate: true,
  });
  if (!b.ok) throw new Error(b.error.message);
  return b.tree;
}

async function resultTab() {
  return waitFor(() => {
    const tab = Object.values(tabs().trees.research?.nodes ?? {}).find((node) => node.ref === "doc-9");
    expect(tab).toBeDefined();
    if (!tab) throw new Error("The opened document is missing");
    return tab;
  });
}

beforeEach(() => {
  tabs().resetTabTrees();
  setOpenDocumentHandler(null);
  vi.spyOn(toast, "info").mockReturnValue(0);
  vi.spyOn(toast, "undo").mockReturnValue(0);
  go("/inv/A");
});

afterEach(() => {
  tabs().resetTabTrees();
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/");
});

describe("cross-pane requests keep their original route and parent", () => {
  it("an unloaded tree seeds the original route after a mode switch, without importing the new route", async () => {
    const { response } = holdLoad();
    openDocumentInLeftPane("doc-9", origin);
    go("/read/Book");
    response.resolve(toSnapshot(emptyTabTree("research")));
    const child = await resultTab();
    const tree = tabs().trees.research!;
    expect(child.parent_tab_id).toBe("root:research:/inv/A");
    expect(tree.nodes[child.parent_tab_id!].ref).toBe("/inv/A");
    expect(Object.values(tree.nodes).some((node) => node.ref === "Book")).toBe(false);
    expect(tree.active_tab_id).toBeNull();
    expect(tabs().trees.reading).toBeNull();
    expect(tabs().navIntent).toBeNull();
    expect(window.location.pathname).toBe("/read/Book");
    expect(toast.info).toHaveBeenCalledOnce();
  });

  it("a deferred load preserves same-mode navigation and files under the original route", async () => {
    const { response } = holdLoad();
    openDocumentInLeftPane("doc-9", origin);
    go("/inv/B");
    response.resolve(toSnapshot(twoParents()));
    const child = await resultTab();
    expect(child.parent_tab_id).toBe("parent-a");
    expect(tabs().trees.research?.active_tab_id).toBe("parent-b");
    expect(tabs().navIntent).toBeNull();
    expect(window.location.pathname).toBe("/inv/B");
    expect(toast.info).toHaveBeenCalledOnce();
  });

  it("captures an already-loaded parent before same-mode navigation on the same tick", async () => {
    await tabs().ensureMothership("research");
    adoptRoute("research", "/inv/A");
    const parent = tabs().trees.research!.active_tab_id;
    openDocumentInLeftPane("doc-9", origin);
    go("/inv/B");
    adoptRoute("research", "/inv/B");
    const current = tabs().trees.research!.active_tab_id;
    const child = await resultTab();
    expect(child.parent_tab_id).toBe(parent);
    expect(tabs().trees.research?.active_tab_id).toBe(current);
    expect(tabs().navIntent).toBeNull();
  });

  it("keeps a find as a root when its known parent is removed, without recreating the closed parent or activating", async () => {
    await tabs().ensureMothership("research");
    adoptRoute("research", "/inv/A");
    const parent = tabs().trees.research!.active_tab_id!;
    openDocumentInLeftPane("doc-9", origin);
    tabs().closeTabById("research", parent, "lift_children");
    const afterClose = tabs().navIntent;
    const child = await resultTab();
    expect(child.parent_tab_id).toBeNull();
    expect(tabs().trees.research?.root_order).toEqual([child.tab_id]);
    expect(tabs().trees.research?.active_tab_id).toBeNull();
    expect(tabs().trees.research?.nodes[parent]).toBeUndefined();
    expect(tabs().navIntent).toBe(afterClose);
    expect(toast.info).toHaveBeenCalledOnce();
  });

  it("still activates an on-time open after initially loading and seeding its original route", async () => {
    const { response } = holdLoad();
    openDocumentInLeftPane("doc-9", origin, "Source title");
    response.resolve(toSnapshot(emptyTabTree("research")));
    const child = await resultTab();
    expect(child.parent_tab_id).toBe("root:research:/inv/A");
    expect(child.opened_by).toEqual({ thread_id: "agent-1", agent_kind: "research" });
    expect(tabs().trees.research?.active_tab_id).toBe(child.tab_id);
    expect(tabs().navIntent?.tabId).toBe(child.tab_id);
    expect(toast.info).not.toHaveBeenCalled();
  });

  it("reuses a late result already under the original parent without selecting or duplicating it", async () => {
    await tabs().ensureMothership("research");
    adoptRoute("research", "/inv/A");
    const parent = tabs().trees.research!.active_tab_id!;
    tabs().spawnTab("research", parent, {
      tab_id: "existing-find", kind: "reader", ref: "doc-9", mothership: "research", activate: false,
    });
    openDocumentInLeftPane("doc-9", origin);
    go("/inv/B");
    adoptRoute("research", "/inv/B");
    const current = tabs().trees.research!.active_tab_id;
    await waitFor(() => expect(toast.info).toHaveBeenCalledOnce());
    expect(tabs().trees.research!.nodes[parent].child_order).toEqual(["existing-find"]);
    expect(tabs().trees.research!.active_tab_id).toBe(current);
    expect(tabs().navIntent).toBeNull();
  });

  it.each(["replacement", "same adapter"])("an old load cannot populate a reset store (%s), but its find remains explicitly openable", async (reset) => {
    const { response, adapter } = holdLoad();
    openDocumentInLeftPane("doc-9", origin);
    tabs().setTabTreeAdapter(reset === "replacement" ? createInMemoryTabTreeAdapter() : adapter);
    response.resolve(toSnapshot(twoParents()));
    await waitFor(() => expect(toast.info).toHaveBeenCalledOnce());
    expect(tabs().trees.research).toBeNull();
    expect(tabs().navIntent).toBeNull();
    const options = vi.mocked(toast.info).mock.calls[0][1];
    expect(options).toEqual(expect.objectContaining({ action: expect.objectContaining({ label: "Open document" }) }));
    if (!options || typeof options === "number" || !options.action) throw new Error("Missing explicit open action");
    tabs().setTabTreeAdapter(createInMemoryTabTreeAdapter());
    options.action.run();
    expect((await resultTab()).ref).toBe("doc-9");
  });
});
