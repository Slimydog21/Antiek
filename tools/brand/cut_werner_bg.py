#!/usr/bin/env python3
"""Cut the baked white background out of a Werner pose PNG (SPR-12 M4).

The operator's Krea-generated `_corrected` penguin rasters ship with a
near-white (~255,253,253) FULLY-OPAQUE background baked into the image.
Rendered behind the top-left rail logo (a sun-yellow button) or on any
dark surface, that opaque surround reads as an ugly white box.

This script reproduces the defect (it reports the source corner pixels +
the opaque near-white count) and then fixes it.

  WHY FLOOD-FILL, NOT A GLOBAL THRESHOLD (the round-1 regression):
  the art is a WHITE-BELLIED penguin on a WHITE background. A global
  luminance+neutrality threshold cannot tell the belly's neutral
  near-white pixels apart from the background's, so it alpha-reduces the
  belly too. On the light sun-yellow rail button that ghosting is
  invisible, but the 64px mascot and 72px home hero render the idle pose
  straight onto a dark surface (`dark:bg-space-2`, RGB ~11,16,32) where a
  half-alpha belly composites to a muddy see-through grey. The M4
  criterion is explicitly "blends correctly in BOTH light AND dark," so
  the belly MUST stay opaque.

  The fix is topological, not photometric: the penguin has a CLOSED black
  outline enclosing the belly/face. We flood-fill the background inward
  from all four image edges, traversing ONLY neutral near-white pixels
  (the same neutrality guard + a luminance floor). The black outline
  STOPS the flood, so it can never reach the interior belly/face — those
  pixels are simply never visited and stay fully opaque. The sun-yellow
  bill/feet are non-neutral, so the flood never enters them either. The
  SOFT..HARD luminance ramp is applied ONLY to flood-VISITED boundary
  pixels (anti-fringe on the real edge); unvisited interior pixels are
  copied through untouched.

Deterministic: the BFS visits in a fixed (row-major seed, FIFO) order and
the per-pixel decision is a pure function of the source, so the same
input → byte-identical output. Re-run to regenerate the transparent asset
after the operator supplies a new pose.

    python3 tools/brand/cut_werner_bg.py \
        apps/reading/src/brand/werner/poses/anchor/werner_default_v5_nano_corrected.png \
        apps/reading/src/brand/werner/poses/anchor/werner_default_v5_transparent.png
"""
from __future__ import annotations

import sys
from collections import deque

from PIL import Image

# >= HARD luminance (and neutral) → fully transparent (true background).
HARD = 250
# SOFT..HARD → linear alpha ramp (anti-fringe on the flood boundary).
SOFT = 226
# Flood-fill luminance floor: only traverse pixels at least this bright.
# Below this we treat the pixel as "not background" so the dark outline
# (and any genuinely-dark art) halts the flood. Matches SOFT so the ramp
# region is exactly the band the flood is allowed to walk.
FLOOD_FLOOR = SOFT
# Max channel spread that still counts as "neutral white" (vs. the
# yellow bill/feet, which have a large spread and must stay opaque).
NEUTRAL_SPREAD = 14


def cut(src_path: str, dst_path: str) -> None:
    img = Image.open(src_path).convert("RGBA")
    w, h = img.size
    px = img.load()

    # ── Reproduce: report the pre-fix state. ──
    corners = {"TL": (0, 0), "TR": (w - 1, 0), "BL": (0, h - 1), "BR": (w - 1, h - 1)}
    print(f"source: {src_path}  size={w}x{h}")
    for name, (x, y) in corners.items():
        print(f"  before {name}: {px[x, y]}")

    def is_floodable(x: int, y: int) -> bool:
        """A pixel the background flood may traverse: neutral AND bright
        enough. The dark closed outline fails the luminance floor and so
        halts the flood before it can reach the interior belly/face."""
        r, g, b, _ = px[x, y]
        m = min(r, g, b)
        neutral = (max(r, g, b) - m) <= NEUTRAL_SPREAD
        return neutral and m >= FLOOD_FLOOR

    # ── Flood-fill the background from every edge pixel inward. ──
    # `visited` marks background-connected pixels; everything else (the
    # outline, the belly/face interior it encloses, the bill/feet) is left
    # opaque. BFS in row-major seed + FIFO order → deterministic.
    visited = bytearray(w * h)
    q: deque[tuple[int, int]] = deque()

    def seed(x: int, y: int) -> None:
        i = y * w + x
        if not visited[i] and is_floodable(x, y):
            visited[i] = 1
            q.append((x, y))

    for x in range(w):
        seed(x, 0)
        seed(x, h - 1)
    for y in range(h):
        seed(0, y)
        seed(w - 1, y)

    while q:
        x, y = q.popleft()
        if x > 0:
            seed(x - 1, y)
        if x < w - 1:
            seed(x + 1, y)
        if y > 0:
            seed(x, y - 1)
        if y < h - 1:
            seed(x, y + 1)

    # ── Composite: visited pixels get the background cut (HARD→0,
    # SOFT..HARD→ramp); unvisited pixels (incl. the interior belly) are
    # copied through unchanged so the white belly stays fully opaque. ──
    out = Image.new("RGBA", (w, h))
    opx = out.load()
    changed = 0
    for y in range(h):
        row = y * w
        for x in range(w):
            r, g, b, a = px[x, y]
            if not visited[row + x]:
                opx[x, y] = (r, g, b, a)
                continue
            m = min(r, g, b)
            if m >= HARD:
                opx[x, y] = (r, g, b, 0)
            else:  # SOFT <= m < HARD (flood only walks m >= FLOOD_FLOOR=SOFT)
                frac = (m - SOFT) / (HARD - SOFT)
                opx[x, y] = (r, g, b, int(round(a * (1.0 - frac))))
            changed += 1
    out.save(dst_path)

    vp = out.load()
    print(f"wrote:  {dst_path}  changed={changed}/{w * h}")
    for name, (x, y) in corners.items():
        print(f"  after  {name}: {vp[x, y]}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(2)
    cut(sys.argv[1], sys.argv[2])
