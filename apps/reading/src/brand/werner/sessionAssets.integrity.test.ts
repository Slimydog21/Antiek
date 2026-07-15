/**
 * Session brand PNG integrity — no baked white/gray box on product paths.
 *
 * Cabinet key-art (ice fishing, zombies) and mood poses (thinking, celebrate)
 * must have fully transparent corners so they composite over glass/dark chrome
 * without an opaque plate. Opaque provenance files remain on disk for redo.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { PNG } from "pngjs";
import { describe, expect, it } from "vitest";

function decode(relUrl: string): PNG {
  const path = fileURLToPath(new URL(relUrl, import.meta.url));
  return PNG.sync.read(readFileSync(path));
}

function pixel(
  png: PNG,
  x: number,
  y: number,
): [number, number, number, number] {
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

function opaqueSampleCount(png: PNG, step = 8): number {
  let n = 0;
  for (let y = 0; y < png.height; y += step) {
    for (let x = 0; x < png.width; x += step) {
      if (pixel(png, x, y)[3] > 200) n += 1;
    }
  }
  return n;
}

/** Product paths actually imported by sessionAssets / ArcadeCabinet / Werner. */
const PRODUCT_SESSION_PNGS = [
  "./poses/session/werner_thinking_session_v1.png",
  "./poses/session/werner_celebrate_session_v1.png",
  "./poses/session/werner_ice_fishing_session_v1.png",
  "./poses/session/werner_zombies_session_v1.png",
] as const;

describe("session brand PNG alpha integrity", () => {
  it.each(PRODUCT_SESSION_PNGS)(
    "%s has alpha=0 at all four canvas corners",
    (rel) => {
      const png = decode(rel);
      for (const [, , , a] of corners(png)) {
        expect(a, `${rel} corner must be fully transparent`).toBe(0);
      }
    },
  );

  it.each(PRODUCT_SESSION_PNGS)(
    "%s keeps a substantial opaque body (not erased)",
    (rel) => {
      const png = decode(rel);
      expect(
        opaqueSampleCount(png),
        `${rel} must retain opaque mark pixels`,
      ).toBeGreaterThan(200);
    },
  );

  it("opaque provenance still proves the ice-fishing/zombies fringe defect", () => {
    // Before the residual-fringe flood, TR (and sometimes BL) corners were
    // fully opaque light-gray — the integrity gap this wave closed.
    const ice = decode(
      "./poses/session/werner_ice_fishing_session_v1_opaque_provenance.png",
    );
    const zombies = decode(
      "./poses/session/werner_zombies_session_v1_opaque_provenance.png",
    );
    const iceCorners = corners(ice).map((c) => c[3]);
    const zombieCorners = corners(zombies).map((c) => c[3]);
    expect(
      iceCorners.some((a) => a === 255),
      "ice fishing provenance must retain at least one opaque corner",
    ).toBe(true);
    expect(
      zombieCorners.some((a) => a === 255),
      "zombies provenance must retain at least one opaque corner",
    ).toBe(true);
  });

  it("curious v2 candidate is alpha-honest (staged, not yet product-mapped)", () => {
    const curious = decode(
      "./poses/session/werner_curious_session_v2_candidate.png",
    );
    for (const [, , , a] of corners(curious)) {
      expect(a).toBe(0);
    }
    expect(opaqueSampleCount(curious)).toBeGreaterThan(100);
  });
});
