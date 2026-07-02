import { describe, expect, it } from "vitest";

import { EMPTY_SNAPSHOT } from "../workspace/panel.types";
import { nextZ } from "../workspace/panelLayoutLogic";
import { WINDOW_Z_BASE } from "../workspace/windowsStore";
import { FLOATING_Z_BASE } from "./elevation";
import { Z_LADDER_ORDER, forceAbove, zIndex } from "./zIndex";

/**
 * These tests PIN the z-index ladder. Each `toBe(<number>)` below is the exact
 * value that surface used BEFORE consolidation — so this file is a tripwire: a
 * future edit that drifts a layer (or reorders the stack) fails here. This is a
 * pure-consolidation milestone, so the assertions are intentionally exact.
 */
describe("zIndex ladder — pinned values (no behaviour change)", () => {
  it("pins each named layer to its prior magic number", () => {
    // Re-exported numbers, value-for-value from the pre-consolidation sources:
    expect(zIndex.raised).toBe(1); //                docked-over-dock-chrome
    expect(zIndex.floatingPanelBase).toBe(2); //     elevation.ts FLOATING_Z_BASE
    expect(zIndex.sceneBadge).toBe(5); //            SceneStatusBadge.tsx (#144)
    expect(zIndex.windowBase).toBe(40); //           windowsStore WINDOW_Z_BASE
    expect(zIndex.floatingPanelCeiling).toBe(50); // WorkspaceStore "z = 2…50"
    expect(zIndex.mascot).toBe(60); //               PenguinMascot z-[60]
    expect(zIndex.modal).toBe(100); //               LemonModal z-[100]
    expect(zIndex.popover).toBe(120); //             SlashMenu z-[120]
    expect(zIndex.adOverlay).toBe(150); //           AdBorder z-[150]
    expect(zIndex.toast).toBe(200); //               LemonToast z-[200]
  });

  it("WINDOW_Z_BASE is still 40 and sources from the ladder (no value change)", () => {
    expect(WINDOW_Z_BASE).toBe(40);
    expect(WINDOW_Z_BASE).toBe(zIndex.windowBase);
  });

  it("floatingPanelBase is still 2 and the store's first floating z materialises to it", () => {
    expect(zIndex.floatingPanelBase).toBe(2);
    expect(FLOATING_Z_BASE).toBe(2);
    expect(FLOATING_Z_BASE).toBe(zIndex.floatingPanelBase);
    // The first floating panel's z is `nextZ(EMPTY_SNAPSHOT.zCounter)`. Pin that
    // it still equals the named base — catches a drift in either direction.
    expect(nextZ(EMPTY_SNAPSHOT.zCounter)).toBe(zIndex.floatingPanelBase);
  });

  it("is strictly monotonic in stacking order (bottom → top)", () => {
    const values = Z_LADDER_ORDER.map((name) => zIndex[name]);
    for (let i = 1; i < values.length; i++) {
      expect(values[i]).toBeGreaterThan(values[i - 1]);
    }
    // Spot-check the load-bearing layering: a toast never sits under a modal,
    // a window always sits over a floating panel's base, etc.
    expect(zIndex.raised).toBeLessThan(zIndex.floatingPanelBase);
    expect(zIndex.floatingPanelBase).toBeLessThan(zIndex.windowBase);
    expect(zIndex.windowBase).toBeLessThan(zIndex.modal);
    expect(zIndex.modal).toBeLessThan(zIndex.toast);
  });

  it("covers every named layer in the ordering array (no orphan layer)", () => {
    const named = Object.keys(zIndex).sort();
    const ordered = [...Z_LADDER_ORDER].sort();
    expect(ordered).toEqual(named);
  });

  it("the ladder is frozen (a value can't be mutated at runtime)", () => {
    expect(Object.isFrozen(zIndex)).toBe(true);
  });

  it("forceAbove returns the smallest z strictly above a base (named `zCounter + 1`)", () => {
    expect(forceAbove(zIndex.windowBase)).toBe(41);
    expect(forceAbove(zIndex.modal)).toBe(101);
    expect(forceAbove(zIndex.windowBase)).toBeGreaterThan(zIndex.windowBase);
  });
});
