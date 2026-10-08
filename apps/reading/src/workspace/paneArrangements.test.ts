/**
 * paneArrangements.test.ts — SPR-01 M6, the pure model + the persistence
 * blob + flag-off absence. The flow-mode acceptance criteria (jump/cycle/
 * move through the real store and dispatcher) live in
 * paneArrangements.flow.test.tsx, which sets antiek.flag.pane.flow before
 * any import reads it; THIS file is the default flag-OFF world every other
 * test sees.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setWorkspaceOwner } from "../lib/accountWorkspaceOwner";
import {
  applyPreset,
  emptyProjectSlots,
  isArrangementSlot,
  moveTargetBetweenPresets,
  nextExistingSlot,
  snapshotPreset,
  visibleTargets,
  type ArrangementPreset,
  type ProjectSlots,
} from "./paneArrangements";
import { CORE_PANE, COMPANION_PANE, paneKey, samePane } from "./paneFlowGeometry";
import type { PaneTarget } from "./panel.types";
import {
  clearPaneArrangements,
  readPaneArrangements,
  writePaneArrangements,
} from "./persistence";
import { createActionHandlers } from "./shortcuts";
import { disablePersistence, useWorkspace } from "./WorkspaceStore";
import { useWindows } from "./windowsStore";

const WIN_A: PaneTarget = { kind: "window", id: "win:a" };
const WIN_B: PaneTarget = { kind: "window", id: "win:b" };

function projectWith(presets: ProjectSlots["presets"], current: ProjectSlots["current"] = "1"): ProjectSlots {
  return { ...emptyProjectSlots(), current, presets };
}

afterEach(() => {
  clearPaneArrangements();
  setWorkspaceOwner(null);
  useWindows.getState().reset();
  useWorkspace.getState().reset();
  vi.restoreAllMocks();
});

describe("the pure arrangement model", () => {
  it("a preset never records legacy and never carries zoom (R12)", () => {
    expect(snapshotPreset({ paneArrangement: "legacy", paneOrder: [CORE_PANE], paneTiles: null })).toBeNull();
    const preset = snapshotPreset({ paneArrangement: "tiled", paneOrder: [CORE_PANE], paneTiles: { kind: "leaf", target: CORE_PANE } });
    expect(preset).toEqual({ arrangement: "tiled", order: [CORE_PANE], tiles: { kind: "leaf", target: CORE_PANE } });
    expect(Object.keys(preset!)).not.toContain("zoom");
  });

  it("visibleTargets: unassigned panes join the current view; another slot's members park", () => {
    const admitted = [CORE_PANE, COMPANION_PANE, WIN_A, WIN_B];
    // No presets at all: the pre-M6 view — everything admitted is visible.
    expect(visibleTargets(admitted, emptyProjectSlots())).toEqual(admitted);
    const project = projectWith({ "1": { arrangement: "horizontal", order: [CORE_PANE, WIN_A], tiles: null } });
    // WIN_A is a member of slot 1 (current); WIN_B is unassigned → both
    // visible. Assign WIN_B to slot 2 and it parks.
    expect(visibleTargets(admitted, project)).toEqual([CORE_PANE, COMPANION_PANE, WIN_A, WIN_B]);
    const parked = projectWith({
      "1": { arrangement: "horizontal", order: [CORE_PANE, WIN_A], tiles: null },
      "2": { arrangement: "horizontal", order: [WIN_B], tiles: null },
    });
    expect(visibleTargets(admitted, parked)).toEqual([CORE_PANE, COMPANION_PANE, WIN_A]);
    // …and slot 2's view shows its own member plus the unassigned; CORE
    // and WIN_A park with slot 1.
    expect(visibleTargets(admitted, parked, "2")).toEqual([COMPANION_PANE, WIN_B]);
  });

  it("applyPreset drops a target whose host is gone — named, never substituted (S01/S09)", () => {
    const preset: ArrangementPreset = {
      arrangement: "tiled",
      order: [WIN_A, WIN_B, CORE_PANE],
      tiles: { kind: "split", axis: "x", ratio: 0.5, first: { kind: "leaf", target: WIN_A }, second: { kind: "leaf", target: WIN_B } },
    };
    const applied = applyPreset(preset, [CORE_PANE, WIN_A], projectWith({ "1": preset }), "1");
    expect(applied.dropped).toEqual(["window:win:b"]);
    expect(applied.order).toEqual([WIN_A, CORE_PANE]);
    // The gone host's tile is pruned, never replaced with another pane; the
    // admitted core pane re-joins the tile tree (reconcile's standing rule).
    expect(JSON.stringify(applied.tiles)).not.toContain("win:b");
    expect(JSON.stringify(applied.tiles)).toContain("win:a");
  });

  it("nextExistingSlot skips empty slots and wraps; null when no other slot exists", () => {
    const project = projectWith({
      "1": { arrangement: "horizontal", order: [CORE_PANE], tiles: null },
      "4": { arrangement: "horizontal", order: [CORE_PANE], tiles: null },
      "0": { arrangement: "horizontal", order: [CORE_PANE], tiles: null },
    });
    expect(nextExistingSlot(project, 1)).toBe("4");
    expect(nextExistingSlot(project, -1)).toBe("0");
    expect(nextExistingSlot({ ...project, current: "4" }, 1)).toBe("0");
    expect(nextExistingSlot({ ...project, current: "0" }, 1)).toBe("1");
    expect(nextExistingSlot(projectWith({ "1": { arrangement: "horizontal", order: [CORE_PANE], tiles: null } }), 1)).toBeNull();
    expect(nextExistingSlot(emptyProjectSlots(), 1)).toBeNull();
  });

  it("moveTargetBetweenPresets: out of the source, appended to a fresh destination with the source's arrangement", () => {
    const source: ArrangementPreset = { arrangement: "tiled", order: [CORE_PANE, WIN_A], tiles: null };
    const moved = moveTargetBetweenPresets(source, null, WIN_A);
    expect(moved).not.toBeNull();
    expect(moved!.source.order).toEqual([CORE_PANE]);
    expect(moved!.destination).toEqual({ arrangement: "tiled", order: [WIN_A], tiles: { kind: "leaf", target: WIN_A } });
    // A target not in the source moves nothing.
    expect(moveTargetBetweenPresets(source, null, WIN_B)).toBeNull();
  });

  it("isArrangementSlot admits exactly 1–9 and 0", () => {
    for (const slot of ["1", "5", "9", "0"]) expect(isArrangementSlot(slot)).toBe(true);
    for (const bad of ["10", "", "a", 1, null]) expect(isArrangementSlot(bad)).toBe(false);
  });
});

describe("the arrangements blob (persistence.ts)", () => {
  beforeEach(() => setWorkspaceOwner("arr-test"));

  it("round-trips every project's slots deep-equal", () => {
    const map = {
      "project-one": projectWith({
        "1": { arrangement: "tiled" as const, order: [CORE_PANE, WIN_A], tiles: { kind: "leaf" as const, target: WIN_A } },
      }),
      "project-two": { ...projectWith({}), current: "3" as const, last: "1" as const },
    };
    writePaneArrangements(map);
    expect(readPaneArrangements()).toEqual(map);
  });

  it("an unknown schemaVersion discards the blob WHOLE, with a warning", () => {
    writePaneArrangements({ "project-one": projectWith({}) });
    const key = Object.keys(window.localStorage).find((k) => k.includes("pane-arrangements"))!;
    window.localStorage.setItem(key, JSON.stringify({ schemaVersion: 2, projects: {} }));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(readPaneArrangements()).toEqual({});
    expect(warn).toHaveBeenCalledOnce();
  });

  it("a structurally invalid entry discards the blob whole, never a half-trusted preset", () => {
    const key = (() => { writePaneArrangements({}); return Object.keys(window.localStorage).find((k) => k.includes("pane-arrangements"))!; })();
    window.localStorage.setItem(key, JSON.stringify({
      schemaVersion: 1,
      projects: {
        good: projectWith({}),
        bad: { current: "1", last: null, presets: { "1": { arrangement: "sideways", order: [], tiles: null } } },
      },
    }));
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(readPaneArrangements()).toEqual({});
    expect(warn).toHaveBeenCalledOnce();
  });
});

describe("flag OFF: the feature is absent", () => {
  beforeEach(() => {
    disablePersistence();
    useWorkspace.getState().reset();
  });

  it("a legacy arrangement refuses every arrangement key (the only state a flag-off operator can reach)", () => {
    const ws = () => useWorkspace.getState();
    expect(ws().paneArrangement).toBe("legacy");
    expect(ws().jumpPaneArrangement("2")).toBe(false);
    expect(ws().moveFocusedPaneToArrangement("2")).toBe(false);
    expect(ws().cyclePaneArrangement(1)).toBe(false);
    expect(ws().jumpToLastPaneArrangement()).toBe(false);
    expect(ws().paneSlots).toEqual({});
  });

  it("the dispatcher binds no arrangement handler with the flag off (the rows are declared pending)", () => {
    const handlers = createActionHandlers((() => {}) as never);
    expect(handlers["pane.arrangement1"]).toBeUndefined();
    expect(handlers["pane.moveToArrangement1"]).toBeUndefined();
    expect(handlers["pane.nextArrangement"]).toBeUndefined();
  });
});

describe("ownership rules (Grok adversarial review of #3772)", () => {
  it("hole 2: applyPreset never resurrects a parked pane, even handed the full admitted list", () => {
    // WIN_B is parked on slot 2; applying slot 1's preset must not bring it back.
    const project = projectWith({
      "1": { arrangement: "horizontal", order: [CORE_PANE], tiles: null },
      "2": { arrangement: "horizontal", order: [WIN_B], tiles: null },
    });
    const applied = applyPreset(project.presets["1"]!, [CORE_PANE, COMPANION_PANE, WIN_A, WIN_B], project, "1");
    expect(applied.order.map(paneKey)).not.toContain("window:win:b");
    // Unassigned admitted panes still join (the intent's other half).
    expect(applied.order.map(paneKey)).toContain("core");
    expect(applied.order.map(paneKey)).toContain("window:win:a");
  });

  it("hole 3: moving onto a slot that already lists the pane never stores it twice", () => {
    const source: ArrangementPreset = { arrangement: "horizontal", order: [CORE_PANE, WIN_A], tiles: null };
    // The destination already lists the pane (the dual-membership state
    // hole 1 produced): the move must leave it there exactly once.
    const destination: ArrangementPreset = { arrangement: "horizontal", order: [WIN_A], tiles: null };
    const moved = moveTargetBetweenPresets(source, destination, WIN_A)!;
    expect(moved.source.order.map(paneKey)).toEqual(["core"]);
    expect(moved.destination.order.filter((t) => samePane(t, WIN_A))).toHaveLength(1);
  });
});
