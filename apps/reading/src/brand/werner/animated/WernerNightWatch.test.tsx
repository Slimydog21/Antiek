import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { render } from "@testing-library/react";
import { PNG } from "pngjs";
import { describe, expect, it } from "vitest";

import WernerNightWatch from "./WernerNightWatch";

const ASSET = "../poses/werner_night_watch_v1_transparent.png";

function decode(): PNG {
  return PNG.sync.read(readFileSync(fileURLToPath(new URL(ASSET, import.meta.url))));
}

function alpha(png: PNG, x: number, y: number): number {
  return png.data[(png.width * y + x) * 4 + 3];
}

function rgba(png: PNG, x: number, y: number): [number, number, number, number] {
  const offset = (png.width * y + x) * 4;
  return [
    png.data[offset],
    png.data[offset + 1],
    png.data[offset + 2],
    png.data[offset + 3],
  ];
}

describe("WernerNightWatch (SPR-30)", () => {
  it("uses a private authored pose without creating a product mood", () => {
    const { container } = render(<WernerNightWatch size={64} />);
    expect(container.querySelector('[data-werner-night-watch="true"]')).not.toBeNull();
    expect(container.querySelector('[data-werner-authored-pose="nightWatch"]')).not.toBeNull();
    expect(container.querySelector("[data-werner-mood]")).toBeNull();
  });

  it("collapses to the same static semantic pose for reduced motion", () => {
    const { container } = render(<WernerNightWatch reduced />);
    const root = container.querySelector('[data-werner-night-watch="true"]');
    expect(root?.getAttribute("data-reduced")).toBe("true");
    expect(root?.className).toBe("");
  });

  it("ships clean RGBA edges while preserving the enclosed belly", () => {
    const png = decode();
    expect([png.width, png.height]).toEqual([1024, 1024]);
    for (let x = 0; x < png.width; x += 1) {
      expect(alpha(png, x, 0)).toBe(0);
      expect(alpha(png, x, png.height - 1)).toBe(0);
    }
    for (let y = 0; y < png.height; y += 1) {
      expect(alpha(png, 0, y)).toBe(0);
      expect(alpha(png, png.width - 1, y)).toBe(0);
    }

    let partialAlphaPixels = 0;
    let paleBoundaryPixels = 0;
    for (let y = 1; y < png.height - 1; y += 1) {
      for (let x = 1; x < png.width - 1; x += 1) {
        const [r, g, b, a] = rgba(png, x, y);
        if (a > 0 && a < 255) partialAlphaPixels += 1;
        if (a !== 255) continue;
        const touchesTransparent =
          alpha(png, x - 1, y) === 0 ||
          alpha(png, x + 1, y) === 0 ||
          alpha(png, x, y - 1) === 0 ||
          alpha(png, x, y + 1) === 0;
        const neutralAndPale =
          Math.min(r, g, b) >= 180 && Math.max(r, g, b) - Math.min(r, g, b) <= 14;
        if (touchesTransparent && neutralAndPale) paleBoundaryPixels += 1;
      }
    }
    expect(partialAlphaPixels).toBe(0);
    expect(paleBoundaryPixels).toBe(0);
    expect(alpha(png, 512, 640)).toBe(255);
  });
});
