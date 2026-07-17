/**
 * densify: instrument helpers (bait chrome + tip→bait tension) stay public on
 * the werner barrel so product shells can share the fixed-station contract.
 */
import { describe, expect, it } from "vitest";

import {
  baitChromeFromFollow,
  catenaryPath,
  rodBendFromPoints,
  tipToBaitDistance,
} from "./index";

describe("werner instrument barrel densify", () => {
  it("exports baitChromeFromFollow for cursor-is-bait chrome", () => {
    expect(
      baitChromeFromFollow({ live: { x: 5, y: 9 }, tabHidden: false }),
    ).toEqual({ display: "block", left: "5px", top: "9px" });
  });

  it("exports tip→bait geometry shared with the fishing line densify", () => {
    const rod = { x: 0, y: 0 };
    const bait = { x: 30, y: 40 };
    expect(tipToBaitDistance(rod, bait)).toBe(50);
    expect(rodBendFromPoints(rod, bait)).toBeGreaterThan(0);
    expect(catenaryPath(rod, bait).endsWith(" 30 40")).toBe(true);
  });
});
