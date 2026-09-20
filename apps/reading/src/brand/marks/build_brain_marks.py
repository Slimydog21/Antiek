"""
Derive favicon + apple-touch-icon + avatar + social card from the brain hero.

Inputs:
  ../mascot-brain/01_hero_front_transparent.png   (canonical transparent hero)

Outputs (in this directory):
  mark-32.png            32x32   favicon
  mark-180.png           180x180 apple-touch-icon
  avatar-400.png         400x400 social avatar
  social-card-1200.png   1200x630 og:image / Twitter card with wordmark

Mirrors ../werner/marks/build_marks.py (same recipe, brain source).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
SRC = HERE.parent / "mascot-brain" / "01_hero_front_transparent.png"

# Brand
INK = (0x0F, 0x14, 0x19, 255)
ICE = (0xFB, 0xFC, 0xFD, 255)
SUN = (0xF5, 0xDF, 0x24, 255)


def crop_to_square(img: Image.Image, pad_ratio: float = 0.06) -> Image.Image:
    """Crop to the brain's bounding box (non-transparent pixels), then pad to square."""
    alpha = img.getchannel("A")
    bbox = alpha.point(lambda p: 255 if p > 8 else 0).getbbox()
    if not bbox:
        return img
    cropped = img.crop(bbox)
    w, h = cropped.size
    side = max(w, h)
    pad = int(side * pad_ratio)
    side += 2 * pad
    out = Image.new("RGBA", (side, side), ICE)
    out.paste(cropped, ((side - w) // 2, (side - h) // 2), cropped)
    return out


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"missing source: {SRC}")
    brain = Image.open(SRC).convert("RGBA")
    square = crop_to_square(brain)

    # Favicon — 32x32, tightly cropped, on ice background
    fav = square.resize((32, 32), Image.LANCZOS)
    fav.save(HERE / "mark-32.png")

    # Apple touch icon — 180x180, ice background
    apple = square.resize((180, 180), Image.LANCZOS)
    apple.save(HERE / "mark-180.png")

    # Avatar 400x400 — ice background
    avatar = square.resize((400, 400), Image.LANCZOS)
    avatar.save(HERE / "avatar-400.png")

    # Social card 1200x630 with wordmark right of mark
    card = Image.new("RGBA", (1200, 630), ICE)
    draw = ImageDraw.Draw(card)
    draw.rectangle([0, 0, 1200, 8], fill=SUN)
    draw.rectangle([0, 622, 1200, 630], fill=SUN)

    # Brain on left half (centered vertically)
    brain_card = square.resize((460, 460), Image.LANCZOS)
    card.paste(brain_card, (120, 85), brain_card)

    # Wordmark area on right half
    try:
        font_big = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 88)
        font_sub = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 28)
    except OSError:
        font_big = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    draw.text((640, 240), "ANTIEK", fill=INK, font=font_big)
    draw.text((640, 350), "the unknown, mapped.", fill=(0x3C, 0x4A, 0x57, 255), font=font_sub)

    draw.rectangle([640, 410, 770, 418], fill=SUN, outline=INK, width=2)

    card.save(HERE / "social-card-1200.png")

    for f in ["mark-32.png", "mark-180.png", "avatar-400.png", "social-card-1200.png"]:
        p = HERE / f
        sz = Image.open(p).size
        print(f"  {f}  ->  {sz[0]}x{sz[1]}  ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
