/**
 * WernerLogoTransparency.test.ts — SPR-12 M4 deterministic proof.
 *
 * The lostpixel visual gate (Storybook build + chromium screenshot diff of
 * the top-left logo in light + dark) is the spec's stated check for "no
 * white box." That gate needs a headless-chromium build-storybook run,
 * which is not reliably available in this sandbox. This test is the
 * deterministic SUBSTITUTE: it decodes the actual PNG bytes off disk and
 * asserts the defect-and-fix at the pixel level, which is the real
 * load-bearing fact (the white box was baked into the raster, not styling).
 *
 *   BEFORE (the source `_corrected` pose): the four corners are FULLY
 *   OPAQUE near-white — i.e. the white box is baked in.
 *
 *   AFTER (the alpha-cut transparent variant that Werner now renders for
 *   the idle/logo pose): the four corners are alpha == 0 (transparent), so
 *   the mark blends into both the sun-yellow rail button (light) and dark
 *   surfaces (dark) — there is no opaque white surround in EITHER theme.
 *
 * Transparency is theme-independent (alpha 0 composites onto whatever is
 * behind it), so a single alpha assertion covers both light and dark.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { PNG } from "pngjs";
import { describe, expect, it } from "vitest";

function decode(relUrl: string): PNG {
  const path = fileURLToPath(new URL(relUrl, import.meta.url));
  return PNG.sync.read(readFileSync(path));
}

/** [r,g,b,a] of one pixel. */
function pixel(png: PNG, x: number, y: number): [number, number, number, number] {
  const i = (png.width * y + x) << 2;
  return [png.data[i], png.data[i + 1], png.data[i + 2], png.data[i + 3]];
}

function corners(png: PNG): Array<[number, number, number, number]> {
  const { width: w, height: h } = png;
  return [
    pixel(png, 0, 0),
    pixel(png, w - 1, 0),
    pixel(png, 0, h - 1),
    pixel(png, w - 1, h - 1),
  ];
}

const SRC = "./werner/poses/anchor/werner_default_v5_nano_corrected.png";
const FIXED = "./werner/poses/anchor/werner_default_v5_transparent.png";

describe("Werner logo white-background fix (SPR-12 M4)", () => {
  it("reproduces the defect: the source pose has opaque near-white corners (the baked white box)", () => {
    const src = decode(SRC);
    for (const [r, g, b, a] of corners(src)) {
      expect(a, "source corner must be fully opaque (white box baked in)").toBe(255);
      expect(Math.min(r, g, b), "source corner must be near-white").toBeGreaterThan(240);
    }
  });

  it("fixes it: the transparent variant has alpha=0 corners (no white box, light OR dark)", () => {
    const fixed = decode(FIXED);
    for (const [, , , a] of corners(fixed)) {
      expect(a, "fixed corner must be fully transparent").toBe(0);
    }
  });

  it("keeps the penguin: the transparent variant still has opaque body pixels (we didn't erase the mark)", () => {
    const fixed = decode(FIXED);
    let opaque = 0;
    let sunYellow = 0;
    for (let y = 0; y < fixed.height; y += 8) {
      for (let x = 0; x < fixed.width; x += 8) {
        const [r, g, b, a] = pixel(fixed, x, y);
        if (a > 200) opaque += 1;
        // The sun-yellow bill/feet (#F5DF24-ish) must survive the cut —
        // they are NOT neutral white, so the neutrality guard spares them.
        if (a > 200 && r > 200 && g > 170 && b < 120) sunYellow += 1;
      }
    }
    expect(opaque, "the penguin body must remain opaque").toBeGreaterThan(500);
    expect(sunYellow, "the sun-yellow bill/feet must be preserved").toBeGreaterThan(20);
  });

  it("keeps the BELLY: the white-bellied interior stays OPAQUE (the dark-bg ghosting regression)", () => {
    // The round-1 global-threshold cut ghosted the penguin's white belly:
    // its neutral near-white pixels were alpha-reduced just like the
    // background, so on `dark:bg-space-2` (RGB ~11,16,32) the belly
    // composited to a muddy see-through grey (measured mean interior alpha
    // ~137/255). The corner-alpha + opaque-count + sun-yellow assertions
    // all PASS even with that ghost (the black outline / bill / feet
    // survive), so they do not catch it. This is the assertion that does:
    // the flood-fill from the edges stops at the closed black outline and
    // never reaches the belly, so the center box must read fully opaque.
    //
    // Pre-fix (ghosted) mean center alpha ≈ 137 → FAILS this.
    // Post-fix (flood-filled)              ≈ 255 → PASSES this.
    const fixed = decode(FIXED);
    const { width: w, height: h } = fixed;
    let sum = 0;
    let n = 0;
    for (let y = Math.floor(h * 0.35); y < Math.floor(h * 0.65); y += 4) {
      for (let x = Math.floor(w * 0.35); x < Math.floor(w * 0.65); x += 4) {
        sum += pixel(fixed, x, y)[3];
        n += 1;
      }
    }
    const meanAlpha = sum / n;
    expect(
      meanAlpha,
      "the white belly/face center must stay opaque (it must NOT ghost on a dark surface)",
    ).toBeGreaterThan(230);
  });
});
