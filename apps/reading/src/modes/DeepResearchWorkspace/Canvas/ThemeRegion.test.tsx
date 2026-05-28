/**
 * ThemeRegion.test.tsx — DRW block-canvas M4 (theme grouping, cuttable).
 *
 * Pins the criteria:
 *  - a region groups a set of blocks and is visible on the canvas (a labelled
 *    rectangle bounding its members);
 *  - the region geometry is DERIVED from member positions (regionBounds), so
 *    it reflows when a member moves — no separate persistence;
 *  - an empty region renders nothing (no zero-size box).
 *
 * Persistence of grouping rides the SAME block.positioned typed event
 * (region_id / region_label) — verified at the schema level (events.py) and
 * the Canvas grouping derivation; there is no side store.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import ThemeRegion from "./ThemeRegion";
import { regionBounds, type BlockPosition } from "./canvasLayout";

afterEach(() => cleanup());

function pos(x: number, y: number): BlockPosition {
  return { x, y, regionId: "r1", regionLabel: "Costs", persisted: true };
}

describe("ThemeRegion — grouping is visible (M4)", () => {
  it("renders a labelled region bounding its members", () => {
    const { container, getByText } = render(
      <ThemeRegion region={{ regionId: "r1", label: "Costs", members: [pos(100, 100), pos(400, 300)] }} />,
    );
    const box = container.querySelector('[data-theme-region="r1"]') as HTMLElement;
    expect(box).toBeTruthy();
    expect(getByText("Costs")).toBeTruthy();
    // The box spans both members (left of the leftmost, wider than the gap).
    expect(parseFloat(box.style.left)).toBeLessThanOrEqual(100);
    expect(parseFloat(box.style.width)).toBeGreaterThan(300);
  });

  it("renders nothing for an empty region (no zero-size box)", () => {
    const { container } = render(
      <ThemeRegion region={{ regionId: "r1", label: "Empty", members: [] }} />,
    );
    expect(container.querySelector('[data-theme-region="r1"]')).toBeNull();
  });
});

describe("regionBounds — derived geometry", () => {
  it("returns null for no members and a padded box otherwise", () => {
    expect(regionBounds([])).toBeNull();
    const b = regionBounds([{ x: 100, y: 100 }, { x: 200, y: 250 }]);
    expect(b).not.toBeNull();
    expect(b!.x).toBeLessThan(100); // padded out
    expect(b!.width).toBeGreaterThan(0);
  });
});
