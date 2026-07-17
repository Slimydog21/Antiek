import { describe, expect, it } from "vitest";

import { anchorRelativeToLayer, chooseAdjacentWindowRect } from "./adjacentWindowPlacement";

const size = { width: 720, height: 520 };

describe("chooseAdjacentWindowRect", () => {
  it("prefers a whole right-side placement", () => {
    expect(chooseAdjacentWindowRect({ left: 20, top: 40, right: 200, bottom: 90, width: 180, height: 50 }, { width: 1200, height: 800 }, size)).toEqual({ x: 216, y: 40, ...size });
  });

  it("uses left when right cannot fit", () => {
    expect(chooseAdjacentWindowRect({ left: 800, top: 700, right: 980, bottom: 750, width: 180, height: 50 }, { width: 1200, height: 800 }, size)).toEqual({ x: 64, y: 280, ...size });
  });

  it("uses below then above when horizontal sides cannot fit", () => {
    const anchor = { left: 380, top: 20, right: 820, bottom: 80, width: 440, height: 60 };
    expect(chooseAdjacentWindowRect(anchor, { width: 1000, height: 700 }, size)).toEqual({ x: 280, y: 96, ...size });
    expect(chooseAdjacentWindowRect({ ...anchor, top: 620, bottom: 680 }, { width: 1000, height: 700 }, size)).toEqual({ x: 280, y: 84, ...size });
  });

  it("returns undefined when no whole non-overlapping placement exists", () => {
    const anchor = { left: 300, top: 240, right: 500, bottom: 300, width: 200, height: 60 };
    expect(chooseAdjacentWindowRect(anchor, { width: 800, height: 600 }, size)).toBeUndefined();
    expect(chooseAdjacentWindowRect(anchor, { width: 600, height: 400 }, size)).toBeUndefined();
  });

  it("keeps the anchor immutable and honors a custom gutter", () => {
    const anchor = { left: 20, top: 40, right: 200, bottom: 90, width: 180, height: 50 };
    const snapshot = { ...anchor };
    expect(chooseAdjacentWindowRect(anchor, { width: 1200, height: 800 }, size, 24)?.x).toBe(224);
    expect(anchor).toEqual(snapshot);
  });

  it("translates a viewport anchor into a non-zero layer without mutation", () => {
    const anchor = { left: 110, top: 220, right: 190, bottom: 240, width: 80, height: 20 };
    const snapshot = { ...anchor };
    expect(anchorRelativeToLayer(anchor, { left: 10, top: 20, width: 1000, height: 700 })).toEqual({ left: 100, top: 200, right: 180, bottom: 220, width: 80, height: 20 });
    expect(anchor).toEqual(snapshot);
  });
});
