import { beforeEach, describe, expect, it } from "vitest";

import { isWindowEligible, openNewWindow } from "./openWindow";
import { MAX_WINDOWS, useWindows } from "../../workspace/windowsStore";

describe("openNewWindow", () => {
  beforeEach(() => useWindows.getState().reset());

  it("registers research-chase as window-native and creates fresh concurrent instances", () => {
    expect(isWindowEligible("research-chase")).toBe(true);
    const first = openNewWindow("research-chase", { spawnContext: "first", parentInvestigationId: "read-a" });
    const second = openNewWindow("research-chase", { spawnContext: "second", parentInvestigationId: "read-a" });
    expect(first).not.toBe(second);
    expect(useWindows.getState().order).toEqual([first, second]);
    expect(useWindows.getState().windows[first].payload).toEqual({ spawnContext: "first", parentInvestigationId: "read-a" });
    expect(useWindows.getState().windows[second].payload).toEqual({ spawnContext: "second", parentInvestigationId: "read-a" });
    expect(first).not.toContain("first");
    expect(second).not.toContain("second");
  });

  it("can replace the oldest at the shared cap for an exact requested chase", () => {
    for (let i = 0; i < MAX_WINDOWS; i += 1) {
      useWindows.getState().open("library", { i }, { id: `existing:${i}` });
    }
    const id = openNewWindow(
      "research-chase",
      { spawnContext: "exact passage", parentInvestigationId: "read-a" },
      { replaceOldestAtLimit: true },
    );
    expect(useWindows.getState().order).toHaveLength(MAX_WINDOWS);
    expect(useWindows.getState().windows["existing:0"]).toBeUndefined();
    expect(useWindows.getState().windows[id].payload.spawnContext).toBe("exact passage");
  });

  it("never evicts the initiating reader when replacing at the cap", () => {
    useWindows.getState().open("reader", {}, { id: "reader:source" });
    for (let i = 1; i < MAX_WINDOWS; i += 1) {
      useWindows.getState().open("library", { i }, { id: `existing:${i}` });
    }
    const id = openNewWindow(
      "research-chase",
      { spawnContext: "from the source reader", parentInvestigationId: "read-a" },
      { replaceOldestAtLimit: true, preserveIdsAtLimit: ["reader:source"] },
    );
    expect(useWindows.getState().windows["reader:source"]).toBeDefined();
    expect(useWindows.getState().windows["existing:1"]).toBeUndefined();
    expect(useWindows.getState().windows[id]).toBeDefined();
  });
});
