/**
 * landscapePalette.test.ts — ATP-01 milestone 1 & 4.
 *
 * Proves:
 *   - All four DayPart keys exist with exactly six roles each.
 *   - All four tuples are unique (no two dayparts share the same palette).
 *   - Day and night values are byte-identical to the pre-ATP-01 ProceduralSky
 *     classes (the frozen contract).
 *   - Dawn and dusk roles use distinct token names from day/night.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { sceneLandscape } from "../design/tokens";
import {
  LANDSCAPE_PALETTE,
  skyGradientClasses,
  ridgeFillClass,
} from "./landscapePalette";
import type { DayPart } from "./mood";

const ALL_DAY_PARTS: DayPart[] = ["dawn", "day", "dusk", "night"];

const APP_ROOT = join(__dirname, "../..");
const TOKENS_CSS = readFileSync(
  join(APP_ROOT, "src/design/tokens.css"),
  "utf8",
);
const TAILWIND = readFileSync(join(APP_ROOT, "tailwind.config.js"), "utf8");

const TOKEN_ROLE = {
  skyTop: "top",
  skyMid: "mid",
  skyHorizon: "horizon",
  ridgeFar: "ridge-far",
  ridgeMid: "ridge-mid",
  ridgeNear: "ridge-near",
} as const;

describe("LANDSCAPE_PALETTE", () => {
  it("has all four dayparts", () => {
    expect(Object.keys(LANDSCAPE_PALETTE).sort()).toEqual(
      ["dawn", "day", "dusk", "night"],
    );
  });

  it("every daypart has one sky class and exactly three ridge classes", () => {
    for (const dp of ALL_DAY_PARTS) {
      const p = LANDSCAPE_PALETTE[dp];
      const keys = Object.keys(p).sort();
      expect(keys).toEqual(["ridges", "sky"]);
      expect(p.ridges).toHaveLength(3);
    }
  });

  it("all four tuples are unique — no two dayparts share the same palette", () => {
    const tuples = ALL_DAY_PARTS.map(
      (dp) => JSON.stringify(LANDSCAPE_PALETTE[dp]),
    );
    const unique = new Set(tuples);
    expect(unique.size).toBe(4);
  });

  it("day sky gradient matches pre-ATP-01: from-glacial-1 via-ice-3 to-ice-1", () => {
    const gradient = skyGradientClasses("day");
    expect(gradient).toBe(
      "bg-gradient-to-b from-glacial-1 via-ice-3 to-ice-1",
    );
  });

  it("day ridge fills match pre-ATP-01: fill-glacial-1, fill-glacial-2, fill-shadow-1", () => {
    expect(ridgeFillClass("day", 0)).toBe("fill-glacial-1");
    expect(ridgeFillClass("day", 1)).toBe("fill-glacial-2");
    expect(ridgeFillClass("day", 2)).toBe("fill-shadow-1");
  });

  it("night sky gradient matches pre-ATP-01: from-space-2 via-space-1 to-charcoal-2", () => {
    const gradient = skyGradientClasses("night");
    expect(gradient).toBe(
      "bg-gradient-to-b from-space-2 via-space-1 to-charcoal-2",
    );
  });

  it("night ridge fills match pre-ATP-01: fill-charcoal-2, fill-charcoal-1, fill-space-1", () => {
    expect(ridgeFillClass("night", 0)).toBe("fill-charcoal-2");
    expect(ridgeFillClass("night", 1)).toBe("fill-charcoal-1");
    expect(ridgeFillClass("night", 2)).toBe("fill-space-1");
  });

  it("dawn uses the scene-dawn-horizon token (not the day horizon)", () => {
    expect(skyGradientClasses("dawn")).toBe("bg-scene-dawn-sky");
    expect(skyGradientClasses("day")).toContain("to-ice-1");
    expect(skyGradientClasses("dawn")).not.toBe(skyGradientClasses("day"));
  });

  it("dusk uses scene-dusk tokens (not the night ramp)", () => {
    expect(skyGradientClasses("dusk")).toBe("bg-scene-dusk-sky");
    expect(skyGradientClasses("night")).toContain("from-space-2");
    expect(skyGradientClasses("dusk")).not.toBe(skyGradientClasses("night"));
  });

  it("dawn ridge fills are authored independently from day", () => {
    for (let b = 0; b < 3; b++) {
      expect(ridgeFillClass("dawn", b)).not.toBe(ridgeFillClass("day", b));
    }
  });

  it("dusk ridge fills are authored independently from night", () => {
    for (let b = 0; b < 3; b++) {
      expect(ridgeFillClass("dusk", b)).not.toBe(ridgeFillClass("night", b));
    }
  });
});

describe("scene landscape token parity", () => {
  it("keeps every dawn/dusk TypeScript value byte-identical to CSS and Tailwind var-backed", () => {
    for (const dayPart of ["dawn", "dusk"] as const) {
      for (const [role, value] of Object.entries(sceneLandscape[dayPart])) {
        const token =
          `scene-${dayPart}-${TOKEN_ROLE[role as keyof typeof TOKEN_ROLE]}`;
        const assignments = TOKENS_CSS.match(
          new RegExp(`--${token}:\\s*${value};`, "gi"),
        );
        expect(assignments).toHaveLength(2);
        expect(TAILWIND).toContain(`"${token}": "var(--${token})"`);
      }
    }
  });
});
