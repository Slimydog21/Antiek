import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  accountStorageKey, awaitWorkspaceOwnerSession, beforeWorkspaceOwnerChange,
  isWorkspaceOwnerSession, resumeWorkspaceOwner, setWorkspaceOwner,
  suspendWorkspaceOwner, workspaceOwnerSession,
} from "./accountWorkspaceOwner";

const unsubscribers: Array<() => void> = [];
function onRetirement(listener: () => void) {
  const unsubscribe = beforeWorkspaceOwnerChange(listener);
  unsubscribers.push(unsubscribe);
  return unsubscribe;
}

beforeEach(() => {
  window.localStorage.clear();
  setWorkspaceOwner("acct_test_a");
});
afterEach(() => {
  for (const unsubscribe of unsubscribers.splice(0)) unsubscribe();
  setWorkspaceOwner(null);
  resumeWorkspaceOwner();
});

describe("replacement closes outbound admission before every retirement callback", () => {
  it("denies an earlier retained callback while preserving old-owner local keys", () => {
    const owner = workspaceOwnerSession();
    const outbound = vi.fn();
    const observation: Array<{ readable: string | null; admitted: boolean }> = [];
    onRetirement(() => {
      observation.push({ readable: workspaceOwnerSession().subject, admitted: isWorkspaceOwnerSession(owner) });
      const key = accountStorageKey("private-draft", owner);
      if (key) window.localStorage.setItem(key, "A final local edit");
      if (isWorkspaceOwnerSession(owner)) outbound();
    });
    onRetirement(() => { if (isWorkspaceOwnerSession(owner)) outbound(); });
    setWorkspaceOwner("acct_test_b");
    expect(observation).toEqual([{ readable: "acct_test_a", admitted: false }]);
    expect(outbound).not.toHaveBeenCalled();
    expect(window.localStorage.getItem("private-draft.owner.acct_test_a")).toBe("A final local edit");
    expect(window.localStorage.getItem("private-draft.owner.acct_test_b")).toBeNull();
    expect(isWorkspaceOwnerSession(workspaceOwnerSession())).toBe(true);
  });

  it("a callback cannot reopen retired authority by resuming revalidation", async () => {
    const owner = workspaceOwnerSession();
    suspendWorkspaceOwner();
    const held = awaitWorkspaceOwnerSession(owner);
    const outbound = vi.fn();
    onRetirement(() => {
      resumeWorkspaceOwner();
      if (isWorkspaceOwnerSession(owner)) outbound();
    });
    setWorkspaceOwner("acct_test_b");
    expect(await held).toBe(false);
    expect(outbound).not.toHaveBeenCalled();
  });

  it("a new waiter created inside retirement is refused instead of confirming A", async () => {
    const owner = workspaceOwnerSession();
    let pending = Promise.resolve(true);
    onRetirement(() => { pending = awaitWorkspaceOwnerSession(owner); });
    setWorkspaceOwner(null);
    expect(await pending).toBe(false);
    expect(workspaceOwnerSession().subject).toBeNull();
  });

  it("failed cleanup retains readable old keys but cannot reauthorize the old actor", async () => {
    const owner = workspaceOwnerSession();
    const primary = new Error("synthetic local cleanup failure");
    const unsubscribe = onRetirement(() => { throw primary; });
    suspendWorkspaceOwner();
    const held = awaitWorkspaceOwnerSession(owner);
    expect(() => setWorkspaceOwner("acct_test_b")).toThrow(primary);
    resumeWorkspaceOwner();
    expect(workspaceOwnerSession()).toBe(owner);
    expect(isWorkspaceOwnerSession(owner)).toBe(false);
    expect(await held).toBe(false);
    expect(await awaitWorkspaceOwnerSession(owner)).toBe(false);
    unsubscribe();
    setWorkspaceOwner("acct_test_b");
    expect(isWorkspaceOwnerSession(workspaceOwnerSession())).toBe(true);
  });

  it("same-owner confirmation does not retire, change epoch or lose local state", async () => {
    const owner = workspaceOwnerSession();
    const retire = vi.fn();
    onRetirement(retire);
    const key = accountStorageKey("private-draft", owner);
    if (!key) throw new Error("test actor has no local partition");
    window.localStorage.setItem(key, "same-owner continuity");
    suspendWorkspaceOwner();
    const held = awaitWorkspaceOwnerSession(owner);
    setWorkspaceOwner("acct_test_a");
    resumeWorkspaceOwner();
    expect(await held).toBe(true);
    expect(workspaceOwnerSession()).toBe(owner);
    expect(retire).not.toHaveBeenCalled();
    expect(window.localStorage.getItem(key)).toBe("same-owner continuity");
  });

  it("ordinary same-owner work remains admitted until replacement starts", () => {
    const owner = workspaceOwnerSession();
    const outbound = vi.fn();
    if (isWorkspaceOwnerSession(owner)) outbound();
    expect(outbound).toHaveBeenCalledOnce();
    setWorkspaceOwner("acct_test_b");
    setWorkspaceOwner("acct_test_a");
    expect(isWorkspaceOwnerSession(owner)).toBe(false);
    expect(isWorkspaceOwnerSession(workspaceOwnerSession())).toBe(true);
  });
});
