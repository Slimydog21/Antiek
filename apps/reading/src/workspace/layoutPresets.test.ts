/**
 * layoutPresets.test.ts — the named-layout store (save/list/apply/delete).
 */
import { beforeEach, describe, expect, it } from "vitest";

import { useWorkspace } from "./WorkspaceStore";
import {
  applyLayoutPreset,
  deleteLayoutPreset,
  listLayoutPresets,
  saveLayoutPreset,
} from "./layoutPresets";
import { project } from "./persistence";

describe("layout presets", () => {
  beforeEach(() => {
    window.localStorage.clear();
    useWorkspace.getState().reset();
  });

  it("starts empty", () => {
    expect(listLayoutPresets()).toEqual([]);
  });

  it("saves and lists a preset from the current snapshot", () => {
    const id = useWorkspace.getState().open("FakeSidebar", {}, { mode: "docked-left" });
    const snapshot = project(useWorkspace.getState());
    saveLayoutPreset("research", snapshot);
    const presets = listLayoutPresets();
    expect(presets).toHaveLength(1);
    expect(presets[0].name).toBe("research");
    expect(presets[0].snapshot.panels[id]).toBeDefined();
  });

  it("saving the same name replaces, not duplicates", () => {
    saveLayoutPreset("x", project(useWorkspace.getState()));
    saveLayoutPreset("x", project(useWorkspace.getState()));
    expect(listLayoutPresets()).toHaveLength(1);
  });

  it("rejects empty names", () => {
    expect(() => saveLayoutPreset("   ", project(useWorkspace.getState()))).toThrow();
  });

  it("applies a saved preset (panels materialize)", () => {
    const id = useWorkspace.getState().open("FakeSidebar", {}, { mode: "docked-left" });
    saveLayoutPreset("research", project(useWorkspace.getState()));
    useWorkspace.getState().reset();
    expect(useWorkspace.getState().panels[id]).toBeUndefined();
    expect(applyLayoutPreset("research")).toBe(true);
    expect(useWorkspace.getState().panels[id]).toBeDefined();
    expect(useWorkspace.getState().dockLeftIds).toContain(id);
  });

  it("applying a missing preset returns false", () => {
    expect(applyLayoutPreset("nope")).toBe(false);
  });

  it("delete removes the preset", () => {
    saveLayoutPreset("x", project(useWorkspace.getState()));
    deleteLayoutPreset("x");
    expect(listLayoutPresets()).toEqual([]);
  });

  it("an applied preset never resurrects zoom (transient mode)", () => {
    const id = useWorkspace.getState().open("FakeSidebar", {}, { mode: "docked-left" });
    saveLayoutPreset("research", project(useWorkspace.getState()));
    useWorkspace.getState().toggleZoom(id);
    useWorkspace.getState().reset();
    applyLayoutPreset("research");
    expect(useWorkspace.getState().zoomedPanelId).toBeNull();
  });
});
