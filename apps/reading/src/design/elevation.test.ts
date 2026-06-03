import { describe, expect, it } from "vitest";

import {
  CASCADE_PANEL_STEP_PX,
  CASCADE_PANEL_WRAP_PX,
  CASCADE_WINDOW_STEP_PX,
  CASCADE_WINDOW_WRAP_PX,
  cascadeOffset,
  ELEVATION_EXEMPT_SURFACES,
  shadowForStackDepth,
} from "./elevation";

describe("elevation — shadowForStackDepth", () => {
  it("opaque-chunky depth 0 differs from depth 3", () => {
    expect(shadowForStackDepth(0, "opaque-chunky")).not.toBe(
      shadowForStackDepth(3, "opaque-chunky"),
    );
  });

  it("maps each depth tier to the expected z-shadow class string", () => {
    expect(shadowForStackDepth(0, "opaque-chunky")).toBe(
      "shadow-z1 dark:shadow-z1-night",
    );
    expect(shadowForStackDepth(1, "opaque-chunky")).toBe(
      "shadow-z2 dark:shadow-z2-night",
    );
    expect(shadowForStackDepth(2, "opaque-chunky")).toBe(
      "shadow-z3 dark:shadow-z3-night",
    );
    expect(shadowForStackDepth(3, "opaque-chunky")).toBe(
      "shadow-z3 dark:shadow-z3-night",
    );
  });

  it("clamps negative and oversized depth", () => {
    expect(shadowForStackDepth(-2, "opaque-chunky")).toBe(
      shadowForStackDepth(0, "opaque-chunky"),
    );
    expect(shadowForStackDepth(99, "opaque-chunky")).toBe(
      shadowForStackDepth(3, "opaque-chunky"),
    );
  });

  it("glass-scene returns minimal title-bar shadow only (no depth scaling)", () => {
    const shallow = shadowForStackDepth(0, "glass-scene");
    const deep = shadowForStackDepth(3, "glass-scene");
    expect(shallow).toBe("shadow-z1 dark:shadow-z1-night");
    expect(deep).toBe(shallow);
  });
});

describe("elevation — exemptions", () => {
  it("lists ResearchWorkstation IDE among exempt surfaces", () => {
    expect(ELEVATION_EXEMPT_SURFACES.some((s) => /ResearchWorkstation/i.test(s))).toBe(
      true,
    );
    expect(ELEVATION_EXEMPT_SURFACES.length).toBeGreaterThanOrEqual(3);
  });
});

describe("elevation — cascadeOffset", () => {
  it("windows store matches windowsStore cascadeRect step and wrap", () => {
    expect(cascadeOffset(0, "windows")).toEqual({ x: 0, y: 0 });
    expect(cascadeOffset(1, "windows")).toEqual({
      x: CASCADE_WINDOW_STEP_PX,
      y: CASCADE_WINDOW_STEP_PX,
    });
    expect(cascadeOffset(8, "windows")).toEqual({ x: 0, y: 0 });
    expect(CASCADE_WINDOW_WRAP_PX).toBe(CASCADE_WINDOW_STEP_PX * 8);
  });

  it("panels store matches initialFloatingRect jitter", () => {
    expect(cascadeOffset(0, "panels")).toEqual({ x: 0, y: 0 });
    expect(cascadeOffset(1, "panels")).toEqual({
      x: CASCADE_PANEL_STEP_PX,
      y: CASCADE_PANEL_STEP_PX,
    });
    expect(cascadeOffset(9, "panels").x).toBe(
      (9 * CASCADE_PANEL_STEP_PX) % CASCADE_PANEL_WRAP_PX,
    );
  });
});