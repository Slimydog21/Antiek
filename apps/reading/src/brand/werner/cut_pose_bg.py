"""
Cut the baked near-white BACKGROUND out of the Werner emote poses (SPR-06 M2).

THE WHITE-BOX CRUX (anchor[penguin], v1 complaint #5)
-----------------------------------------------------
The emote poses in poses/*_v1_corrected.png were rendered by Krea/Nano on a
near-white (#FBFCFD / #FFFFFF-class, ≈(253,254,253,255)) OPAQUE backdrop. That
backdrop is BAKED INTO the raster — it is NOT a CSS class (a grep of emotes.tsx
is clean). So when an emote plays over the dark mascot surface (or the sun rail)
the corner pixels paint an ugly opaque WHITE BOX behind the penguin. We do NOT
redraw the art (honesty, rigor #1); we only remove the backdrop.

WHY FLOOD-FILL, NOT A GLOBAL LUMINANCE THRESHOLD (the load-bearing choice)
--------------------------------------------------------------------------
Werner's BELLY and FACE are themselves near-white. A global "make every
near-white pixel transparent" pass would punch holes through his belly and
leave a ghost penguin. The background, by contrast, is the connected region of
neutral near-white reachable from the image EDGES — and it is SEPARATED from the
white belly by Werner's closed black/ink OUTLINE. So we FLOOD-FILL inward from
the four edges, traversing only neutral near-white pixels, and HALT at the first
non-near-white (the outline). Only the true surround is reached → only it goes
alpha-0. The belly/face, never reached by the flood, stay FULLY OPAQUE. This is
the exact topological cut the anchor transparent variant
(poses/anchor/werner_default_v5_transparent.png, produced by the same family of
script) already uses; this mirrors it for the emote poses.

EDGES (anti-aliasing): a neutral backdrop pixel adjacent to the kept subject is
cut completely. Retaining the source RGB under partial alpha produces a pale
matte when composited on Antiek's night surfaces; the authored dark outline is
the subject-side anti-aliasing boundary.

Usage:
    python3 cut_pose_bg.py                 # cut every poses/*_v1_corrected.png
    python3 cut_pose_bg.py --image PATH    # cut one file → <stem>_transparent.png
    python3 cut_pose_bg.py --image PATH --near-white-min 180 --hard-cut

Output: poses/<name>_transparent.png (e.g. werner_thinking_v1_transparent.png).
The source PNG is kept on disk for provenance (we never overwrite it).
"""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

from PIL import Image

# A pixel is "near-white background candidate" if every channel is high and the
# channel spread is small (NEUTRAL — not a saturated yellow bill / blue accent,
# which can also be bright). The Krea backdrop sits ≈(253,254,253); the brand
# sun bill is saturated and so is NOT neutral, so it is never eaten.
# ChatGPT Image checker tiles can dip below this default. Those sources opt in
# to a lower floor; topology, not brightness alone, protects the enclosed
# warm-white interior.
NEAR_WHITE_MIN = 226   # ordinary near-white matte floor …
NEUTRAL_SPREAD = 14    # … and (max-min) channel spread <= this


def is_neutral_near_white(
    r: int, g: int, b: int, min_channel: int = NEAR_WHITE_MIN
) -> bool:
    """True if (r,g,b) is a neutral near-white background candidate."""
    if r < min_channel or g < min_channel or b < min_channel:
        return False
    return (max(r, g, b) - min(r, g, b)) <= NEUTRAL_SPREAD


def cut(
    image_path: Path,
    out_path: Path | None = None,
    *,
    min_channel: int = NEAR_WHITE_MIN,
    hard_cut: bool = False,
) -> Path:
    img = Image.open(image_path).convert("RGBA")
    out_path = out_path or image_path.with_name(
        image_path.stem.replace("_corrected", "") + "_transparent.png"
    )
    px = img.load()
    w, h = img.size

    # ── Flood-fill the background from the four edges (4-connectivity) ──
    # `bg[y*w+x]` is True once a pixel is proven to belong to the connected
    # near-white surround reachable from an edge. The flood traverses ONLY
    # neutral near-white pixels and is halted by the penguin's outline, so it
    # can never leak through the body into the belly.
    bg = bytearray(w * h)
    q: deque[tuple[int, int]] = deque()

    def seed(x: int, y: int) -> None:
        i = y * w + x
        if bg[i]:
            return
        r, g, b, _a = px[x, y]
        if is_neutral_near_white(r, g, b, min_channel):
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

    # ── Apply the cut ──
    # Background pixels become alpha 0. Interior pixels (belly/face/outline)
    # are unreachable through the closed outline and remain untouched.
    cut_count = 0
    feather_count = 0
    for y in range(h):
        for x in range(w):
            i = y * w + x
            if bg[i]:
                r, g, b, _a = px[x, y]
                px[x, y] = (r, g, b, 0)
                cut_count += 1
                continue
            if hard_cut:
                continue
            r, g, b, a = px[x, y]
            if a == 0 or not is_neutral_near_white(r, g, b, min_channel):
                continue
            touches_bg = any(
                0 <= nx < w and 0 <= ny < h and bg[ny * w + nx]
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
            )
            if touches_bg:
                whiteness = (min(r, g, b) - min_channel) / (255 - min_channel)
                whiteness = max(0.0, min(1.0, whiteness))
                px[x, y] = (r, g, b, int(round(a * (1.0 - whiteness))))
                feather_count += 1
    img.save(out_path)
    total = w * h
    print(
        f"  {image_path.name} → {out_path.name}  "
        f"({cut_count:,} px cut to alpha-0 = {100 * cut_count / total:.1f}%, "
        f"{feather_count:,} edge px feathered)"
    )
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--image", type=Path, default=None,
        help="Cut one file instead of the default poses/ sweep.",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Write the single-image result to this path.",
    )
    parser.add_argument(
        "--near-white-min", type=int, default=NEAR_WHITE_MIN,
        help="Minimum neutral channel value; lower only for checkerboard sources.",
    )
    parser.add_argument(
        "--hard-cut", action="store_true",
        help="Do not retain a partially transparent neutral matte at the boundary.",
    )
    args = parser.parse_args()

    if args.image:
        cut(
            args.image,
            args.output,
            min_channel=args.near_white_min,
            hard_cut=args.hard_cut,
        )
        return

    poses_dir = Path(__file__).parent / "poses"
    targets = sorted(poses_dir.glob("werner_*_v1_corrected.png"))
    print(f"Cutting backdrop from {len(targets)} emote pose(s)…")
    for p in targets:
        cut(p)
    print("done.")


if __name__ == "__main__":
    main()
