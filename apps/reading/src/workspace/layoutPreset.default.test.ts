import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { clearLayoutPreset, readLayoutPreset, writeLayoutPreset } from "./persistence";

const KEY = "antiek.workspace.layout-preset";

beforeEach(() => {
  window.localStorage.clear();
  vi.resetModules();
});

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe("the cockpit is the workspace default", () => {
  it.each([
    null,
    "null",
    "{",
    JSON.stringify({ schemaVersion: 99, preset: "docked" }),
    JSON.stringify({ schemaVersion: 1, preset: null }),
    JSON.stringify({ schemaVersion: 1 }),
    JSON.stringify({ schemaVersion: 1, preset: "unknown" }),
  ])("starts in the cockpit when storage contains %s", (raw) => {
    if (raw !== null) window.localStorage.setItem(KEY, raw);
    expect(readLayoutPreset()).toBe("omarchy-inset");
  });

  it("initializes a fresh store and records its explicit preset without a user toggle", async () => {
    expect(window.localStorage.getItem(KEY)).toBeNull();
    const { useWorkspace } = await import("./WorkspaceStore");
    expect(useWorkspace.getState().layoutPreset).toBe("omarchy-inset");
    expect(JSON.parse(window.localStorage.getItem(KEY)!)).toEqual({
      schemaVersion: 1,
      preset: "omarchy-inset",
    });
  });

  it.each(["docked", "omarchy-inset"] as const)("keeps an explicit %s choice on startup", async (preset) => {
    writeLayoutPreset(preset);
    const { useWorkspace } = await import("./WorkspaceStore");
    expect(useWorkspace.getState().layoutPreset).toBe(preset);
    expect(readLayoutPreset()).toBe(preset);
  });

  it("returns to the cockpit after clearing a stored docked choice", () => {
    writeLayoutPreset("docked");
    clearLayoutPreset();
    expect(readLayoutPreset()).toBe("omarchy-inset");
  });

  it("starts in the cockpit even when browser storage is unavailable", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("disabled"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("disabled"); });
    const { useWorkspace } = await import("./WorkspaceStore");
    expect(useWorkspace.getState().layoutPreset).toBe("omarchy-inset");
  });
});
