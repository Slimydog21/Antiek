/** Actual companion/account stores with local DOM and synthetic clock, no auth/provider proof. */
import { createElement } from "react";
import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { awaitWorkspaceOwnerSession, resumeWorkspaceOwner, setWorkspaceOwner, suspendWorkspaceOwner, workspaceOwnerSession } from "../../lib/accountWorkspaceOwner";
import { toast, LemonToastViewport } from "../../components/lemon/LemonToast";
import { useCompanion } from "../companionStore";
import { closeAgentPane, CLOSE_LINGER_MS, useAgentPaneStore } from "./agentPaneStore";
const id = "agent:pane:x:1";
const open = () => useCompanion.getState().openAgentTab({ kind: "dialogue", agentId: "x:1", title: "local agent" });
beforeEach(async () => { vi.useFakeTimers(); setWorkspaceOwner(null); setWorkspaceOwner("unit-A"); await awaitWorkspaceOwnerSession(workspaceOwnerSession()); useCompanion.getState().reset(); useAgentPaneStore.getState().reset(); open(); document.body.innerHTML = '<div data-pane="left" tabindex="-1"></div>'; });
afterEach(() => { cleanup(); setWorkspaceOwner(null); vi.useRealTimers(); vi.restoreAllMocks(); document.body.innerHTML = ""; });
describe("delayed pane close ownership", () => {
  it("old A close cannot close B same ID or move B focus", async () => {
    const undo = vi.spyOn(toast, "undo"); closeAgentPane(id); setWorkspaceOwner("unit-B"); useCompanion.getState().reset(); open();
    const focus = document.createElement("button"); document.body.append(focus); focus.focus();
    await vi.advanceTimersByTimeAsync(CLOSE_LINGER_MS);
    expect(useCompanion.getState().tabs.map((t) => t.id)).toEqual([id]); expect(undo).not.toHaveBeenCalled(); expect(document.activeElement).toBe(focus);
  });
  it("a newer same-ID pane is not the old close target", async () => {
    const undo = vi.spyOn(toast, "undo"); closeAgentPane(id); useCompanion.getState().closeAgentTab(id); open();
    await vi.advanceTimersByTimeAsync(CLOSE_LINGER_MS);
    expect(useCompanion.getState().tabs.map((t) => t.id)).toEqual([id]); expect(undo).not.toHaveBeenCalled();
  });
  it("same owner suspension holds close and Undo/focus until confirmed", async () => {
    const undo = vi.spyOn(toast, "undo"); closeAgentPane(id); suspendWorkspaceOwner(); await vi.advanceTimersByTimeAsync(CLOSE_LINGER_MS);
    expect(useCompanion.getState().tabs.map((t) => t.id)).toEqual([id]); expect(undo).not.toHaveBeenCalled();
    resumeWorkspaceOwner(); await vi.advanceTimersByTimeAsync(0);
    expect(useCompanion.getState().tabs).toEqual([]); expect(undo).toHaveBeenCalledTimes(1);
  });
  it("same-owner normal close retains exact linger, Undo, reopen and focus", async () => {
    const undo = vi.spyOn(toast, "undo"); closeAgentPane(id); await vi.advanceTimersByTimeAsync(CLOSE_LINGER_MS - 1); expect(useCompanion.getState().tabs).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1); expect(useCompanion.getState().tabs).toEqual([]); expect(document.activeElement).toBe(document.querySelector('[data-pane="left"]'));
    undo.mock.calls[0][1](); await vi.advanceTimersByTimeAsync(0); expect(useCompanion.getState().tabs.map((t) => t.id)).toEqual([id]);
  });
  it("old Undo refuses B and A-B-A even if called after the old toast survives", async () => {
    const undo = vi.spyOn(toast, "undo"); closeAgentPane(id); await vi.advanceTimersByTimeAsync(CLOSE_LINGER_MS);
    const old = undo.mock.calls[0][1]; setWorkspaceOwner("unit-B"); useCompanion.getState().reset(); setWorkspaceOwner("unit-A"); old(); await vi.advanceTimersByTimeAsync(0);
    expect(useCompanion.getState().tabs).toEqual([]);
  });
  it("pane state retires synchronously but a same-owner suspension preserves it", () => {
    const s = useAgentPaneStore.getState(); s.setRecording(id, true); s.dismissChip(id, "anchor"); s.bumpNonce(id);
    suspendWorkspaceOwner(); expect(useAgentPaneStore.getState().recording[id]).toBe(true); resumeWorkspaceOwner();
    setWorkspaceOwner("unit-B"); expect(useAgentPaneStore.getState()).toMatchObject({ closing: {}, recording: {}, chipDismissed: {}, openNonce: {} });
  });
  it("old linger does not mark a reopened same-ID pane closing", async () => {
    closeAgentPane(id); useCompanion.getState().closeAgentTab(id); open();
    expect(useAgentPaneStore.getState().closing[id]).toBeUndefined();
    await vi.advanceTimersByTimeAsync(CLOSE_LINGER_MS); expect(useCompanion.getState().tabs).toHaveLength(1);
    closeAgentPane(id); await vi.advanceTimersByTimeAsync(CLOSE_LINGER_MS); expect(useCompanion.getState().tabs).toHaveLength(0);
  });
  it("focus/anchor descriptor clones keep the real current lease and normal close", async () => {
    closeAgentPane(id); useCompanion.getState().openAgentTab({ kind: "dialogue", agentId: "x:1", scope: "project", projectId: "same" });
    await vi.advanceTimersByTimeAsync(CLOSE_LINGER_MS); expect(useCompanion.getState().tabs).toHaveLength(0);
  });
  it("old Undo cannot restore an incarnation reopened and closed again", async () => {
    const undo = vi.spyOn(toast, "undo"); closeAgentPane(id); await vi.advanceTimersByTimeAsync(CLOSE_LINGER_MS); const old = undo.mock.calls[0][1];
    open(); useCompanion.getState().closeAgentTab(id); old(); await vi.advanceTimersByTimeAsync(0); expect(useCompanion.getState().tabs).toEqual([]);
  });

  it("an owned close toast cannot retain the outgoing pane title after account retirement", async () => {
    render(createElement(LemonToastViewport)); closeAgentPane(id, "A private title"); await vi.advanceTimersByTimeAsync(CLOSE_LINGER_MS);
    expect(document.body.textContent).toContain("A private title"); setWorkspaceOwner("unit-B");
    await vi.advanceTimersByTimeAsync(0); expect(document.body.textContent).not.toContain("A private title");
  });

});
