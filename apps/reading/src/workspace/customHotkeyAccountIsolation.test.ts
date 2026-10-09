import { act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { awaitWorkspaceOwnerSession, accountStorageKey, resumeWorkspaceOwner, setWorkspaceOwner, suspendWorkspaceOwner, subscribeWorkspaceOwnerAdmission, workspaceOwnerSession } from "../lib/accountWorkspaceOwner";
import { PRODUCT_ACTIVATE_EVENT } from "../components/hotkeys/bindings";
import { getCustomHotkeys, installShortcuts, setCustomHotkeys } from "./shortcuts";
import { pinPlatform, press, unpinPlatform } from "./keymapTestKit";
import { readKeyboardOwnership } from "./keyboardOwnership";
const binding = { id: "custom-unit", spec: "mod+.", route: "/research/a", entityId: "a" };
const settle = () => act(async () => { await awaitWorkspaceOwnerSession(workspaceOwnerSession()); });
const key = () => accountStorageKey("antiek.workspace.custom-hotkeys")!;
const seed = () => localStorage.setItem(key(), JSON.stringify({ schemaVersion: 1, bindings: [binding] }));
const disposals: (() => void)[] = [];
const activationListeners: EventListener[] = [];
function observeActivation(listener: EventListener) { activationListeners.push(listener); window.addEventListener(PRODUCT_ACTIVATE_EVENT, listener); }
beforeEach(() => { setWorkspaceOwner("custom-unit-a"); localStorage.clear(); pinPlatform("mac"); document.body.focus(); });
afterEach(() => { for (const stop of disposals.splice(0)) stop(); for (const listener of activationListeners.splice(0)) window.removeEventListener(PRODUCT_ACTIVATE_EVENT, listener); vi.restoreAllMocks(); setWorkspaceOwner(null); localStorage.clear(); unpinPlatform(); });
const install = (navigate = vi.fn()) => { const stop = installShortcuts(navigate); disposals.push(stop); return { navigate, stop }; };

describe("captured custom dispatcher admission (synthetic local UNIT)", () => {
  it("does not dispatch a suspended producer", async () => { seed(); const { navigate } = install(); await settle(); suspendWorkspaceOwner(); press(document.body, "mod+.", "mac"); expect(navigate).not.toHaveBeenCalled(); expect(getCustomHotkeys()).toEqual([]); });
  it("does not relabel an old installed map after owner replacement", async () => { seed(); const { navigate } = install(); await settle(); setWorkspaceOwner("custom-unit-b"); press(document.body, "mod+.", "mac"); expect(navigate).not.toHaveBeenCalled(); });
  it("old cleanup does not retire a newer owner's map", async () => {
    seed(); const a = install(); await settle(); setWorkspaceOwner("custom-unit-b"); seed(); const b = install(); await settle(); a.stop(); press(document.body, "mod+.", "mac"); expect(b.navigate).toHaveBeenCalledWith(binding.route); expect(getCustomHotkeys()).toHaveLength(1);
  });
  it("does not hydrate from storage while suspended", async () => { seed(); suspendWorkspaceOwner(); const read = vi.spyOn(Storage.prototype, "getItem"); install(); expect(read).not.toHaveBeenCalled(); });
  it("refuses a map whose read changes the owner", async () => {
    seed(); const original = Storage.prototype.getItem;
    vi.spyOn(Storage.prototype, "getItem").mockImplementationOnce(function (this: Storage, k: string) { const value = original.call(this, k); setWorkspaceOwner("custom-unit-b"); return value; });
    const { navigate } = install(); await settle(); press(document.body, "mod+.", "mac"); expect(navigate).not.toHaveBeenCalled(); expect(getCustomHotkeys()).toEqual([]);
  });
  it("withholds positive activation and action after navigation replaces the owner", async () => {
    seed(); const activated = vi.fn(); observeActivation(activated);
    const { navigate } = install(vi.fn(() => setWorkspaceOwner("custom-unit-b"))); await settle(); const e = press(document.body, "mod+.", "mac");
    expect(navigate).toHaveBeenCalledOnce(); expect(e.defaultPrevented).toBe(true); expect(activated).not.toHaveBeenCalled();
    expect(readKeyboardOwnership().traces.at(-1)?.actions).toEqual([]); window.removeEventListener(PRODUCT_ACTIVATE_EVENT, activated);
  });
  it("withholds positive activation after navigation suspends the origin", async () => {
    seed(); const activated = vi.fn(); observeActivation(activated); const { navigate } = install(vi.fn(suspendWorkspaceOwner)); await settle(); press(document.body, "mod+.", "mac");
    expect(navigate).toHaveBeenCalledOnce(); expect(activated).not.toHaveBeenCalled(); window.removeEventListener(PRODUCT_ACTIVATE_EVENT, activated);
  });
  it("admitted navigation emits the exact entity activation", async () => {
    seed(); const activated = vi.fn(); observeActivation(activated); const { navigate } = install(); await settle(); press(document.body, "mod+.", "mac");
    expect(navigate).toHaveBeenCalledWith(binding.route); expect(activated.mock.calls[0][0].detail).toEqual({ productId: "custom", route: binding.route, entityId: "a", source: "hotkey" }); window.removeEventListener(PRODUCT_ACTIVATE_EVENT, activated);
  });
  it("same-token resume restores the installed custom dispatcher", async () => {
    seed(); const { navigate } = install(); await settle(); const owner = workspaceOwnerSession(); suspendWorkspaceOwner(); resumeWorkspaceOwner(owner); await Promise.resolve(); press(document.body, "mod+.", "mac"); expect(navigate).toHaveBeenCalledWith(binding.route);
  });
  it("rejects a stale setter and preserves the current map", async () => {
    const a = workspaceOwnerSession(); setWorkspaceOwner("custom-unit-b"); seed(); install(); await settle(); setCustomHotkeys([], a); expect(getCustomHotkeys()).toHaveLength(1);
  });
  it("hydrates only exact owner-key storage events", async () => {
    const { navigate } = install(); await settle(); seed(); window.dispatchEvent(new StorageEvent("storage", { key: "antiek.workspace.custom-hotkeys.owner.other" })); press(document.body, "mod+.", "mac"); expect(navigate).not.toHaveBeenCalled();
    window.dispatchEvent(new StorageEvent("storage", { key: key() })); press(document.body, "mod+.", "mac"); expect(navigate).toHaveBeenCalledWith(binding.route);
  });
  it("initial install must not read during an unconfirmed ready notification", async () => {
    const read = vi.spyOn(Storage.prototype, "getItem");
    const mount = subscribeWorkspaceOwnerAdmission((snapshot) => { if (snapshot.state === "ready" && snapshot.session.subject === "custom-unit-b") install(); });
    const fail = subscribeWorkspaceOwnerAdmission((snapshot) => { if (snapshot.state === "ready" && snapshot.session.subject === "custom-unit-b") throw new Error("synthetic later observer failure"); });
    try { expect(() => setWorkspaceOwner("custom-unit-b")).toThrow(); expect(read).not.toHaveBeenCalled(); }
    finally { mount(); fail(); }
    await settle(); expect(read).not.toHaveBeenCalled();
  });

});

describe("pending custom installation confirmation lifetime (synthetic local UNIT)", () => {
  it("has no initial private read or dispatch until settled confirmation", async () => {
    seed(); const read = vi.spyOn(Storage.prototype, "getItem"); const { navigate } = install();
    expect(read).not.toHaveBeenCalled(); press(document.body, "mod+.", "mac"); expect(navigate).not.toHaveBeenCalled();
    await settle(); press(document.body, "mod+.", "mac"); expect(navigate).toHaveBeenCalledWith(binding.route);
  });
  it("disposal before confirmation refuses a later genuine resume", async () => {
    seed(); const owner = workspaceOwnerSession(); suspendWorkspaceOwner(); const read = vi.spyOn(Storage.prototype, "getItem");
    const { stop, navigate } = install(); stop(); resumeWorkspaceOwner(owner); await settle();
    expect(read).not.toHaveBeenCalled(); press(document.body, "mod+.", "mac"); expect(navigate).not.toHaveBeenCalled();
  });
  it("replacement before confirmation never adopts the new owner storage", async () => {
    seed(); suspendWorkspaceOwner(); const read = vi.spyOn(Storage.prototype, "getItem"); const { navigate } = install();
    setWorkspaceOwner("custom-unit-b"); await settle(); expect(read).not.toHaveBeenCalled();
    press(document.body, "mod+.", "mac"); expect(navigate).not.toHaveBeenCalled();
  });
});
