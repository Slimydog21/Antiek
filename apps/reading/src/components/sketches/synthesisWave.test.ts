import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import {
  DEFAULT_SYNTHESIS_WAVE_PARAMS,
  layoutSynthesisWave,
  renderSynthesisWave,
  sampleWave,
} from "./synthesisWave";
import { recordingContext } from "./testUtils";

describe("synthesisWave layout — pure determinism", () => {
  it("same seed → identical harmonics", () => {
    const a = layoutSynthesisWave("artifact-wave", 5);
    const b = layoutSynthesisWave("artifact-wave", 5);
    expect(a).toEqual(b);
    expect(a).toHaveLength(5);
  });

  it("different seeds → different harmonics", () => {
    expect(layoutSynthesisWave("a", 5)).not.toEqual(layoutSynthesisWave("b", 5));
  });

  it("harmonics clamp [2, 12]", () => {
    expect(layoutSynthesisWave("x", 1)).toHaveLength(2);
    expect(layoutSynthesisWave("x", 99)).toHaveLength(12);
  });

  it("sampleWave is deterministic and bounded", () => {
    const hs = layoutSynthesisWave("s", 4);
    const y0 = sampleWave(hs, 0.3, 0);
    const y1 = sampleWave(hs, 0.3, 0);
    expect(y0).toBe(y1);
    expect(y0).toBeGreaterThanOrEqual(-1.0001);
    expect(y0).toBeLessThanOrEqual(1.0001);
  });
});

describe("synthesisWave render — pixel-hash determinism", () => {
  const W = 320;
  const H = 200;

  it("same seed + size → identical call-hash", () => {
    const a = recordingContext();
    const b = recordingContext();
    const params = {
      ...DEFAULT_SYNTHESIS_WAVE_PARAMS,
      seed: "det-wave",
      t: 0,
    };
    renderSynthesisWave(a.context, W, H, params);
    renderSynthesisWave(b.context, W, H, params);
    expect(a.hash()).toBe(b.hash());
    expect(a.calls.length).toBeGreaterThan(10);
  });

  it("param / seed change → different hash", () => {
    const a = recordingContext();
    const b = recordingContext();
    const c = recordingContext();
    renderSynthesisWave(a.context, W, H, {
      ...DEFAULT_SYNTHESIS_WAVE_PARAMS,
      seed: "alpha",
    });
    renderSynthesisWave(b.context, W, H, {
      ...DEFAULT_SYNTHESIS_WAVE_PARAMS,
      seed: "beta",
    });
    renderSynthesisWave(c.context, W, H, {
      ...DEFAULT_SYNTHESIS_WAVE_PARAMS,
      seed: "alpha",
      harmonics: 8,
    });
    expect(a.hash()).not.toBe(b.hash());
    expect(a.hash()).not.toBe(c.hash());
  });

  it("reduced-motion freezes phase (t ignored)", () => {
    const still = recordingContext();
    const still2 = recordingContext();
    const moving = recordingContext();
    renderSynthesisWave(still.context, W, H, {
      ...DEFAULT_SYNTHESIS_WAVE_PARAMS,
      seed: "rm",
      t: 0,
      reducedMotion: true,
    });
    renderSynthesisWave(still2.context, W, H, {
      ...DEFAULT_SYNTHESIS_WAVE_PARAMS,
      seed: "rm",
      t: 90_000,
      reducedMotion: true,
    });
    renderSynthesisWave(moving.context, W, H, {
      ...DEFAULT_SYNTHESIS_WAVE_PARAMS,
      seed: "rm",
      t: 90_000,
      reducedMotion: false,
    });
    expect(still.hash()).toBe(still2.hash());
    expect(still.hash()).not.toBe(moving.hash());
  });

  it("source discipline: no Math.random / Date / rAF / p5 import", () => {
    const source = readFileSync(
      "src/components/sketches/synthesisWave.ts",
      "utf8",
    );
    expect(source).not.toMatch(
      /Math\.random|Date\.now|performance\.now|requestAnimationFrame|setTimeout|setInterval/,
    );
    expect(source).not.toMatch(/from\s+["']p5(?:\.js)?["']|require\(\s*["']p5/);
  });
});
