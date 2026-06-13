/**
 * field.test.ts — SPR-04 milestone 2 acceptance: "same seed → same frame N".
 *
 * The procedural motion is only defensible if it is DETERMINISTIC: a refactor
 * that quietly introduced Math.random / Date.now would make the scene flake and
 * break snapshots. These tests pin the determinism at the pure-function level
 * (no canvas, no React): identical seed → byte-identical particle sets AND
 * byte-identical positions at an arbitrary frame N.
 */
import { describe, expect, it } from "vitest";

import { makeRng, seedFromString } from "./rng";
import {
  CLOUD_COUNT,
  SNOW_COUNT,
  STAR_COUNT,
  cloudX,
  fieldSeed,
  makeClouds,
  makeSnow,
  makeStars,
  snowAt,
} from "./field";

describe("rng — deterministic", () => {
  it("same seed yields the same stream", () => {
    const a = makeRng(12345);
    const b = makeRng(12345);
    const seqA = Array.from({ length: 8 }, () => a.next());
    const seqB = Array.from({ length: 8 }, () => b.next());
    expect(seqA).toEqual(seqB);
  });

  it("different seeds diverge", () => {
    const a = makeRng(1);
    const b = makeRng(2);
    expect(a.next()).not.toBe(b.next());
  });

  it("seedFromString is stable + deterministic", () => {
    expect(seedFromString("night|snow")).toBe(seedFromString("night|snow"));
    expect(seedFromString("day|snow")).not.toBe(seedFromString("night|snow"));
  });
});

describe("snow field — deterministic layout + frame N", () => {
  it("emits exactly SNOW_COUNT flakes", () => {
    expect(makeSnow(fieldSeed("day|snow"))).toHaveLength(SNOW_COUNT);
  });

  it("same seed → identical flake set", () => {
    const a = makeSnow(fieldSeed("day|snow"));
    const b = makeSnow(fieldSeed("day|snow"));
    expect(a).toEqual(b);
  });

  it("same seed → identical positions at frame N (t fixed)", () => {
    const seed = fieldSeed("night|snow");
    const a = makeSnow(seed);
    const b = makeSnow(seed);
    const t = 4200; // an arbitrary "frame N" timestamp in ms
    const posA = a.map((p) => snowAt(p, t, 1920, 1080, 1.4));
    const posB = b.map((p) => snowAt(p, t, 1920, 1080, 1.4));
    expect(posA).toEqual(posB);
  });

  it("flakes stay within the field bounds (wrapped)", () => {
    const flakes = makeSnow(fieldSeed("day|snow"));
    for (const t of [0, 1000, 7777, 60000]) {
      for (const f of flakes) {
        const { x, y } = snowAt(f, t, 800, 600, 1.4);
        expect(x).toBeGreaterThanOrEqual(0);
        expect(x).toBeLessThanOrEqual(800);
        expect(y).toBeGreaterThanOrEqual(0);
        expect(y).toBeLessThanOrEqual(600);
      }
    }
  });
});

describe("star field — deterministic (ALC SPR-05 M2)", () => {
  it("emits exactly STAR_COUNT stars", () => {
    expect(makeStars(fieldSeed("night|snow"))).toHaveLength(STAR_COUNT);
  });

  it("same seed → byte-identical star field (the M2 determinism gate)", () => {
    const seed = fieldSeed("night|snow");
    expect(makeStars(seed)).toEqual(makeStars(seed));
  });

  it("different scene keys diverge (dusk ≠ night star fields)", () => {
    expect(makeStars(fieldSeed("dusk|snow"))).not.toEqual(
      makeStars(fieldSeed("night|snow")),
    );
  });

  it("stars sit in the UPPER sky (y ≤ 0.66) so none land in the ground", () => {
    for (const s of makeStars(fieldSeed("night|snow"))) {
      expect(s.y).toBeGreaterThanOrEqual(0);
      expect(s.y).toBeLessThanOrEqual(0.66);
      expect(s.x).toBeGreaterThanOrEqual(0);
      expect(s.x).toBeLessThanOrEqual(1);
    }
  });
});

describe("cloud field — deterministic", () => {
  it("emits exactly CLOUD_COUNT puffs", () => {
    expect(makeClouds(fieldSeed("day|snow"))).toHaveLength(CLOUD_COUNT);
  });

  it("same seed → identical clouds + identical x at frame N", () => {
    const seed = fieldSeed("day|snow");
    const a = makeClouds(seed);
    const b = makeClouds(seed);
    expect(a).toEqual(b);
    const t = 9000;
    expect(a.map((c) => cloudX(c, t, 1600))).toEqual(
      b.map((c) => cloudX(c, t, 1600)),
    );
  });
});
