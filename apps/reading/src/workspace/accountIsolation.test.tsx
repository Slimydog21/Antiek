import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { accountStorageKey, notebookDraftKey, setWorkspaceOwner, workspaceOwnerSession } from "../lib/accountWorkspaceOwner";
import { readNotebookDraft, writeNotebookDraft } from "../lib/notebookDraftStorage";
import { useTalkThread } from "../modes/Reading/useTalkThread";
import { useThoughtPartnerThread } from "../hooks/useThoughtPartnerThread";
import { buildChaseDraftHandoff, listChaseDraftHandoffs, recordChaseDraftHandoff } from "../modes/ResearchWorkstation/chaseHandoffs";
import { clearAll, encodeWsParam, project, readCustomHotkeys, readScope, readTabProject, readWsFromUrl, writeCustomHotkeys, writeScope, writeTabProject } from "./persistence";
import { disablePersistence, enablePersistence, setPersistScope, useWorkspace } from "./WorkspaceStore";
import { requestTabTitle, setTitleResolvers, titleKey, useTabTitles } from "./tabTitles";
import "./tabTreeStore";

beforeEach(() => {
  setWorkspaceOwner(null);
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.history.replaceState({}, "", "/");
  setWorkspaceOwner("account-a");
  setPersistScope({ kind: "global" });
  enablePersistence();
});
afterEach(() => {
  cleanup();
  setWorkspaceOwner(null);
  disablePersistence();
  vi.useRealTimers();
});

function privatePanel() {
  useWorkspace.getState().open("NotebookEditor", {
    notebookId: "shared-id", initialContent: "A private body", provider_id: "A-private-provider",
  }, { id: "private" });
  useWorkspace.getState().pin("private");
}

describe("trusted account workspace boundaries", () => {
  it("rejects an A envelope even if it is supplied for B's storage key", () => {
    privatePanel();
    const a = project(useWorkspace.getState());
    setWorkspaceOwner("account-b");
    writeScope({ kind: "global" }, a);
    expect(readScope({ kind: "global" })).toBeNull();
    const key = accountStorageKey("antiek.workspace.global");
    if (key === null) throw new Error("B has not been established");
    window.localStorage.setItem(key, JSON.stringify(a));
    expect(readScope({ kind: "global" })).toBeNull();
  });
  it("flushes A's pending snapshot, retires pinned body props, and restores only A's partition", () => {
    vi.useFakeTimers();
    privatePanel();
    setWorkspaceOwner("account-b");
    expect(useWorkspace.getState().panels).toEqual({});
    expect(readScope({ kind: "global" })).toBeNull();
    vi.runAllTimers();
    expect(readScope({ kind: "global" })).toBeNull();
    setWorkspaceOwner("account-a");
    const restored = readScope({ kind: "global" });
    expect(restored?.panels.private.props.initialContent).toBe("A private body");
    expect(restored?.panels.private.props.provider_id).toBe("A-private-provider");
  });

  it("leaves legacy unowned bodies and harmless layout preferences stored without adopting them", () => {
    window.localStorage.setItem("antiek.workspace.global", JSON.stringify({ schemaVersion: 1, panels: { legacy: { props: { body: "operator" } } } }));
    window.localStorage.setItem("antiek.notebook.shared-id", "operator draft");
    window.localStorage.setItem("antiek.workspace.layout-preset", JSON.stringify({ schemaVersion: 1, preset: "docked" }));
    setWorkspaceOwner("account-b");
    expect(readScope({ kind: "global" })).toBeNull();
    expect(readNotebookDraft("shared-id")).toBeNull();
    clearAll();
    expect(window.localStorage.getItem("antiek.workspace.global")).toContain("operator");
    expect(window.localStorage.getItem("antiek.notebook.shared-id")).toBe("operator draft");
    expect(window.localStorage.getItem("antiek.workspace.layout-preset")).toContain("docked");
  });

  it("separates notebook bodies and etags for the same notebook id and blocks an old completion", () => {
    const a = workspaceOwnerSession();
    expect(writeNotebookDraft("shared-id", "A draft", 0, a)).toBe(1);
    setWorkspaceOwner("account-b");
    expect(readNotebookDraft("shared-id")).toBeNull();
    expect(writeNotebookDraft("shared-id", "A late body", 1, a)).toBeNull();
    expect(writeNotebookDraft("shared-id", "B draft", 0, workspaceOwnerSession())).toBe(1);
    setWorkspaceOwner(null);
    expect(readNotebookDraft("shared-id")).toBeNull();
    setWorkspaceOwner("account-a");
    expect(readNotebookDraft("shared-id")).toEqual({ html: "A draft", etag: 1 });
    expect(window.localStorage.getItem(notebookDraftKey("shared-id") ?? "")).toBe("A draft");
    // Returning to the same subject creates a new epoch: old work stays stale.
    expect(writeNotebookDraft("shared-id", "A stale epoch", 1, a)).toBeNull();
  });

  it("keeps private project and custom hotkey titles with their subject", () => {
    writeTabProject("A-project");
    writeCustomHotkeys({ schemaVersion: 1, bindings: [{ id: "key-a", spec: "mod+j", route: "/inv/a", entityId: "a", entityKind: "investigation", label: "A private title" }] });
    setWorkspaceOwner("account-b");
    expect(readTabProject()).toBeNull();
    expect(readCustomHotkeys().bindings).toEqual([]);
    setWorkspaceOwner("account-a");
    expect(readTabProject()).toBe("A-project");
    expect(readCustomHotkeys().bindings[0].label).toBe("A private title");
  });

  it("refuses an A body-bearing URL snapshot under B and permits its same-owner reload", () => {
    privatePanel();
    const snapshot = project(useWorkspace.getState());
    window.history.replaceState({}, "", `/?ws=${encodeURIComponent(encodeWsParam(snapshot))}`);
    expect(readWsFromUrl()?.panels.private).toBeDefined();
    setWorkspaceOwner("account-b");
    expect(readWsFromUrl()).toBeNull();
    setWorkspaceOwner("account-a");
    expect(readWsFromUrl()?.panels.private.props.initialContent).toBe("A private body");
  });

  it("does not let A's title response satisfy B's loading lookup for the same ref", async () => {
    let resolveA: (title: string) => void = () => { throw new Error("not requested"); };
    setTitleResolvers({ reader: () => new Promise((done) => { resolveA = done; }) });
    requestTabTitle({ kind: "reader", ref: "same-id" });
    setWorkspaceOwner("account-b");
    let resolveB: (title: string) => void = () => { throw new Error("not requested"); };
    setTitleResolvers({ reader: () => new Promise((done) => { resolveB = done; }) });
    requestTabTitle({ kind: "reader", ref: "same-id" });
    await act(async () => { resolveA("A title"); });
    expect(useTabTitles.getState().entries[titleKey("reader", "same-id")]).toEqual({ state: "loading" });
    await act(async () => { resolveB("B title"); });
    expect(useTabTitles.getState().entries[titleKey("reader", "same-id")]).toEqual({ state: "known", title: "B title" });
  });

  it("partitions persisted book answers and provider receipts, preserving A after logout/reload", () => {
    const a = renderHook(() => useTalkThread("same-id"));
    let turn = "";
    act(() => { turn = a.result.current.startTurn("A prompt"); });
    act(() => { a.result.current.completeTurn(turn, "A answer", [], true, null, "unavailable", { authority: "owner_byot", requested_provider_id: "a-provider", requested_model_id: "a-model", actual_provider_id: "a-provider", actual_model_id: "a-model", authority_digest: "a-digest" }); });
    const old = a.result.current;
    a.unmount();
    setWorkspaceOwner(null);
    setWorkspaceOwner("account-b");
    const b = renderHook(() => useTalkThread("same-id"));
    expect(b.result.current.messages).toEqual([]);
    act(() => { old.completeTurn(turn, "A late answer", [], true, null, "unavailable"); });
    expect(b.result.current.messages).toEqual([]);
    b.unmount();
    setWorkspaceOwner("account-a");
    const again = renderHook(() => useTalkThread("same-id"));
    expect(again.result.current.messages[0].answer).toBe("A answer");
    expect(again.result.current.messages[0].model_receipt?.actual_provider_id).toBe("a-provider");
  });

  it("partitions Thought Partner conversations and ignores an A callback after replacement", () => {
    const a = renderHook(useThoughtPartnerThread);
    let turn = "";
    act(() => { turn = a.result.current.startTurn("A question"); });
    act(() => { a.result.current.completeTurn(turn, "A notes", "SYNTHESIS"); });
    const old = a.result.current;
    a.unmount();
    setWorkspaceOwner("account-b");
    const b = renderHook(useThoughtPartnerThread);
    expect(b.result.current.messages).toEqual([]);
    act(() => { old.completeTurn(turn, "A late notes", "SYNTHESIS"); });
    b.unmount();
    setWorkspaceOwner("account-a");
    expect(renderHook(useThoughtPartnerThread).result.current.messages[0].answer).toBe("A notes");
  });

  it("keeps cached chase passages out of B including the storage-unavailable fallback", () => {
    recordChaseDraftHandoff(buildChaseDraftHandoff({ childInvestigationId: "child", parentInvestigationId: "parent", sourcePassage: "A source passage" }));
    setWorkspaceOwner("account-b");
    const blocked = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("storage blocked"); });
    expect(listChaseDraftHandoffs()).toEqual([]);
    blocked.mockRestore();
    setWorkspaceOwner("account-a");
    expect(listChaseDraftHandoffs()[0].source_passage).toBe("A source passage");
  });
});
