import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  readCustomHotkeys,
  retireLegacyWorkspaceSnapshots,
} from "./persistence";

const HOTKEY_KEY = "antiek.workspace.custom-hotkeys";
const VALID_HOTKEYS = {
  schemaVersion: 1,
  bindings: [{
    id: "binding-1",
    spec: "mod+.",
    route: "/inv/inv-1",
    entityId: "inv-1",
    entityKind: "investigation",
    label: "Investigation one",
  }],
};

beforeEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
  window.history.replaceState({}, "", "/");
});

describe("legacy workspace retirement", () => {
  it("deletes hostile layouts without reading values or touching preferences", () => {
    const hostile = JSON.stringify({
      panels: { foreign: { props: { html: "<script>x</script>", prompt: "secret", sourceUrl: "https://foreign", investigationId: "other", nested: { arbitrary: true } } } },
    });
    window.localStorage.setItem("antiek.workspace.global", hostile);
    window.localStorage.setItem("antiek.workspace.route./inv/:id", hostile);
    window.localStorage.setItem("antiek.workspace.inv.foreign", hostile);
    window.localStorage.setItem(HOTKEY_KEY, JSON.stringify(VALID_HOTKEYS));
    window.localStorage.setItem("antiek.notebook.draft", "keep");

    const getItem = vi.spyOn(Storage.prototype, "getItem");
    retireLegacyWorkspaceSnapshots();
    retireLegacyWorkspaceSnapshots();

    expect(getItem).not.toHaveBeenCalled();
    expect(window.localStorage.getItem("antiek.workspace.global")).toBeNull();
    expect(window.localStorage.getItem("antiek.workspace.route./inv/:id")).toBeNull();
    expect(window.localStorage.getItem("antiek.workspace.inv.foreign")).toBeNull();
    expect(window.localStorage.getItem(HOTKEY_KEY)).toBe(JSON.stringify(VALID_HOTKEYS));
    expect(window.localStorage.getItem("antiek.notebook.draft")).toBe("keep");
  });

  it.each([
    "valid-looking",
    "%not-base64%",
    "",
    "x".repeat(100_000),
  ])("removes opaque ws value without decoding (case %#)", (value) => {
    window.history.replaceState({}, "", `/read?keep=a%2Bb&ws=${value}&other=two#section%201`);
    const atobSpy = vi.spyOn(globalThis, "atob");
    retireLegacyWorkspaceSnapshots();
    expect(atobSpy).not.toHaveBeenCalled();
    expect(window.location.pathname + window.location.search + window.location.hash).toBe(
      "/read?keep=a%2Bb&other=two#section%201",
    );
  });

  it("removes duplicate and empty ws parameters while preserving other order and hash", () => {
    window.history.replaceState({}, "", "/read?first=1&ws=&middle=2&ws=duplicate&last=3#hash");
    retireLegacyWorkspaceSnapshots();
    expect(window.location.pathname + window.location.search + window.location.hash).toBe(
      "/read?first=1&middle=2&last=3#hash",
    );
  });

  it("removes a bare ws segment without an equals sign", () => {
    window.history.replaceState({}, "", "/read?first=1&ws&last=3#hash");
    retireLegacyWorkspaceSnapshots();
    expect(window.location.pathname + window.location.search + window.location.hash).toBe(
      "/read?first=1&last=3#hash",
    );
  });

  it("preserves unrelated query bytes rather than normalizing their encoding", () => {
    window.history.replaceState({}, "", "/read?space=a%20b&plus=a+b&tilde=~&ws=opaque&encoded=%2f%2F#h%20x");
    retireLegacyWorkspaceSnapshots();
    expect(window.location.pathname + window.location.search + window.location.hash).toBe(
      "/read?space=a%20b&plus=a+b&tilde=~&encoded=%2f%2F#h%20x",
    );
  });

  it("fails closed when storage cleanup and history replacement throw", () => {
    window.localStorage.setItem("antiek.workspace.global", "hostile");
    window.history.replaceState({}, "", "/?ws=opaque&keep=1#h");
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(window.history, "replaceState").mockImplementation(() => { throw new Error("blocked"); });
    expect(() => retireLegacyWorkspaceSnapshots()).not.toThrow();
  });
});

describe("closed custom-hotkey preference", () => {
  it("accepts the exact existing v1 schema", () => {
    window.localStorage.setItem(HOTKEY_KEY, JSON.stringify(VALID_HOTKEYS));
    expect(readCustomHotkeys()).toEqual(VALID_HOTKEYS);
  });

  it.each([
    { ...VALID_HOTKEYS, extra: true },
    { ...VALID_HOTKEYS, bindings: [{ ...VALID_HOTKEYS.bindings[0], extra: true }] },
    { ...VALID_HOTKEYS, bindings: [{ ...VALID_HOTKEYS.bindings[0], entityKind: "admin" }] },
    { ...VALID_HOTKEYS, bindings: [{ ...VALID_HOTKEYS.bindings[0], route: "https://foreign.example" }] },
    { ...VALID_HOTKEYS, bindings: [{ ...VALID_HOTKEYS.bindings[0], spec: "mod+k" }] },
    { ...VALID_HOTKEYS, bindings: [{ ...VALID_HOTKEYS.bindings[0], spec: "MOD+." }] },
    { ...VALID_HOTKEYS, bindings: [VALID_HOTKEYS.bindings[0], VALID_HOTKEYS.bindings[0]] },
    { ...VALID_HOTKEYS, bindings: Array.from({ length: 101 }, () => VALID_HOTKEYS.bindings[0]) },
  ])("rejects permissive or unbounded envelopes", (value) => {
    window.localStorage.setItem(HOTKEY_KEY, JSON.stringify(value));
    expect(readCustomHotkeys()).toEqual({ schemaVersion: 1, bindings: [] });
  });
});
