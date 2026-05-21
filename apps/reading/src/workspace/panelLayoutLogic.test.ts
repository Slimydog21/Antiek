import { describe, expect, it } from "vitest";

import {
  clampRectToViewport,
  defaultDockedSize,
  initialFloatingRect,
  nextZ,
  reorderArray,
  snapToDock,
  SNAP_THRESHOLD_PX,
} from "./panelLayoutLogic";

const VIEWPORT = { width: 1440, height: 900 };

describe("clampRectToViewport", () => {
  it("leaves an in-bounds rect untouched", () => {
    const rect = { x: 200, y: 200, width: 560, height: 420 };
    expect(clampRectToViewport(rect, VIEWPORT)).toEqual(rect);
  });

  it("clamps y to 0 when rect is dragged above the viewport", () => {
    const rect = { x: 200, y: -500, width: 560, height: 420 };
    const out = clampRectToViewport(rect, VIEWPORT);
    expect(out.y).toBe(0);
    expect(out.x).toBe(200);
  });

  it("keeps at least 80px visible when dragged off the right edge", () => {
    const rect = { x: 100_000, y: 200, width: 560, height: 420 };
    const out = clampRectToViewport(rect, VIEWPORT);
    // viewport.width - 80 = 1360
    expect(out.x).toBeLessThanOrEqual(VIEWPORT.width - 80);
  });

  it("keeps at least 80px visible when dragged off the left edge", () => {
    const rect = { x: -100_000, y: 200, width: 560, height: 420 };
    const out = clampRectToViewport(rect, VIEWPORT);
    // 80 - rect.width = -480
    expect(out.x).toBeGreaterThanOrEqual(80 - rect.width);
  });

  it("clamps y to leave at least 80px visible at the bottom", () => {
    const rect = { x: 200, y: 100_000, width: 560, height: 420 };
    const out = clampRectToViewport(rect, VIEWPORT);
    expect(out.y).toBeLessThanOrEqual(VIEWPORT.height - 80);
  });
});

describe("snapToDock", () => {
  it("returns null for a rect comfortably in the middle", () => {
    const rect = { x: 500, y: 500, width: 560, height: 420 };
    expect(snapToDock(rect, VIEWPORT)).toBeNull();
  });

  it("snaps to left when x is within the threshold of the left edge", () => {
    const rect = { x: SNAP_THRESHOLD_PX - 1, y: 200, width: 560, height: 420 };
    expect(snapToDock(rect, VIEWPORT)).toBe("left");
  });

  it("snaps to right when the right edge of rect overlaps the viewport edge", () => {
    const rect = {
      x: VIEWPORT.width - 560 - (SNAP_THRESHOLD_PX - 1),
      y: 200,
      width: 560,
      height: 420,
    };
    expect(snapToDock(rect, VIEWPORT)).toBe("right");
  });

  it("returns null when the rect is exactly at the threshold", () => {
    const rect = { x: SNAP_THRESHOLD_PX, y: 200, width: 560, height: 420 };
    expect(snapToDock(rect, VIEWPORT)).toBeNull();
  });
});

describe("nextZ", () => {
  it("increments the counter by 1", () => {
    expect(nextZ(0)).toBe(1);
    expect(nextZ(42)).toBe(43);
  });

  it("is pure", () => {
    const before = 5;
    nextZ(before);
    expect(before).toBe(5);
  });
});

describe("reorderArray", () => {
  it("moves an element forward", () => {
    expect(reorderArray(["a", "b", "c", "d"], 1, 3)).toEqual(["a", "c", "d", "b"]);
  });

  it("moves an element backward", () => {
    expect(reorderArray(["a", "b", "c", "d"], 3, 0)).toEqual(["d", "a", "b", "c"]);
  });

  it("returns the same array reference for from === to", () => {
    const arr = ["a", "b", "c"];
    expect(reorderArray(arr, 1, 1)).toBe(arr);
  });

  it("returns unchanged for out-of-bounds inputs", () => {
    const arr = ["a", "b", "c"];
    expect(reorderArray(arr, -1, 1)).toBe(arr);
    expect(reorderArray(arr, 1, 99)).toBe(arr);
  });

  it("does not mutate the input", () => {
    const arr = ["a", "b", "c"];
    reorderArray(arr, 0, 2);
    expect(arr).toEqual(["a", "b", "c"]);
  });
});

describe("initialFloatingRect", () => {
  it("cascades position based on z (each subsequent panel shifts ~22px)", () => {
    const r1 = initialFloatingRect(1);
    const r2 = initialFloatingRect(2);
    expect(r2.x).toBeGreaterThan(r1.x);
    expect(r2.y).toBeGreaterThan(r1.y);
  });

  it("returns the same default size", () => {
    expect(initialFloatingRect(7).width).toBe(560);
    expect(initialFloatingRect(7).height).toBe(420);
  });
});

describe("defaultDockedSize", () => {
  it("returns a 320-wide hint", () => {
    expect(defaultDockedSize().width).toBe(320);
  });
});
