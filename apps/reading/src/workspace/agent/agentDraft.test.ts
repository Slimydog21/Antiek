/** agentDraft.test.ts — SPR-07 invariant 7: drafts are account-scoped sessionStorage, purged before the owner changes. */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { accountStorageKey, setWorkspaceOwner } from "../../lib/accountWorkspaceOwner";
import { agentDraftKey } from "./agentPaneId";
import { AGENT_STORAGE_PREFIX, DRAFT_DEBOUNCE_MS, purgeAgentDrafts, readAgentDraft, useAgentDraft, writeAgentDraft } from "./agentDraft";

beforeEach(() => { window.sessionStorage.clear(); });
afterEach(() => { vi.useRealTimers(); window.sessionStorage.clear(); });

const keyFor = () => agentDraftKey({ projectId: "p", agentId: "x", pane: "companion" });

describe("the draft key pins {user, project, agent, pane} with DISTINCT fixtures (repair C10)", () => {
  it("keys that differ only by agentId, or only by pane, are different keys with independent drafts", () => {
    setWorkspaceOwner("owner-a");
    const agentA = agentDraftKey({ projectId: "p", agentId: "p:proj-1", pane: "companion" })!;
    const agentB = agentDraftKey({ projectId: "p", agentId: "x:7", pane: "companion" })!;
    const paneTiled = agentDraftKey({ projectId: "p", agentId: "p:proj-1", pane: "tiled" })!;
    expect(new Set([agentA, agentB, paneTiled]).size).toBe(3);
    writeAgentDraft(agentA, "for agent A in the companion");
    expect(readAgentDraft(agentA)).toBe("for agent A in the companion");
    expect(readAgentDraft(agentB)).toBe("");
    expect(readAgentDraft(paneTiled)).toBe("");
    writeAgentDraft(paneTiled, "same agent, tiled host");
    expect(readAgentDraft(agentA)).toBe("for agent A in the companion");
    expect(readAgentDraft(paneTiled)).toBe("same agent, tiled host");
    // A cross-project pane has no project component; it never aliases a project one.
    const cross = agentDraftKey({ agentId: "p:proj-1", pane: "companion" })!;
    expect(cross).not.toBe(agentA);
    expect(readAgentDraft(cross)).toBe("");
  });
});

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

  it("a pending write never resurrects a draft the owner-change purge deleted, even when the hook re-keys instead of unmounting (finding 3)", () => {
    vi.useFakeTimers();
    setWorkspaceOwner("owner-a");
    const kA = keyFor();
    const { result, rerender } = renderHook(({ k }) => useAgentDraft(k), { initialProps: { k: kA } });
    act(() => result.current[1]("owner A secret"));
    setWorkspaceOwner("owner-b"); // the purge runs here
    rerender({ k: keyFor() }); // owner B's key: the hook stays mounted
    act(() => { vi.advanceTimersByTime(DRAFT_DEBOUNCE_MS + 50); });
    expect(Object.keys(window.sessionStorage).filter((k) => k.startsWith(AGENT_STORAGE_PREFIX))).toEqual([]);
  });

  it("under one owner, a pending write is flushed (not dropped) when the key changes, so a quick tab switch loses no words", () => {
    vi.useFakeTimers();
    setWorkspaceOwner("owner-a");
    const kA = keyFor()!;
    const kB = agentDraftKey({ projectId: "q", agentId: "x", pane: "companion" })!;
    const { result, rerender } = renderHook(({ k }) => useAgentDraft(k), { initialProps: { k: kA } });
    act(() => result.current[1]("last words"));
    rerender({ k: kB }); // within the debounce window
    expect(readAgentDraft(kA)).toBe("last words");
    expect(result.current[0]).toBe("");
    act(() => { vi.advanceTimersByTime(DRAFT_DEBOUNCE_MS + 50); });
    expect(readAgentDraft(kB)).toBe("");
  });

  it("a page load (null → the same subject) keeps that subject's draft and drops any other subject's (finding 4)", () => {
    setWorkspaceOwner(null);
    const mine = accountStorageKey("antiek.agent.draft.v1.p.x.companion", { subject: "owner-a", epoch: 0 })!;
    const theirs = accountStorageKey("antiek.agent.draft.v1.p.x.companion", { subject: "owner-z", epoch: 0 })!;
    // sessionStorage survived the reload; the module graph starts with subject null.
    window.sessionStorage.setItem(mine, "survive me");
    window.sessionStorage.setItem(theirs, "not mine");
    setWorkspaceOwner("owner-a"); // /auth/me answers with the same user
    expect(readAgentDraft(keyFor())).toBe("survive me");
    expect(window.sessionStorage.getItem(theirs)).toBeNull();
    // A real owner change still purges everything.
    setWorkspaceOwner("owner-b");
    expect(Object.keys(window.sessionStorage).some((k) => k.startsWith(AGENT_STORAGE_PREFIX))).toBe(false);
  });
});
