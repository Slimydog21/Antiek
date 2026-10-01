import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createInMemoryTabTreeAdapter, emptyTabTree, rebase, setPaneActive, spawnChild, toSnapshot } from "./tabTree";
import { useCompanion } from "./companionStore";
import { setTabOwner } from "./tabTreeOwner";
import { useTabTrees } from "./tabTreeStore";
import { openDocumentInLeftPane } from "./crossPane";
import { toast } from "../components/lemon/LemonToast";

const tabs = () => useTabTrees.getState();
const comp = () => useCompanion.getState();
const drain = async () => { for (let i = 0; i < 100; i++) await Promise.resolve(); };
const project = (id: string) => ({ project_id: id, title: id, kind: "project", order: 0, pinned: false, archived_at: null, primary_document_id: null, created_at: "2026-10-01", updated_at: null, member_count: 0 });
beforeEach(() => { setTabOwner("owner"); tabs().resetTabTrees(); comp().reset(); });
afterEach(() => { setTabOwner(null); tabs().resetTabTrees(); comp().reset(); window.history.replaceState({}, "", "/"); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it("binds the explicitly selected owned project, even when it is not the first registry row", async () => {
  window.history.replaceState({}, "", "/?project=chosen");
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ projects: [project("first"), project("chosen")] }))));
  await tabs().bindActiveProject();
  expect(tabs().projectId).toBe("chosen");
});

it("does not bind any registry row without an explicit selection", async () => {
  const fetcher = vi.fn<typeof fetch>();
  vi.stubGlobal("fetch", fetcher);
  await tabs().bindActiveProject();
  expect(tabs().projectId).toBeNull();
  expect(tabs().tabsPersistence).toBe("session");
  expect(fetcher).not.toHaveBeenCalled();
});

it("persists a visible research agent and restores active_right without replacing the left document focus", async () => {
  const adapter = createInMemoryTabTreeAdapter();
  await tabs().bindActiveProject(async () => "chosen", () => adapter);
  await tabs().ensureMothership("research");
  tabs().spawnTab("research", null, { tab_id: "left", kind: "reader", ref: "source", mothership: "research", activate: true });
  const id = comp().openAgentTab({ kind: "research-thread", investigationId: "thread", title: "Thread" });
  await drain();
  expect(tabs().trees.research?.nodes[id]).toMatchObject({ side: "right", kind: "research", ref: "thread", public_number: expect.any(Number) });
  expect(tabs().trees.research?.active_right).toBe(id);
  expect(tabs().trees.research?.active_tab_id).toBe("left");
  tabs().resetTabTrees();
  await tabs().bindActiveProject(async () => "chosen", () => adapter);
  await tabs().ensureMothership("research");
  expect(comp().activeTabId).toBe(id);
  expect(comp().tabs.find((tab) => tab.id === id)?.investigationId).toBe("thread");
  expect(tabs().trees.research?.active_left).toBe("left");
});

it("rebases a right selection over a remote left selection without claiming the document focus", () => {
  let tree = emptyTabTree("research");
  for (const [id, side, kind] of [["leftA", "left", "reader"], ["leftB", "left", "reader"], ["right", "right", "research"]] as const) {
    const result = spawnChild(tree, null, { tab_id: id, side, kind, ref: id, mothership: "research", activate: side === "left" });
    if (!result.ok) throw new Error(result.error.message);
    tree = result.tree;
  }
  const selected = setPaneActive(tree, "right", "right");
  if (!selected.ok) throw new Error(selected.error.message);
  const replayed = rebase(tree, [selected.op]);
  expect(replayed.tree.active_left).toBe("leftB");
  expect(replayed.tree.active_tab_id).toBe("leftB");
  expect(replayed.tree.active_right).toBe("right");
  expect(setPaneActive(tree, "right", "leftA").ok).toBe(false);
});

it("keeps imported real dialogue and project-tool references distinct from a new one-shot dialogue", async () => {
  const adapter = createInMemoryTabTreeAdapter();
  let tree = emptyTabTree("research");
  for (const [id, kind, ref] of [["realDialogue", "dialogue", "real-thread-id"], ["findings", "findings", "chosen"]] as const) {
    const result = spawnChild(tree, null, { tab_id: id, side: "right", kind, ref, mothership: "research", activate: false });
    if (!result.ok) throw new Error(result.error.message);
    tree = result.tree;
  }
  await adapter.save("chosen", "research", toSnapshot(tree));
  await tabs().bindActiveProject(async () => "chosen", () => adapter);
  await tabs().ensureMothership("research");
  expect(comp().tabs.find((tab) => tab.id === "realDialogue")).toMatchObject({ kind: "durable-thread", threadKind: "dialogue", investigationId: "real-thread-id", persistence: "tree", publicNumber: null });
  expect(comp().tabs.find((tab) => tab.id === "findings")).toMatchObject({ kind: "project-tool", toolKind: "findings", projectId: "chosen" });
  const oneShot = comp().openAgentTab({ kind: "dialogue" });
  expect(comp().tabs.find((tab) => tab.id === oneShot)).toMatchObject({ kind: "dialogue", persistence: "session" });
  expect(tabs().trees.research?.nodes[oneShot]).toBeUndefined();
});

it("drops an agent's deferred document open when its project changes without offering a copy into the new project", async () => {
  const adapter = createInMemoryTabTreeAdapter();
  await tabs().bindActiveProject(async () => "A", () => adapter);
  await tabs().ensureMothership("research");
  const agentTabId = comp().openAgentTab({ kind: "research-thread", investigationId: "threadA" });
  await drain();
  const notice = vi.spyOn(toast, "info");
  openDocumentInLeftPane("sourceA", { from: "companion", agentTabId, investigationId: "threadA", agentKind: "research" });
  tabs().resetTabTrees();
  await tabs().bindActiveProject(async () => "B", () => adapter);
  await tabs().ensureMothership("research");
  await drain();
  expect(Object.values(tabs().trees.research?.nodes ?? {}).some((node) => node.ref === "sourceA")).toBe(false);
  expect(notice).not.toHaveBeenCalled();
});

it("rejects a one-shot Undo from a previous owner", () => {
  const undo = vi.spyOn(toast, "undo").mockReturnValue(1);
  const id = comp().openAgentTab({ kind: "dialogue", title: "Private title" });
  comp().closeAgentTabWithUndo(id);
  setTabOwner("replacement");
  undo.mock.calls[0][1]();
  expect(comp().tabs).toEqual([]);
});
