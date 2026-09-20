import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import {
  DEFAULT_HEAT_TRAIL_PARAMS,
  layoutHeatTrail,
  renderHeatTrail,
} from "./heatTrail";
import { recordingContext } from "./testUtils";

describe("heatTrail layout — pure determinism", () => {
  it("same seed → identical foci", () => {
    const a = layoutHeatTrail("artifact-7", 9, 0.55);
    const b = layoutHeatTrail("artifact-7", 9, 0.55);
    expect(a).toEqual(b);
    expect(a).toHaveLength(9);
  });

  it("different seeds → different foci", () => {
    expect(layoutHeatTrail("a", 9, 0.55)).not.toEqual(
      layoutHeatTrail("b", 9, 0.55),
    );
  });

  it("focusCount clamp [3, 32]", () => {
    expect(layoutHeatTrail("x", 1)).toHaveLength(3);
    expect(layoutHeatTrail("x", 100)).toHaveLength(32);
  });

  it("positions stay in [0,1]²", () => {
    for (const f of layoutHeatTrail("bounds", 20, 1)) {
      expect(f.x).toBeGreaterThanOrEqual(0);
      expect(f.x).toBeLessThanOrEqual(1);
      expect(f.y).toBeGreaterThanOrEqual(0);
      expect(f.y).toBeLessThanOrEqual(1);
    }
  });
});

describe("heatTrail render — pixel-hash determinism", () => {
  const W = 320;
  const H = 200;

  it("same seed + size → identical call-hash", () => {
    const a = recordingContext();
    const b = recordingContext();
    const params = { ...DEFAULT_HEAT_TRAIL_PARAMS, seed: "det-heat", t: 0 };
    renderHeatTrail(a.context, W, H, params);
    renderHeatTrail(b.context, W, H, params);
    expect(a.hash()).toBe(b.hash());
    expect(a.calls.length).toBeGreaterThan(10);
  });

  it("param / seed change → different hash", () => {
    const a = recordingContext();
    const b = recordingContext();
    const c = recordingContext();
    // reducedMotion so the full trail is drawn (t=0 only reveals the head).
    const base = {
      ...DEFAULT_HEAT_TRAIL_PARAMS,
      reducedMotion: true as const,
    };
    renderHeatTrail(a.context, W, H, { ...base, seed: "alpha" });
    renderHeatTrail(b.context, W, H, { ...base, seed: "beta" });
    renderHeatTrail(c.context, W, H, {
      ...base,
      seed: "alpha",
      focusCount: 14,
    });
    expect(a.hash()).not.toBe(b.hash());
    expect(a.hash()).not.toBe(c.hash());
  });

  it("reduced-motion freezes trail (t ignored) and draws full path", () => {
    const still = recordingContext();
    const still2 = recordingContext();
    const moving = recordingContext();
    renderHeatTrail(still.context, W, H, {
      ...DEFAULT_HEAT_TRAIL_PARAMS,
      seed: "rm",
      t: 0,
      reducedMotion: true,
    });
    renderHeatTrail(still2.context, W, H, {
      ...DEFAULT_HEAT_TRAIL_PARAMS,
      seed: "rm",
      t: 80_000,
      reducedMotion: true,
    });
    renderHeatTrail(moving.context, W, H, {
      ...DEFAULT_HEAT_TRAIL_PARAMS,
      seed: "rm",
      t: 80_000,
      reducedMotion: false,
    });
    expect(still.hash()).toBe(still2.hash());
    expect(still.hash()).not.toBe(moving.hash());
  });

  it("source discipline: no Math.random / Date / rAF / p5 import", () => {
    const source = readFileSync("src/components/sketches/heatTrail.ts", "utf8");
    expect(source).not.toMatch(
      /Math\.random|Date\.now|performance\.now|requestAnimationFrame|setTimeout|setInterval/,
    );
    expect(source).not.toMatch(/from\s+["']p5(?:\.js)?["']|require\(\s*["']p5/);
  });
});
