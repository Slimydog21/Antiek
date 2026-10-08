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

describe("synchronous close publication", () => {
  for (const boundary of ["closing=false", "companion removal", "removed closing=false"] as const) {
    for (const replacement of ["owner", "incarnation"] as const) {
      it(`refuses old close sinks after ${replacement} replacement at ${boundary}`, async () => {
        const undo = vi.spyOn(toast, "undo");
        const focus = document.createElement("button"); document.body.append(focus); focus.focus();
        let observed = 0;
        const replace = () => {
          observed++;
          if (replacement === "owner") setWorkspaceOwner("unit-B");
          useCompanion.getState().reset();
          useCompanion.getState().openAgentTab({ kind: "dialogue", agentId: "x:1", title: "replacement pane" });
          focus.focus();
        };
        const off = boundary === "companion removal"
          ? useCompanion.subscribe((state, previous) => {
              if (previous.tabs.some((tab) => tab.id === id) && !state.tabs.some((tab) => tab.id === id) && observed === 0) { off(); replace(); }
            })
          : useAgentPaneStore.subscribe((state, previous) => {
              const publication = boundary === "closing=false" ? previous.closing[id] && !state.closing[id]
                : !state.closing[id] && !useCompanion.getState().tabs.some((tab) => tab.id === id);
              if (publication && observed === 0) { off(); replace(); }
            });
        try {
          closeAgentPane(id, "outgoing private title");
          await vi.advanceTimersByTimeAsync(CLOSE_LINGER_MS);
          expect(observed).toBe(1);
          expect({
            tabs: useCompanion.getState().tabs.map((tab) => ({ id: tab.id, title: tab.title })),
            retired: useCompanion.getState().retired,
            toastCount: undo.mock.calls.length,
            focusUnchanged: document.activeElement === focus,
          }).toEqual({ tabs: [{ id, title: "replacement pane" }], retired: [], toastCount: 0, focusUnchanged: true });
          await awaitWorkspaceOwnerSession(workspaceOwnerSession());
          closeAgentPane(id);
          await vi.advanceTimersByTimeAsync(CLOSE_LINGER_MS);
          expect(useCompanion.getState().tabs).toEqual([]);
          expect(undo).toHaveBeenCalledTimes(1);
        } finally { off(); }
      });
    }
  }

  for (const boundary of ["closing=false", "companion removal", "retirement publication", "toast return"] as const) {
    it(`holds the remaining close effects through same-owner suspension at ${boundary}`, async () => {
      const realUndo = toast.undo;
      let observed = 0;
      const suspend = () => { if (observed === 0) { observed++; suspendWorkspaceOwner(); } };
      const undo = vi.spyOn(toast, "undo").mockImplementation((message, run) => {
        const returned = realUndo(message, run);
        if (boundary === "toast return") suspend();
        return returned;
      });
      const off = boundary === "closing=false"
        ? useAgentPaneStore.subscribe((state, previous) => { if (previous.closing[id] && !state.closing[id]) suspend(); })
        : useCompanion.subscribe((state, previous) => {
            if (boundary === "companion removal" && previous.tabs.some((tab) => tab.id === id) && !state.tabs.some((tab) => tab.id === id)) suspend();
            if (boundary === "retirement publication" && state.retired.length > previous.retired.length) suspend();
          });
      const owner = workspaceOwnerSession();
      const focus = document.createElement("button"); document.body.append(focus); focus.focus();
      try {
        closeAgentPane(id); await vi.advanceTimersByTimeAsync(CLOSE_LINGER_MS);
        expect(observed).toBe(1); expect(workspaceOwnerSession()).toBe(owner);
        expect(useCompanion.getState().tabs).toHaveLength(boundary === "closing=false" ? 1 : 0);
        expect(useCompanion.getState().retired).toHaveLength(boundary === "retirement publication" || boundary === "toast return" ? 1 : 0);
        expect(undo).toHaveBeenCalledTimes(boundary === "toast return" ? 1 : 0);
        expect(document.activeElement).toBe(focus);
        resumeWorkspaceOwner(owner); await vi.advanceTimersByTimeAsync(0);
        expect(useCompanion.getState().tabs).toEqual([]); expect(undo).toHaveBeenCalledTimes(1);
        expect(document.activeElement).toBe(document.querySelector('[data-pane="left"]'));
        undo.mock.calls[0][1](); await vi.advanceTimersByTimeAsync(0);
        expect(useCompanion.getState().tabs.map((tab) => tab.id)).toEqual([id]);
      } finally { off(); }
    });
  }

  it("a synchronous descriptor clone at closing=false preserves normal close and Undo", async () => {
    const undo = vi.spyOn(toast, "undo"); let observed = 0;
    const off = useAgentPaneStore.subscribe((state, previous) => {
      if (previous.closing[id] && !state.closing[id] && observed === 0) {
        off(); observed++; useCompanion.getState().openAgentTab({ kind: "dialogue", agentId: "x:1", scope: "project", projectId: "clone" });
      }
    });
    try {
      closeAgentPane(id); await vi.advanceTimersByTimeAsync(CLOSE_LINGER_MS);
      expect(observed).toBe(1); expect(useCompanion.getState().tabs).toEqual([]); expect(undo).toHaveBeenCalledTimes(1);
      undo.mock.calls[0][1](); await vi.advanceTimersByTimeAsync(0);
      expect(useCompanion.getState().tabs).toHaveLength(1); expect(useCompanion.getState().tabs[0].projectId).toBe("clone");
    } finally { off(); }
  });

  it("normal real-store closes retain twenty retired entries and the ten-second Undo window", async () => {
    render(createElement(LemonToastViewport));
    const undo = vi.spyOn(toast, "undo");
    for (let i = 0; i < 21; i++) {
      const tabId = useCompanion.getState().openAgentTab({ kind: "dialogue", agentId: `limit-${i}`, title: `local pane ${i}` });
      closeAgentPane(tabId); await vi.advanceTimersByTimeAsync(CLOSE_LINGER_MS);
    }
    expect(useCompanion.getState().retired.map((entry) => entry.tab.agentId)).toEqual(Array.from({ length: 20 }, (_, i) => `limit-${i + 1}`));
    expect(undo).toHaveBeenCalledTimes(21);
    await vi.advanceTimersByTimeAsync(9_999); expect(document.body.textContent).toContain("local pane 20");
    await vi.advanceTimersByTimeAsync(1); expect(document.body.textContent).not.toContain("local pane 20");
  });

  for (const boundary of ["closing=false", "retirement publication"] as const) {
    it(`retains the actual error and refuses remaining effects when ${boundary} throws`, async () => {
      const undo = vi.spyOn(toast, "undo");
      const failure = new Error(`local ${boundary} observer failed`);
      const off = boundary === "closing=false"
        ? useAgentPaneStore.subscribe((state, previous) => { if (previous.closing[id] && !state.closing[id]) { off(); throw failure; } })
        : useCompanion.subscribe((state, previous) => { if (state.retired.length > previous.retired.length) { off(); throw failure; } });
      try {
        closeAgentPane(id); await expect(vi.advanceTimersByTimeAsync(CLOSE_LINGER_MS)).rejects.toBe(failure);
        expect(useCompanion.getState().retired).toEqual([]); expect(undo).not.toHaveBeenCalled();
        expect(useCompanion.getState().tabs).toHaveLength(boundary === "closing=false" ? 1 : 0);
        open(); closeAgentPane(id); await vi.advanceTimersByTimeAsync(CLOSE_LINGER_MS);
        expect(useCompanion.getState().tabs).toEqual([]); expect(undo).toHaveBeenCalledTimes(1);
      } finally { off(); }
    });
  }

  for (const replacement of ["owner", "incarnation"] as const) {
    it(`removes only its own retired record after ${replacement} replacement in retirement publication`, async () => {
      const undo = vi.spyOn(toast, "undo");
      const focus = document.createElement("button"); document.body.append(focus); focus.focus();
      let observed = 0;
      const off = useCompanion.subscribe((state, previous) => {
        if (state.retired.length > previous.retired.length && observed === 0) {
          off(); observed++;
          if (replacement === "owner") setWorkspaceOwner("unit-B");
          open(); focus.focus();
        }
      });
      try {
        closeAgentPane(id, "outgoing private title"); await vi.advanceTimersByTimeAsync(CLOSE_LINGER_MS);
        expect(observed).toBe(1);
        expect(useCompanion.getState().tabs.map((tab) => tab.id)).toEqual([id]);
        expect(useCompanion.getState().retired).toEqual([]);
        expect(undo).not.toHaveBeenCalled(); expect(document.activeElement).toBe(focus);
        await awaitWorkspaceOwnerSession(workspaceOwnerSession()); closeAgentPane(id); await vi.advanceTimersByTimeAsync(CLOSE_LINGER_MS);
        expect(useCompanion.getState().tabs).toEqual([]); expect(undo).toHaveBeenCalledTimes(1);
      } finally { off(); }
    });

    it(`dismisses its actual returned toast after ${replacement} retirement before return`, async () => {
      render(createElement(LemonToastViewport));
      const realUndo = toast.undo;
      let returned: number | null = null;
      let observed = 0;
      const undo = vi.spyOn(toast, "undo").mockImplementation((message, run) => {
        const actualId = realUndo(message, run);
        if (observed === 0) {
          returned = actualId; observed++;
          if (replacement === "owner") setWorkspaceOwner("unit-B");
          open();
        }
        return actualId;
      });
      const focus = document.createElement("button"); document.body.append(focus); focus.focus();
      try {
        closeAgentPane(id, "outgoing private title"); await vi.advanceTimersByTimeAsync(CLOSE_LINGER_MS);
        expect(observed).toBe(1); expect(undo).toHaveBeenCalledTimes(1);
        expect(document.body.textContent).not.toContain("outgoing private title");
        expect(useCompanion.getState().retired).toEqual([]);
        expect(useCompanion.getState().tabs.map((tab) => tab.id)).toEqual([id]); expect(document.activeElement).toBe(focus);
        await awaitWorkspaceOwnerSession(workspaceOwnerSession()); closeAgentPane(id); await vi.advanceTimersByTimeAsync(CLOSE_LINGER_MS);
        expect(useCompanion.getState().tabs).toEqual([]); expect(undo).toHaveBeenCalledTimes(2);
      } finally { if (returned !== null) toast.dismiss(returned); }
    });
  }
});
