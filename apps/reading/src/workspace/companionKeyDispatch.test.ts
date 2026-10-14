import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  awaitWorkspaceOwnerSession,
  resumeWorkspaceOwner,
  setWorkspaceOwner,
  subscribeWorkspaceOwnerAdmission,
  suspendWorkspaceOwner,
  workspaceOwnerSession,
} from "../lib/accountWorkspaceOwner";
import { useCompanion } from "./companionStore";
import { companionHandle } from "./companionHandle";
import { createActionHandlers } from "./shortcuts";
import { useTabTrees } from "./tabTreeStore";
import { disablePersistence, useWorkspace } from "./WorkspaceStore";
import { useWriteOutline } from "./writeOutlineStore";

// Real local stores and the canonical owner bridge; this UNIT fixture does
// not establish an account, provider, agent response, or server admission.
const handlers = createActionHandlers(vi.fn());
const comp = () => useCompanion.getState();
const ws = () => useWorkspace.getState();
const keys = ["tab.next", "tab.close", "tab.reopen"] as const;

function rightPane() {
  ws().reset();
  ws().setLayoutPreset("omarchy-inset");
  ws().setFocusedPane("right");
  window.history.replaceState(null, "", "/read/unit-document");
}

function tabs() {
  comp().reset();
  const first = comp().openAgentTab({ kind: "research-thread", investigationId: "unit-first" });
  const second = comp().openAgentTab({ kind: "research-thread", investigationId: "unit-second" });
  const third = comp().openAgentTab({ kind: "research-thread", investigationId: "unit-third" });
  comp().activateAgentTab(first);
  return { first, second, third };
}

function withRetired() {
  const ids = tabs();
  comp().closeAgentTabWithUndo(ids.third);
  return ids;
}

beforeEach(async () => {
  disablePersistence();
  setWorkspaceOwner(null);
  setWorkspaceOwner("unit-companion-A");
  await awaitWorkspaceOwnerSession(workspaceOwnerSession());
  rightPane();
  comp().reset();
  useWriteOutline.getState().reset();
});

afterEach(async () => {
  try {
    await vi.dynamicImportSettled();
    comp().reset();
    ws().reset();
    useWriteOutline.getState().reset();
    useTabTrees.getState().resetTabTrees();
    window.history.replaceState(null, "", "/");
  } finally {
    setWorkspaceOwner(null);
  }
});

describe("companion keys use the pane present at the keystroke", () => {
  it("does not acquire a later store when the loaded-store handle is absent", async () => {
    tabs();
    const mounted = comp();
    const store = companionHandle.store;
    companionHandle.store = null;
    try {
      handlers["tab.next"]();
      companionHandle.store = store;
      await vi.dynamicImportSettled();
      expect(comp()).toBe(mounted);
    } finally {
      companionHandle.store = store;
    }
  });

  it("cycles next synchronously in the already loaded pane", () => {
    const { second } = tabs();
    handlers["tab.next"]();
    expect(comp().activeTabId).toBe(second);
  });

  it("cycles previous synchronously with wraparound", () => {
    const { third } = tabs();
    handlers["tab.prev"]();
    expect(comp().activeTabId).toBe(third);
  });

  it("applies each rapid next key before the following key", () => {
    const { first, second, third } = tabs();
    handlers["tab.next"]();
    expect(comp().activeTabId).toBe(second);
    handlers["tab.next"]();
    expect(comp().activeTabId).toBe(third);
    handlers["tab.next"]();
    expect(comp().activeTabId).toBe(first);
  });

  it("closes the current active view synchronously and preserves Undo history", () => {
    const { first, second, third } = tabs();
    handlers["tab.close"]();
    expect(comp().tabs.map((tab) => tab.id)).toEqual([second, third]);
    expect(comp().retired.map(({ tab }) => tab.id)).toEqual([first]);
  });

  it("reopens the current retired view synchronously in its original order", () => {
    const { first, second, third } = withRetired();
    handlers["tab.reopen"]();
    expect(comp().tabs.map((tab) => tab.id)).toEqual([first, second, third]);
    expect(comp().activeTabId).toBe(third);
    expect(comp().retired).toEqual([]);
  });

  it.each(keys)("%s never later consumes replacement account state", async (key) => {
    withRetired();
    handlers[key]();
    setWorkspaceOwner("unit-companion-B");
    rightPane();
    withRetired();
    const replacement = comp();
    await vi.dynamicImportSettled();
    expect(comp()).toBe(replacement);
  });

  it("does not reuse an A token after A-B-A replacement", async () => {
    tabs();
    handlers["tab.next"]();
    setWorkspaceOwner("unit-companion-B");
    setWorkspaceOwner("unit-companion-A");
    rightPane();
    tabs();
    const replacement = comp();
    await vi.dynamicImportSettled();
    expect(comp()).toBe(replacement);
  });

  it("does not defer a key into another selected project's replacement rows", async () => {
    useTabTrees.getState().selectProject("unit-project-A");
    tabs();
    handlers["tab.next"]();
    useTabTrees.getState().selectProject("unit-project-B");
    tabs();
    const replacement = comp();
    await vi.dynamicImportSettled();
    expect(comp()).toBe(replacement);
  });

  it("has no pending cycle after focus moves to the left pane", async () => {
    const { second } = tabs();
    handlers["tab.next"]();
    expect(comp().activeTabId).toBe(second);
    ws().setFocusedPane("left");
    comp().activateAgentTab(tabs().first);
    const replacement = comp();
    await vi.dynamicImportSettled();
    expect(comp()).toBe(replacement);
  });

  it.each(keys)("%s refuses a suspended owner without discarding mounted tabs", async (key) => {
    withRetired();
    suspendWorkspaceOwner();
    const mounted = comp();
    handlers[key]();
    await vi.dynamicImportSettled();
    expect(comp()).toBe(mounted);
  });

  it("does not queue a suspended key; a fresh key works after same-token confirmation", async () => {
    const { first, second } = tabs();
    const owner = workspaceOwnerSession();
    suspendWorkspaceOwner();
    const mounted = comp();
    handlers["tab.next"]();
    await vi.dynamicImportSettled();
    expect(comp()).toBe(mounted);
    expect(resumeWorkspaceOwner(owner)).toBe(true);
    await awaitWorkspaceOwnerSession(owner);
    expect(comp().activeTabId).toBe(first);
    handlers["tab.next"]();
    expect(comp().activeTabId).toBe(second);
  });

  it("refuses an unknown owner", async () => {
    setWorkspaceOwner(null);
    rightPane();
    tabs();
    const unknown = comp();
    handlers["tab.next"]();
    await vi.dynamicImportSettled();
    expect(comp()).toBe(unknown);
  });

  it("refuses failed canonical admission", async () => {
    tabs();
    const unsubscribe = subscribeWorkspaceOwnerAdmission(() => { throw new Error("unit admission failure"); });
    try {
      expect(() => suspendWorkspaceOwner()).toThrow("Workspace owner admission failed");
    } finally {
      unsubscribe();
    }
    const failed = comp();
    handlers["tab.next"]();
    await vi.dynamicImportSettled();
    expect(comp()).toBe(failed);
  });

  it("preserves Writing block precedence and refuses agent close/reopen there", async () => {
    tabs();
    window.history.replaceState(null, "", "/write/unit-piece");
    useWriteOutline.getState().setBlocks(["unit-block-A", "unit-block-B"]);
    const agents = comp();
    handlers["tab.next"]();
    expect(useWriteOutline.getState().activeBlockId).toBe("unit-block-B");
    handlers["tab.close"]();
    handlers["tab.reopen"]();
    await vi.dynamicImportSettled();
    expect(comp()).toBe(agents);
  });

  it("refuses an absent docked companion", async () => {
    tabs();
    ws().setLayoutPreset("docked");
    const agents = comp();
    handlers["tab.next"]();
    await vi.dynamicImportSettled();
    expect(comp()).toBe(agents);
  });
});
