import { describe, expect, it } from "vitest";

import { adjacentPane, COMPANION_PANE, CORE_PANE, paneGeometry, paneKey, reconcilePaneOrder,
  reconcilePaneTiles, resizePaneTile, resizePaneTileByPixels, revealPane, spatialPaneNeighbor, swapAdjacentPane, swapPaneTiles } from "./paneFlowGeometry";
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

describe("SPR-01 M4: resizePaneTile (R8)", () => {
  //  x-split 0.5
  //  ├── leaf core
  //  └── y-split 0.6
  //      ├── leaf companion
  //      └── leaf a
  const tree: PaneTile = {
    kind: "split", axis: "x", ratio: 0.5,
    first: { kind: "leaf", target: CORE_PANE },
    second: {
      kind: "split", axis: "y", ratio: 0.6,
      first: { kind: "leaf", target: COMPANION_PANE },
      second: { kind: "leaf", target: a },
    },
  };

  it("adjusts the nearest ancestor split on the axis, growing the target's side", () => {
    // a sits second in the y-split: growing a means SHRINKING the first share.
    const grown = resizePaneTile(tree, a, "y", 0.05);
    expect(grown).not.toBeNull();
    expect(grown!.kind).toBe("split");
    if (grown!.kind === "split" && grown!.second.kind === "split") {
      expect(grown!.second.ratio).toBeCloseTo(0.55, 10);
      expect(grown!.ratio).toBe(0.5); // the x ancestor is untouched
    }
    // core sits FIRST in the x-split: growing core grows the ratio.
    const coreGrown = resizePaneTile(tree, CORE_PANE, "x", 0.05);
    expect(coreGrown!.kind).toBe("split");
    if (coreGrown!.kind === "split") expect(coreGrown!.ratio).toBeCloseTo(0.55, 10);
  });

  it("skips a nearer ancestor on the OTHER axis", () => {
    // companion's nearest ancestor is the y-split; an x nudge walks past it.
    const resized = resizePaneTile(tree, COMPANION_PANE, "x", 0.05);
    // companion is inside the x-split's SECOND child: growing it shrinks the ratio.
    if (resized!.kind === "split") expect(resized!.ratio).toBeCloseTo(0.45, 10);
    expect(resized!.kind === "split" && resized!.second.kind === "split" && resized!.second.ratio).toBe(0.6);
  });

  it("clamps at 0.1 and 0.9 (the packet's render clamp, at write time)", () => {
    let t: PaneTile | null = tree;
    for (let i = 0; i < 20; i++) t = resizePaneTile(t, a, "y", -0.05);
    expect(t!.kind === "split" && t!.second.kind === "split" && t!.second.ratio).toBe(0.9);
    for (let i = 0; i < 30; i++) t = resizePaneTile(t, a, "y", 0.05);
    expect(t!.kind === "split" && t!.second.kind === "split" && t!.second.ratio).toBe(0.1);
  });

  it("no axis-matching ancestor (or no target) is a same-reference no-op", () => {
    const flat: PaneTile = { kind: "split", axis: "x", ratio: 0.5, first: { kind: "leaf", target: CORE_PANE }, second: { kind: "leaf", target: COMPANION_PANE } };
    expect(resizePaneTile(flat, CORE_PANE, "y", 0.05)).toBe(flat);
    expect(resizePaneTile(tree, b, "y", 0.05)).toBe(tree);
    expect(resizePaneTile(null, CORE_PANE, "x", 0.05)).toBeNull();
  });

  it("resizePaneTileByPixels converts px against the measured parent extent", () => {
    // placements for the x split [core | companion]: working 1000×700 with
    // the 10 px gap → 980 wide; the split's extent along x is 980 px.
    const flat: PaneTile = { kind: "split", axis: "x", ratio: 0.5, first: { kind: "leaf", target: CORE_PANE }, second: { kind: "leaf", target: COMPANION_PANE } };
    const placements = [
      { target: CORE_PANE, rect: { x: 10, y: 10, width: 485, height: 680 } },
      { target: COMPANION_PANE, rect: { x: 505, y: 10, width: 485, height: 680 } },
    ];
    const resized = resizePaneTileByPixels(flat, placements, CORE_PANE, "x", 100);
    expect(resized!.kind === "split" && resized!.ratio).toBeCloseTo(0.5 + 100 / 980, 10);
    // A missing measurement is a refusal, not a guess.
    expect(resizePaneTileByPixels(flat, [], CORE_PANE, "x", 100)).toBeNull();
  });
});

describe("SPR-01 M5: the maximize level (R12)", () => {
  const geometryInput = { width: 1000, height: 700, arrangement: "horizontal" as const, order, tiles: null, zoom: null };
  it("maximize fills the work area edge to edge where zoom keeps the gap inset", () => {
    const maximized = paneGeometry({ ...geometryInput, maximize: a });
    expect(maximized.kind).toBe("measured");
    if (maximized.kind === "measured") {
      expect(maximized.placements).toEqual([{ target: a, rect: { x: 0, y: 0, width: 1000, height: 700 } }]);
    }
    const zoomed = paneGeometry({ ...geometryInput, zoom: a });
    if (zoomed.kind === "measured") {
      expect(zoomed.placements[0].rect).toEqual({ x: 10, y: 10, width: 980, height: 680 });
    }
  });
  it("an absent maximize target is a normal layout, and zoom wins if both are set", () => {
    const absent = paneGeometry({ ...geometryInput, maximize: { kind: "window", id: "gone" } });
    expect(absent.kind === "measured" && absent.placements.length).toBe(order.length);
    const both = paneGeometry({ ...geometryInput, zoom: b, maximize: a });
    expect(both.kind === "measured" && both.placements[0].target).toEqual(b);
  });
});
