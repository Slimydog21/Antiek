import { describe, expect, it } from "vitest";

import { isReelSettled, reelStep } from "./reelPursuit";

describe("reelPursuit", () => {
  it("settles toward target within lag budget window", () => {
    let pos = { x: 0, y: 0 };
    const target = { x: 100, y: 0 };
    let t = 0;
    // LAG_MS + REEL_TAU_MS budget (~950ms); allow one extra tau for 8px epsilon.
    while (t < 1100 && !isReelSettled(pos, target, 12)) {
      pos = reelStep(pos, target, 16);
      t += 16;
    }
    expect(isReelSettled(pos, target, 12)).toBe(true);
  });

  it("caps per-frame displacement on teleport", () => {
    const next = reelStep({ x: 0, y: 0 }, { x: 2000, y: 0 }, 16);
    expect(Math.hypot(next.x, next.y)).toBeLessThanOrEqual((480 * 16) / 1000 + 0.01);
  });

  it("moves only toward target not away on axis", () => {
    const next = reelStep({ x: 0, y: 0 }, { x: 50, y: 0 }, 16);
    expect(next.x).toBeGreaterThan(0);
    expect(next.y).toBe(0);
  });
});