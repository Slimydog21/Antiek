"""
Lock generated Werner illustrations to the exact Antiek brand yellow #F5DF24.

Krea / Nano Banana renders the bill + feet in an amber-leaning yellow that
visually drifts from the brand outline colour. This script:

  1. Reads each PNG in poses/ (+ anchor/, optional)
  2. Detects "yellow-region" pixels using HSV thresholds
  3. Remaps those pixels to the exact brand sun (#F5DF24), preserving
     the lightness/value of the original pixel so highlights and
     shaded areas keep their internal structure (the colour pivots,
     the luminance varies)
  4. Writes the result alongside the source as *_corrected.png

Usage:
    python3 color_correct.py                  # process all poses
    python3 color_correct.py --include-anchor # also process anchor/*
    python3 color_correct.py --image PATH     # process one file
"""

from __future__ import annotations

import argparse
import colorsys
from pathlib import Path

from PIL import Image


# Brand sun #F5DF24 — the one constant
BRAND_R, BRAND_G, BRAND_B = 0xF5, 0xDF, 0x24
BRAND_H, BRAND_S, BRAND_V = colorsys.rgb_to_hsv(BRAND_R / 255, BRAND_G / 255, BRAND_B / 255)


def is_yellow_region(r: int, g: int, b: int) -> bool:
    """True if (r,g,b) is within the yellow/amber band Krea tends to emit."""
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    # Yellow hue band: ~35° – ~65° (in 0..1 hue space: 0.097 – 0.181)
    # We extend slightly to catch amber/orange-leaning outputs.
    if not (0.07 <= h <= 0.20):
        return False
    # Must be reasonably saturated (not off-white)
    if s < 0.25:
        return False
    # Must be bright (not muddy brown)
    if v < 0.40:
        return False
    return True


def correct_pixel(r: int, g: int, b: int) -> tuple[int, int, int]:
    """Snap a yellow-band pixel to the brand hue, preserving its lightness."""
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    # Replace hue + saturation with brand; keep the original value (lightness)
    # so the pixel sits naturally in any internal shading or anti-alias edge.
    nr, ng, nb = colorsys.hsv_to_rgb(BRAND_H, BRAND_S, v)
    return (int(nr * 255), int(ng * 255), int(nb * 255))


def correct(image_path: Path, out_path: Path | None = None) -> Path:
    img = Image.open(image_path).convert("RGBA")
    out_path = out_path or image_path.with_name(image_path.stem + "_corrected.png")
    pixels = img.load()
    w, h = img.size
    changed = 0
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            if is_yellow_region(r, g, b):
                nr, ng, nb = correct_pixel(r, g, b)
                pixels[x, y] = (nr, ng, nb, a)
                changed += 1
    img.save(out_path)
    pct = 100 * changed / (w * h)
    print(f"  {image_path.name} → {out_path.name}  ({changed:,} px corrected, {pct:.2f}% of frame)")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-anchor", action="store_true",
                        help="Also process the anchor/ directory of intermediate iterations")
    parser.add_argument("--image", type=Path, default=None,
                        help="Process a single image file instead of the default sweep")
    args = parser.parse_args()

    root = Path(__file__).parent
    if args.image:
        correct(args.image)
        return

    poses_dir = root / "poses"
    targets: list[Path] = sorted(p for p in poses_dir.glob("werner_*_v1.png"))
    if args.include_anchor:
        anchor_dir = poses_dir / "anchor"
        targets += sorted(p for p in anchor_dir.glob("werner_*_v5_nano.png"))

    print(f"Processing {len(targets)} image(s) → target hue: H={BRAND_H:.3f} S={BRAND_S:.3f}")
    print(f"Brand sun = #F5DF24")
    for p in targets:
        correct(p)
    print("done.")


if __name__ == "__main__":
    main()
