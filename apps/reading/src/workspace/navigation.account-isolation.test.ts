import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setWorkspaceOwner } from "../lib/accountWorkspaceOwner";
import type { DeliverableDetailResponse } from "../lib/api";
import { toast } from "../components/lemon/LemonToast";
import { openDocumentInLeftPane, setOpenDocumentHandler } from "./crossPane";
import { spawnNewTab } from "./newTab";
import { createInMemoryTabTreeAdapter } from "./tabTree";
import { useTabTrees } from "./tabTreeStore";
import { titleKey, useTabTitles } from "./tabTitles";
import { useWriteTreeSync } from "./writeTreeSync";

const tabs = () => useTabTrees.getState();
const DETAIL: DeliverableDetailResponse = {
  deliverable_id: "a-piece", title: "A private title", deliverable_kind: "general_essay",
  status: "draft", investigation_root_id: null, sections: [],
};
function heldAdapter() {
  let release: () => void = () => { throw new Error("gate not constructed"); };
  const gate = new Promise<void>((done) => { release = done; });
  const backing = createInMemoryTabTreeAdapter();
  tabs().setTabTreeAdapter({ ...backing, load: async (project, mothership) => {
    if (project === "default") await gate;
    return backing.load(project, mothership);
  } });
  return release;
}
beforeEach(() => {
  setWorkspaceOwner(null);
  window.localStorage.clear();
  setWorkspaceOwner("account-a");
  tabs().resetTabTrees();
  setOpenDocumentHandler(null);
  window.history.replaceState({}, "", "/");
  vi.spyOn(toast, "info").mockReturnValue(0);
});
afterEach(() => { cleanup(); setWorkspaceOwner(null); vi.restoreAllMocks(); });

describe("async navigation keeps its authenticated owner", () => {
  it("preserves a same-owner project change while a new-tab load is deferred", async () => {
    const release = heldAdapter();
    const pending = spawnNewTab({ kind: "reader", ref: "a-document", title: "A private title" });
    tabs().selectProject("same-owner-project");
    release();
    await pending;
    expect(tabs().projectId).toBe("same-owner-project");
    expect(Object.values(tabs().trees.reading?.nodes ?? {}).some((node) => node.ref === "a-document")).toBe(true);
    expect(useTabTitles.getState().entries[titleKey("reader", "a-document")]).toEqual({ state: "known", title: "A private title" });
  });

  it("cannot refile an A new-tab target/title into B after a deferred load", async () => {
    const release = heldAdapter();
    const pending = spawnNewTab({ kind: "reader", ref: "a-document", title: "A private title" });
    setWorkspaceOwner("account-b");
    await tabs().ensureMothership("reading");
    release();
    await pending;
    expect(Object.values(tabs().trees.reading?.nodes ?? {}).some((node) => node.ref === "a-document")).toBe(false);
    expect(useTabTitles.getState().entries[titleKey("reader", "a-document")]).toBeUndefined();
  });

  it("does not retain an old cross-pane offer or title after account replacement", async () => {
    const release = heldAdapter();
    const loaded = tabs().ensureMothership("research");
    openDocumentInLeftPane("a-document", { from: "companion", investigationId: "a-thread", agentKind: "research" }, "A private title");
    setWorkspaceOwner("account-b");
    await tabs().ensureMothership("research");
    await act(async () => { release(); await loaded; });
    expect(Object.values(tabs().trees.research?.nodes ?? {}).some((node) => node.ref === "a-document")).toBe(false);
    expect(useTabTitles.getState().entries[titleKey("reader", "a-document")]).toBeUndefined();
    expect(toast.info).not.toHaveBeenCalled();
  });

  it.each([false, true])("Write sync after deferred load respects account replacement=%s", async (replace) => {
    const release = heldAdapter();
    const loaded = tabs().ensureMothership("writing");
    renderHook(() => useWriteTreeSync(DETAIL));
    if (replace) {
      setWorkspaceOwner("account-b");
      await tabs().ensureMothership("writing");
    }
    await act(async () => { release(); await loaded; });
    expect(Object.values(tabs().trees.writing?.nodes ?? {}).some((node) => node.ref === "/write/a-piece")).toBe(!replace);
    const title = useTabTitles.getState().entries[titleKey("document", "/write/a-piece")];
    expect(title).toEqual(replace ? undefined : { state: "known", title: "A private title" });
  });
});
