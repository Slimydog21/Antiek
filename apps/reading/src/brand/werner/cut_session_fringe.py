#!/usr/bin/env python3
"""Cut residual opaque light-gray fringe from session cabinet PNGs.

Studio poses use cut_pose_bg.py (near-white flood). Session cabinet arts
(ice fishing, paperclip zombies) often arrive with a mostly-cut checkerboard
surround PLUS residual light-gray opaque fringe at canvas corners that fails
alpha integrity. This script floods from the edges through:

  - already-transparent pixels (bridge)
  - neutral light pixels (luminance >= LUM_MIN, channel spread <= SPREAD)

and sets those background pixels to alpha 0. Dark outline and saturated
bill/rod colors halt the flood so character interiors stay opaque.

Usage:
    python3 cut_session_fringe.py --image poses/session/foo_opaque_provenance.png \\
        --out poses/session/foo.png
"""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

from PIL import Image

LUM_MIN = 210
SPREAD = 22


def is_bg_rgb(r: int, g: int, b: int) -> bool:
    if max(r, g, b) - min(r, g, b) > SPREAD:
        return False
    return (0.299 * r + 0.587 * g + 0.114 * b) >= LUM_MIN


def cut_session(src: Path, dst: Path) -> None:
    img = Image.open(src).convert("RGBA")
    px = img.load()
    w, h = img.size
    bg = bytearray(w * h)
    q: deque[tuple[int, int]] = deque()

    def seed(x: int, y: int) -> None:
        i = y * w + x
        if bg[i]:
            return
        r, g, b, a = px[x, y]
        if a == 0 or is_bg_rgb(r, g, b):
            bg[i] = 1
            q.append((x, y))

    for x in range(w):
        seed(x, 0)
        seed(x, h - 1)
    for y in range(h):
        seed(0, y)
        seed(w - 1, y)

    while q:
        x, y = q.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h:
                seed(nx, ny)

    cut = 0
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if bg[i]:
                r, g, b, a = px[x, y]
                if a != 0:
                    cut += 1
                px[x, y] = (r, g, b, 0)

    img.save(dst)
    print(f"  {src.name} → {dst.name}  (extra_cut={cut:,} px to alpha-0)")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--image", type=Path, required=True)
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()
    out = args.out or args.image.with_name(
        args.image.stem.replace("_opaque_provenance", "") + ".png"
    )
    cut_session(args.image, out)


if __name__ == "__main__":
    main()
