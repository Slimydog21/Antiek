import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { awaitWorkspaceOwnerSession, accountStorageKey, beforeWorkspaceOwnerChange, resumeWorkspaceOwner, setWorkspaceOwner, subscribeWorkspaceOwnerAdmission, suspendWorkspaceOwner, workspaceOwnerSession } from "../../lib/accountWorkspaceOwner";
import { getCustomHotkeys, installShortcuts } from "../../workspace/shortcuts";
import { useCustomHotkeys } from "./useCustomHotkeys";
import { pinPlatform, press, unpinPlatform } from "../../workspace/keymapTestKit";

const settle = () => act(async () => { await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
const key = () => accountStorageKey("antiek.workspace.custom-hotkeys")!;
const input = { spec: "mod+.", route: "/research/a", entityId: "a", entityKind: "investigation" as const, label: "A" };
const seed = () => localStorage.setItem(key(), JSON.stringify({ schemaVersion: 1, bindings: [{ ...input, id: "a-binding" }] }));
beforeEach(() => { setWorkspaceOwner("custom-unit-a"); localStorage.clear(); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); setWorkspaceOwner(null); localStorage.clear(); });

describe("originating custom hook admission (synthetic local UNIT)", () => {
  it("refuses anonymous mutation", async () => {
    setWorkspaceOwner(null); const { result } = renderHook(useCustomHotkeys); await settle();
    act(() => { expect(result.current.assign(input).ok).toBe(false); });
    expect(result.current.bindings).toEqual([]); expect(getCustomHotkeys()).toEqual([]);
  });
  it("does not read or write while first mounted suspended", async () => {
    seed(); suspendWorkspaceOwner(); const read = vi.spyOn(Storage.prototype, "getItem"); const write = vi.spyOn(Storage.prototype, "setItem");
    const { result } = renderHook(useCustomHotkeys);
    expect(result.current.bindings).toEqual([]); expect(read).not.toHaveBeenCalled(); expect(write).not.toHaveBeenCalled();
  });
  it("refuses adoption when the storage read replaces the owner", async () => {
    seed(); const original = Storage.prototype.getItem;
    vi.spyOn(Storage.prototype, "getItem").mockImplementationOnce(function (this: Storage, k: string) { const value = original.call(this, k); setWorkspaceOwner("custom-unit-b"); return value; });
    const { result } = renderHook(useCustomHotkeys); await settle(); expect(result.current.bindings).toEqual([]); expect(getCustomHotkeys()).toEqual([]);
  });
  it("old assign cannot publish into a replacement owner", async () => {
    const a = renderHook(useCustomHotkeys); await settle(); const assign = a.result.current.assign;
    act(() => { setWorkspaceOwner("custom-unit-b"); }); const b = renderHook(useCustomHotkeys); await settle();
    act(() => { expect(assign(input).ok).toBe(false); });
    expect(b.result.current.bindings).toEqual([]); expect(getCustomHotkeys()).toEqual([]);
  });
  it("old reset cannot clear the replacement owner's storage", async () => {
    const a = renderHook(useCustomHotkeys); await settle(); const reset = a.result.current.resetAll; a.unmount(); setWorkspaceOwner("custom-unit-b"); seed(); const before = localStorage.getItem(key());
    act(reset); expect(localStorage.getItem(key())).toBe(before);
  });
  it("old remove cannot publish after A-B-A incarnation replacement", async () => {
    seed(); const a = renderHook(useCustomHotkeys); await settle(); const remove = a.result.current.removeForEntity;
    act(() => { setWorkspaceOwner("custom-unit-b"); setWorkspaceOwner("custom-unit-a"); }); const before = localStorage.getItem(key());
    act(() => remove("a")); expect(localStorage.getItem(key())).toBe(before); expect(a.result.current.bindings).toEqual([]);
  });
  it("retains a same-token suspended snapshot and resumes admitted edits", async () => {
    seed(); const { result } = renderHook(useCustomHotkeys); await settle(); const owner = workspaceOwnerSession();
    act(suspendWorkspaceOwner); expect(result.current.bindings).toHaveLength(1);
    act(() => { expect(result.current.assign({ ...input, entityId: "b", spec: "mod+," }).ok).toBe(false); });
    act(() => { resumeWorkspaceOwner(owner); });
    await waitFor(() => { expect(result.current.bindings).toHaveLength(1); });
    await act(async () => { await Promise.resolve(); });
    act(() => { expect(result.current.assign({ ...input, entityId: "b", spec: "mod+," }).ok).toBe(true); });
    expect(result.current.bindings).toHaveLength(2);
  });
  it("admitted assignment updates siblings and survives remount", async () => {
    const a = renderHook(useCustomHotkeys); await settle(); const b = renderHook(useCustomHotkeys); await settle();
    act(() => { expect(a.result.current.assign(input).ok).toBe(true); }); expect(b.result.current.bindings).toHaveLength(1);
    a.unmount(); b.unmount(); const c = renderHook(useCustomHotkeys); await settle(); expect(c.result.current.bindings).toHaveLength(1);
  });
  it("only the captured owner storage event adopts changed data", async () => {
    const { result } = renderHook(useCustomHotkeys); await settle(); seed();
    act(() => { window.dispatchEvent(new StorageEvent("storage", { key: "antiek.workspace.custom-hotkeys.owner.other" })); }); expect(result.current.bindings).toEqual([]);
    act(() => { window.dispatchEvent(new StorageEvent("storage", { key: key() })); }); expect(result.current.bindings).toHaveLength(1);
  });
  it("failed retirement refuses loaded state and edits at the unchanged token", async () => {
    seed(); const { result } = renderHook(useCustomHotkeys); await settle(); const retire = beforeWorkspaceOwnerChange(() => { throw new Error("synthetic retirement failure"); });
    act(() => { expect(() => setWorkspaceOwner("custom-unit-b")).toThrow(); }); retire();
    expect(result.current.bindings).toEqual([]); act(() => { expect(result.current.assign(input).ok).toBe(false); });
  });
  it("unmounted callbacks refuse mutation", async () => {
    const { result, unmount } = renderHook(useCustomHotkeys); await settle(); const assign = result.current.assign; unmount();
    expect(assign(input).ok).toBe(false); expect(localStorage.getItem(key())).toBe(JSON.stringify({ schemaVersion: 1, bindings: [] }));
  });
});

describe("confirmed initial custom hydration and accepted edit lifetime (synthetic local UNIT)", () => {
  it("starts without private reads then hydrates the settled captured owner", async () => {
    seed(); const read = vi.spyOn(Storage.prototype, "getItem");
    const { result } = renderHook(useCustomHotkeys);
    expect(result.current.bindings).toEqual([]); expect(read).not.toHaveBeenCalled();
    await settle(); expect(result.current.bindings).toHaveLength(1); expect(read).toHaveBeenCalled();
  });
  it("refuses initial hook reads when a later ready observer fails", async () => {
    const read = vi.spyOn(Storage.prototype, "getItem");
    const mount = subscribeWorkspaceOwnerAdmission((admission) => {
      if (admission.state === "ready" && admission.session.subject === "custom-unit-b") renderHook(useCustomHotkeys);
    });
    const fail = subscribeWorkspaceOwnerAdmission((admission) => {
      if (admission.state === "ready" && admission.session.subject === "custom-unit-b") throw new Error("synthetic later observer failure");
    });
    try { expect(() => setWorkspaceOwner("custom-unit-b")).toThrow(); }
    finally { mount(); fail(); }
    await settle(); expect(read).not.toHaveBeenCalled(); expect(getCustomHotkeys()).toEqual([]);
  });
  it("disposes pending initial confirmation before genuine resume", async () => {
    seed(); const owner = workspaceOwnerSession(); suspendWorkspaceOwner();
    const read = vi.spyOn(Storage.prototype, "getItem"); const hook = renderHook(useCustomHotkeys);
    hook.unmount(); resumeWorkspaceOwner(owner); await settle(); expect(read).not.toHaveBeenCalled();
  });
  it("refuses pending initial hydration after owner replacement", async () => {
    seed(); suspendWorkspaceOwner(); const read = vi.spyOn(Storage.prototype, "getItem");
    const hook = renderHook(useCustomHotkeys); setWorkspaceOwner("custom-unit-b"); await settle();
    expect(read).not.toHaveBeenCalled(); expect(hook.result.current.bindings).toEqual([]);
  });
  it("retains an accepted edit suspended before its updater and persistence then dispatches after confirmed resume", async () => {
    const hook = renderHook(useCustomHotkeys); await settle(); const owner = workspaceOwnerSession();
    const read = vi.spyOn(Storage.prototype, "getItem"); const write = vi.spyOn(Storage.prototype, "setItem");
    act(() => { expect(hook.result.current.assign(input).ok).toBe(true); suspendWorkspaceOwner(); });
    expect(read).not.toHaveBeenCalled(); expect(write).not.toHaveBeenCalled(); expect(hook.result.current.bindings).toHaveLength(1);
    act(() => { resumeWorkspaceOwner(owner); }); await settle();
    expect(hook.result.current.bindings[0].entityId).toBe(input.entityId);
    expect(JSON.parse(localStorage.getItem(key())!).bindings[0].entityId).toBe(input.entityId);
    const navigate = vi.fn(); pinPlatform("mac"); const stop = installShortcuts(navigate);
    try { await settle(); press(document.body, "mod+.", "mac"); expect(navigate).toHaveBeenCalledWith(input.route); }
    finally { stop(); unpinPlatform(); }
  });
  it("retires an accepted unpersisted edit on replacement instead of writing to B", async () => {
    const hook = renderHook(useCustomHotkeys); await settle(); const write = vi.spyOn(Storage.prototype, "setItem");
    act(() => { expect(hook.result.current.assign(input).ok).toBe(true); suspendWorkspaceOwner(); setWorkspaceOwner("custom-unit-b"); });
    await settle(); expect(write).not.toHaveBeenCalled(); expect(hook.result.current.bindings).toEqual([]); expect(getCustomHotkeys()).toEqual([]);
  });
});
