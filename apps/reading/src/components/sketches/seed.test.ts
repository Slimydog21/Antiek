import { describe, expect, it } from "vitest";

import { coerceSeed, makeRng, rngFromSeed, seedFromString } from "./seed";

describe("sketch seed / rng", () => {
  it("seedFromString is stable + deterministic", () => {
    expect(seedFromString("artifact-abc")).toBe(seedFromString("artifact-abc"));
    expect(seedFromString("artifact-abc")).not.toBe(seedFromString("artifact-xyz"));
  });

  it("coerceSeed maps strings via FNV-1a and numbers via u32", () => {
    expect(coerceSeed("hello")).toBe(seedFromString("hello"));
    expect(coerceSeed(99)).toBe(99);
    expect(coerceSeed(-1)).toBe(0xffffffff);
    expect(coerceSeed(Number.NaN)).toBe(0);
  });

  it("mulberry32 same seed → same stream", () => {
    const a = makeRng(12345);
    const b = makeRng(12345);
    expect(Array.from({ length: 8 }, () => a.next())).toEqual(
      Array.from({ length: 8 }, () => b.next()),
    );
  });

  it("different seeds diverge", () => {
    expect(makeRng(1).next()).not.toBe(makeRng(2).next());
  });

  it("rngFromSeed accepts string seeds", () => {
    const a = rngFromSeed("constellation");
    const b = rngFromSeed("constellation");
    expect(a.range(0, 10)).toBe(b.range(0, 10));
    expect(a.int(0, 5)).toBe(b.int(0, 5));
  });
});
