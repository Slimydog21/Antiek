import { describe, expect, it } from "vitest";

import { catenaryPath } from "./fishingLineGeometry";

describe("catenaryPath", () => {
  it("sags on a long span", () => {
    const d = catenaryPath({ x: 0, y: 0 }, { x: 200, y: 0 });
    expect(d).toMatch(/^M 0 0 Q 100 [\d.]+ 200 0$/);
    const match = d.match(/Q 100 ([\d.]+) 200/);
    expect(Number(match![1])).toBeGreaterThan(0);
  });

  it("degenerates to a straight segment when span < 8px", () => {
    expect(catenaryPath({ x: 0, y: 0 }, { x: 4, y: 0 })).toBe("M 0 0 L 4 0");
  });

  it("never produces NaN coordinates", () => {
    const d = catenaryPath({ x: 10, y: 10 }, { x: 10, y: 10 });
    expect(d).not.toContain("NaN");
  });
});