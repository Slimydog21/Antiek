/** agentDraft.test.ts — SPR-07 invariant 7: drafts are account-scoped sessionStorage, purged before the owner changes. */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setWorkspaceOwner } from "../../lib/accountWorkspaceOwner";
import { agentDraftKey } from "./agentPaneId";
import { AGENT_STORAGE_PREFIX, DRAFT_DEBOUNCE_MS, purgeAgentDrafts, readAgentDraft, useAgentDraft, writeAgentDraft } from "./agentDraft";

beforeEach(() => { window.sessionStorage.clear(); });
afterEach(() => { vi.useRealTimers(); window.sessionStorage.clear(); });

const keyFor = () => agentDraftKey({ projectId: "p", agentId: "x", pane: "companion" });

describe("agentDraft", () => {
  it("reads back under the same owner, including after a simulated reload", () => {
    setWorkspaceOwner("owner-a");
    const key = keyFor()!;
    writeAgentDraft(key, "typed words");
    expect(readAgentDraft(key)).toBe("typed words");
    // A reload keeps sessionStorage; a fresh read from the key is the reload.
    expect(readAgentDraft(agentDraftKey({ projectId: "p", agentId: "x", pane: "companion" }))).toBe("typed words");
  });

  it("under owner b the draft reads empty and nothing is written to a's key", () => {
    setWorkspaceOwner("owner-a");
    const keyA = keyFor()!;
    writeAgentDraft(keyA, "a's words");
    setWorkspaceOwner("owner-b");
    const keyB = keyFor()!;
    expect(keyB).not.toBe(keyA);
    expect(readAgentDraft(keyB)).toBe("");
    // The owner-change purge ran: no antiek.agent. key survives.
    expect(Object.keys(window.sessionStorage).some((k) => k.startsWith(AGENT_STORAGE_PREFIX))).toBe(false);
  });

  it("purgeAgentDrafts removes every antiek.agent.* key and nothing else", () => {
    window.sessionStorage.setItem("antiek.agent.draft.v1.p.x.companion.owner.a", "1");
    window.sessionStorage.setItem("antiek.other", "2");
    purgeAgentDrafts();
    expect(window.sessionStorage.getItem("antiek.other")).toBe("2");
    expect(Object.keys(window.sessionStorage).some((k) => k.startsWith(AGENT_STORAGE_PREFIX))).toBe(false);
  });

  it("signed out (null key) ⇒ zero storage calls", () => {
    setWorkspaceOwner(null);
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const getItem = vi.spyOn(Storage.prototype, "getItem");
    writeAgentDraft(null, "x");
    expect(readAgentDraft(null)).toBe("");
    expect(setItem).not.toHaveBeenCalled();
    expect(getItem).not.toHaveBeenCalled();
    setItem.mockRestore(); getItem.mockRestore();
  });

  it("useAgentDraft reads on mount and writes after the debounce, only while the owner session holds", () => {
    vi.useFakeTimers();
    setWorkspaceOwner("owner-a");
    const key = keyFor()!;
    writeAgentDraft(key, "seeded");
    const { result } = renderHook(() => useAgentDraft(key));
    expect(result.current[0]).toBe("seeded");
    act(() => result.current[1]("seeded more"));
    expect(readAgentDraft(key)).toBe("seeded");
    act(() => { vi.advanceTimersByTime(DRAFT_DEBOUNCE_MS); });
    expect(readAgentDraft(key)).toBe("seeded more");
    // The owner changes under the hook: the pending write is dropped.
    act(() => result.current[1]("after switch"));
    setWorkspaceOwner("owner-b");
    act(() => { vi.advanceTimersByTime(DRAFT_DEBOUNCE_MS); });
    expect(window.sessionStorage.getItem(key)).toBeNull();
  });
});
