import { describe, expect, it } from "vitest";

import {
  hitTestHotspot,
  hotspotToPixels,
  isSceneryMarginHotspot,
  SCENE_HOTSPOTS,
} from "./interactiveRegions";

describe("scene interactive regions (Flipbook-feel HTML path)", () => {
  it("scales hotspots with viewport", () => {
    const h = SCENE_HOTSPOTS[0];
    const a = hotspotToPixels(h, { width: 1000, height: 800 });
    const b = hotspotToPixels(h, { width: 500, height: 400 });
    expect(a.w).toBeCloseTo(b.w * 2);
    expect(a.h).toBeCloseTo(b.h * 2);
  });

  it("hit-tests the peak-left edge scenery region", () => {
    const vp = { width: 1000, height: 1000 };
    const peak = SCENE_HOTSPOTS.find((h) => h.id === "peak-left")!;
    const r = hotspotToPixels(peak, vp);
    const hit = hitTestHotspot(r.x + r.w / 2, r.y + r.h / 2, vp);
    expect(hit?.id).toBe("peak-left");
  });

  it("misses outside all regions", () => {
    // Center of a small viewport should not land on edge scenery strips.
    expect(hitTestHotspot(50, 50, { width: 100, height: 100 })).toBeNull();
  });

  it("every hotspot is a scenery-margin rect (does not blanket center cards)", () => {
    for (const h of SCENE_HOTSPOTS) {
      expect(
        isSceneryMarginHotspot(h),
        `${h.id} must stay on empty scenery margins`,
      ).toBe(true);
    }
  });
});
