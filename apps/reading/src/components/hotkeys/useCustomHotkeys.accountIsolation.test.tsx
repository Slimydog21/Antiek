import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { accountStorageKey, beforeWorkspaceOwnerChange, resumeWorkspaceOwner, setWorkspaceOwner, suspendWorkspaceOwner, workspaceOwnerSession } from "../../lib/accountWorkspaceOwner";
import { getCustomHotkeys } from "../../workspace/shortcuts";
import { useCustomHotkeys } from "./useCustomHotkeys";

const key = () => accountStorageKey("antiek.workspace.custom-hotkeys")!;
const input = { spec: "mod+.", route: "/research/a", entityId: "a", entityKind: "investigation" as const, label: "A" };
const seed = () => localStorage.setItem(key(), JSON.stringify({ schemaVersion: 1, bindings: [{ ...input, id: "a-binding" }] }));
beforeEach(() => { setWorkspaceOwner("custom-unit-a"); localStorage.clear(); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); setWorkspaceOwner(null); localStorage.clear(); });

describe("originating custom hook admission (synthetic local UNIT)", () => {
  it("refuses anonymous mutation", () => {
    setWorkspaceOwner(null); const { result } = renderHook(useCustomHotkeys);
    act(() => { expect(result.current.assign(input).ok).toBe(false); });
    expect(result.current.bindings).toEqual([]); expect(getCustomHotkeys()).toEqual([]);
  });
  it("does not read or write while first mounted suspended", () => {
    seed(); suspendWorkspaceOwner(); const read = vi.spyOn(Storage.prototype, "getItem"); const write = vi.spyOn(Storage.prototype, "setItem");
    const { result } = renderHook(useCustomHotkeys);
    expect(result.current.bindings).toEqual([]); expect(read).not.toHaveBeenCalled(); expect(write).not.toHaveBeenCalled();
  });
  it("refuses adoption when the storage read replaces the owner", () => {
    seed(); const original = Storage.prototype.getItem;
    vi.spyOn(Storage.prototype, "getItem").mockImplementationOnce(function (this: Storage, k: string) { const value = original.call(this, k); setWorkspaceOwner("custom-unit-b"); return value; });
    const { result } = renderHook(useCustomHotkeys); expect(result.current.bindings).toEqual([]); expect(getCustomHotkeys()).toEqual([]);
  });
  it("old assign cannot publish into a replacement owner", () => {
    const a = renderHook(useCustomHotkeys); const assign = a.result.current.assign;
    act(() => { setWorkspaceOwner("custom-unit-b"); }); const b = renderHook(useCustomHotkeys);
    act(() => { expect(assign(input).ok).toBe(false); });
    expect(b.result.current.bindings).toEqual([]); expect(getCustomHotkeys()).toEqual([]);
  });
  it("old reset cannot clear the replacement owner's storage", () => {
    const a = renderHook(useCustomHotkeys); const reset = a.result.current.resetAll; a.unmount(); setWorkspaceOwner("custom-unit-b"); seed(); const before = localStorage.getItem(key());
    act(reset); expect(localStorage.getItem(key())).toBe(before);
  });
  it("old remove cannot publish after A-B-A incarnation replacement", () => {
    seed(); const a = renderHook(useCustomHotkeys); const remove = a.result.current.removeForEntity;
    act(() => { setWorkspaceOwner("custom-unit-b"); setWorkspaceOwner("custom-unit-a"); }); const before = localStorage.getItem(key());
    act(() => remove("a")); expect(localStorage.getItem(key())).toBe(before); expect(a.result.current.bindings).toEqual([]);
  });
  it("retains a same-token suspended snapshot and resumes admitted edits", async () => {
    seed(); const { result } = renderHook(useCustomHotkeys); const owner = workspaceOwnerSession();
    act(suspendWorkspaceOwner); expect(result.current.bindings).toHaveLength(1);
    act(() => { expect(result.current.assign({ ...input, entityId: "b", spec: "mod+," }).ok).toBe(false); });
    act(() => { resumeWorkspaceOwner(owner); });
    await waitFor(() => { expect(result.current.bindings).toHaveLength(1); });
    await act(async () => { await Promise.resolve(); });
    act(() => { expect(result.current.assign({ ...input, entityId: "b", spec: "mod+," }).ok).toBe(true); });
    expect(result.current.bindings).toHaveLength(2);
  });
  it("admitted assignment updates siblings and survives remount", () => {
    const a = renderHook(useCustomHotkeys); const b = renderHook(useCustomHotkeys);
    act(() => { expect(a.result.current.assign(input).ok).toBe(true); }); expect(b.result.current.bindings).toHaveLength(1);
    a.unmount(); b.unmount(); const c = renderHook(useCustomHotkeys); expect(c.result.current.bindings).toHaveLength(1);
  });
  it("only the captured owner storage event adopts changed data", () => {
    const { result } = renderHook(useCustomHotkeys); seed();
    act(() => { window.dispatchEvent(new StorageEvent("storage", { key: "antiek.workspace.custom-hotkeys.owner.other" })); }); expect(result.current.bindings).toEqual([]);
    act(() => { window.dispatchEvent(new StorageEvent("storage", { key: key() })); }); expect(result.current.bindings).toHaveLength(1);
  });
  it("failed retirement refuses loaded state and edits at the unchanged token", () => {
    seed(); const { result } = renderHook(useCustomHotkeys); const retire = beforeWorkspaceOwnerChange(() => { throw new Error("synthetic retirement failure"); });
    act(() => { expect(() => setWorkspaceOwner("custom-unit-b")).toThrow(); }); retire();
    expect(result.current.bindings).toEqual([]); act(() => { expect(result.current.assign(input).ok).toBe(false); });
  });
  it("unmounted callbacks refuse mutation", () => {
    const { result, unmount } = renderHook(useCustomHotkeys); const assign = result.current.assign; unmount();
    expect(assign(input).ok).toBe(false); expect(localStorage.getItem(key())).toBe(JSON.stringify({ schemaVersion: 1, bindings: [] }));
  });
});
