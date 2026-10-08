import { describe, expect, it } from "vitest";

import { adjacentPane, COMPANION_PANE, CORE_PANE, paneGeometry, paneKey, reconcilePaneOrder,
  reconcilePaneTiles, revealPane, spatialPaneNeighbor, swapAdjacentPane, swapPaneTiles } from "./paneFlowGeometry";
import { migratePanePreferences, parseLegacyPanePreset, parsePaneArrangement } from "./persistence";
import type { PaneTarget, PaneTile } from "./panel.types";

const a: PaneTarget = { kind: "window", id: "control:a" };
const b: PaneTarget = { kind: "window", id: "control:b" };
const order = [CORE_PANE, COMPANION_PANE, a, b];

describe("pane order and retained tiles", () => {
  it("preserves the admitted presentation order through a z-order change", () => {
    expect(reconcilePaneOrder(order, [b, a, CORE_PANE, COMPANION_PANE])).toEqual(order);
  });
  it("prunes removed identities and appends only actual new admissions once", () => {
    expect(reconcilePaneOrder([a, a, b], [CORE_PANE, b])).toEqual([b, CORE_PANE]);
  });
  it("has total nonwrapping adjacency at both edges and for an absent target", () => {
    expect(adjacentPane(order, CORE_PANE, -1)).toBeNull();
    expect(adjacentPane(order, b, 1)).toBeNull();
    expect(adjacentPane([], a, 1)).toBeNull();
    expect(adjacentPane(order, { kind: "window", id: "absent" }, 1)).toBeNull();
    expect(adjacentPane(order, a, -1)).toEqual(COMPANION_PANE);
  });
  it("swaps semantic neighbors without changing their identities", () => {
    expect(swapAdjacentPane(order, a, -1)).toEqual([CORE_PANE, a, COMPANION_PANE, b]);
    expect(swapAdjacentPane(order, b, 1)).toBe(order);
  });
  it("retains the existing split axes and ratios when a new host arrives", () => {
    const tree: PaneTile = { kind: "split", axis: "y", ratio: 0.37,
      first: { kind: "leaf", target: CORE_PANE }, second: { kind: "leaf", target: COMPANION_PANE } };
    expect(reconcilePaneTiles(tree, [CORE_PANE, COMPANION_PANE])).toEqual(tree);
    const added = reconcilePaneTiles(tree, [CORE_PANE, COMPANION_PANE, a]);
    expect(added?.kind).toBe("split");
    if (added?.kind === "split") { expect(added.axis).toBe("y"); expect(added.ratio).toBe(0.37); }
  });
  it("swaps tiled identities without rebuilding split topology", () => {
    const tree: PaneTile = { kind: "split", axis: "x", ratio: 0.61,
      first: { kind: "leaf", target: a }, second: { kind: "leaf", target: b } };
    expect(swapPaneTiles(tree, a, b)).toEqual({ ...tree,
      first: { kind: "leaf", target: b }, second: { kind: "leaf", target: a } });
    expect(reconcilePaneTiles(tree, [b])).toEqual({ kind: "leaf", target: b });
  });
  it("selects tiled neighbors by actual spatial row before horizontal distance", () => {
    const placements = [
      { target: CORE_PANE, rect: { x: 10, y: 10, width: 480, height: 300 } },
      { target: a, rect: { x: 500, y: 10, width: 480, height: 300 } },
      { target: b, rect: { x: 500, y: 320, width: 480, height: 300 } },
    ];
    expect(spatialPaneNeighbor(placements, CORE_PANE, 1)).toEqual(a);
    expect(spatialPaneNeighbor(placements, CORE_PANE, -1)).toBeNull();
    expect(spatialPaneNeighbor(placements, b, -1)).toEqual(CORE_PANE);
  });
});

describe("measured pane geometry and reveal", () => {
  it.each([1, 2, 15, 40])("places %i admitted panes without a logical cap", (count) => {
    const targets = Array.from({ length: count }, (_, id): PaneTarget => ({ kind: "window", id: String(id) }));
    const result = paneGeometry({ width: 1000, height: 700, arrangement: "horizontal", order: targets, tiles: null, zoom: null });
    expect(result.kind).toBe("measured");
    if (result.kind !== "measured") return;
    expect(result.placements).toHaveLength(count);
    expect(result.placements.map(({ target }) => paneKey(target))).toEqual(targets.map(paneKey));
    expect(result.placements.every(({ rect }) => rect.width === 490 && rect.height === 680)).toBe(true);
    expect(result.width).toBe(Math.max(1000, 10 + count * 500));
  });
  it.each([0, -1, NaN, Infinity])("refuses unmeasured width %s without a browser-width fallback", (width) => {
    expect(paneGeometry({ width, height: 700, arrangement: "horizontal", order, tiles: null, zoom: null })).toEqual({ kind: "unmeasured" });
  });
  it("reveals only the obscured horizontal edge and clamps to the current extent", () => {
    const rect = { x: 1010, y: 10, width: 490, height: 680 };
    expect(revealPane({ rect, viewportWidth: 1000, extentWidth: 2010, scrollLeft: 0 })).toBe(500);
    expect(revealPane({ rect, viewportWidth: 1000, extentWidth: 2010, scrollLeft: 500 })).toBe(500);
    expect(revealPane({ rect: { ...rect, x: 10 }, viewportWidth: 1000, extentWidth: 2010, scrollLeft: 500 })).toBe(10);
    expect(revealPane({ rect, viewportWidth: 0, extentWidth: 2010, scrollLeft: 500 })).toBeNull();
  });
  it("aligns an oversized pane's leading edge and zooms only an admitted identity", () => {
    expect(revealPane({ rect: { x: 370, y: 10, width: 360, height: 500 }, viewportWidth: 300, extentWidth: 740, scrollLeft: 0 })).toBe(370);
    const result = paneGeometry({ width: 1000, height: 700, arrangement: "horizontal", order, tiles: null, zoom: a });
    expect(result).toEqual({ kind: "measured", width: 1000, height: 700,
      placements: [{ target: a, rect: { x: 10, y: 10, width: 980, height: 680 } }] });
  });
});

describe("explicit preference migration", () => {
  it("distinguishes absent, invalid and valid old/new values", () => {
    expect(parsePaneArrangement(null)).toEqual({ kind: "absent" });
    expect(parsePaneArrangement("{}")).toEqual({ kind: "invalid" });
    expect(parsePaneArrangement('{"schemaVersion":1,"arrangement":"tiled"}')).toEqual({ kind: "valid", value: "tiled" });
    expect(parseLegacyPanePreset('{"schemaVersion":1,"preset":"unknown"}')).toEqual({ kind: "invalid" });
  });
  it.each(["docked", "omarchy-inset"])("preserves an explicitly selected %s as legacy", (preset) => {
    expect(migratePanePreferences(null, JSON.stringify({ schemaVersion: 1, preset }))).toEqual({ paneArrangement: "legacy", layoutPreset: preset });
    expect(migratePanePreferences("malformed", JSON.stringify({ schemaVersion: 1, preset }))).toEqual({ paneArrangement: "legacy", layoutPreset: preset });
  });
  it("defaults a fresh desktop to horizontal and honors an explicit new arrangement", () => {
    expect(migratePanePreferences(null, null)).toEqual({ paneArrangement: "horizontal", layoutPreset: "omarchy-inset" });
    expect(migratePanePreferences('{"schemaVersion":1,"arrangement":"tiled"}', '{"schemaVersion":1,"preset":"docked"}'))
      .toEqual({ paneArrangement: "tiled", layoutPreset: "docked" });
  });
});
