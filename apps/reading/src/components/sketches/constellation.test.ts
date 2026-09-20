import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import {
  DEFAULT_CONSTELLATION_PARAMS,
  layoutConstellation,
  renderConstellation,
} from "./constellation";
import { recordingContext } from "./testUtils";

describe("constellation layout — pure determinism", () => {
  it("same seed → identical layout", () => {
    const a = layoutConstellation("artifact-42", 18, 0.28);
    const b = layoutConstellation("artifact-42", 18, 0.28);
    expect(a).toEqual(b);
    expect(a.nodes.length).toBe(18);
    expect(a.edges.length).toBeGreaterThan(0);
  });

  it("different seeds → different layouts", () => {
    const a = layoutConstellation("seed-a", 18, 0.28);
    const b = layoutConstellation("seed-b", 18, 0.28);
    expect(a).not.toEqual(b);
  });

  it("nodeCount clamp [4, 64]", () => {
    expect(layoutConstellation("x", 2).nodes).toHaveLength(4);
    expect(layoutConstellation("x", 200).nodes).toHaveLength(64);
  });

  it("positions stay in [0,1]²", () => {
    const { nodes } = layoutConstellation("bounds-check", 32, 0.5);
    for (const n of nodes) {
      expect(n.x).toBeGreaterThanOrEqual(0);
      expect(n.x).toBeLessThanOrEqual(1);
      expect(n.y).toBeGreaterThanOrEqual(0);
      expect(n.y).toBeLessThanOrEqual(1);
    }
  });
});

describe("constellation render — pixel-hash determinism", () => {
  const W = 320;
  const H = 200;

  it("same seed + size → identical call-hash", () => {
    const a = recordingContext();
    const b = recordingContext();
    const params = { ...DEFAULT_CONSTELLATION_PARAMS, seed: "det-1", t: 0 };
    renderConstellation(a.context, W, H, params);
    renderConstellation(b.context, W, H, params);
    // Compare serialised call-hashes (vi.fn instances differ across contexts).
    expect(a.hash()).toBe(b.hash());
    expect(a.calls.map((c) => c[0])).toEqual(b.calls.map((c) => c[0]));
    expect(a.calls.length).toBeGreaterThan(10);
  });

  it("param / seed change → different hash", () => {
    const a = recordingContext();
    const b = recordingContext();
    const c = recordingContext();
    renderConstellation(a.context, W, H, {
      ...DEFAULT_CONSTELLATION_PARAMS,
      seed: "alpha",
    });
    renderConstellation(b.context, W, H, {
      ...DEFAULT_CONSTELLATION_PARAMS,
      seed: "beta",
    });
    renderConstellation(c.context, W, H, {
      ...DEFAULT_CONSTELLATION_PARAMS,
      seed: "alpha",
      nodeCount: 24,
    });
    expect(a.hash()).not.toBe(b.hash());
    expect(a.hash()).not.toBe(c.hash());
  });

  it("reduced-motion freezes phase (t ignored)", () => {
    const still = recordingContext();
    const still2 = recordingContext();
    const moving = recordingContext();
    renderConstellation(still.context, W, H, {
      ...DEFAULT_CONSTELLATION_PARAMS,
      seed: "rm",
      t: 0,
      reducedMotion: true,
    });
    renderConstellation(still2.context, W, H, {
      ...DEFAULT_CONSTELLATION_PARAMS,
      seed: "rm",
      t: 50_000,
      reducedMotion: true,
    });
    renderConstellation(moving.context, W, H, {
      ...DEFAULT_CONSTELLATION_PARAMS,
      seed: "rm",
      t: 50_000,
      reducedMotion: false,
    });
    expect(still.hash()).toBe(still2.hash());
    expect(still.hash()).not.toBe(moving.hash());
  });

  it("does not import Math.random / Date / rAF (source discipline)", () => {
    const source = readFileSync(
      "src/components/sketches/constellation.ts",
      "utf8",
    );
    expect(source).not.toMatch(
      /Math\.random|Date\.now|performance\.now|requestAnimationFrame|setTimeout|setInterval/,
    );
    // No p5.js dependency — ban imports/requires, not documentary comments.
    expect(source).not.toMatch(/from\s+["']p5(?:\.js)?["']|require\(\s*["']p5/);
  });
});
