"""
Derive favicon + apple-touch-icon + social card from the locked default pose.

Inputs:
  ../poses/anchor/werner_default_v5_nano_corrected.png

Outputs (in this directory):
  mark-32.png            32x32   favicon
  mark-180.png           180x180 apple-touch-icon
  avatar-400.png         400x400 social avatar
  social-card-1200.png   1200x630 og:image / Twitter card with wordmark
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
SRC = HERE.parent / "poses" / "anchor" / "werner_default_v5_nano_corrected.png"

# Brand
INK = (0x0F, 0x14, 0x19, 255)
ICE = (0xFB, 0xFC, 0xFD, 255)
SUN = (0xF5, 0xDF, 0x24, 255)


def crop_to_square(img: Image.Image, pad_ratio: float = 0.06) -> Image.Image:
    """Crop to the penguin's bounding box (non-white pixels), then pad to square."""
    # Treat near-white as background to find bbox
    bg_thresh = 250
    bw = img.convert("L")
    bbox = bw.point(lambda p: 0 if p > bg_thresh else 255).getbbox()
    if not bbox:
        return img
    cropped = img.crop(bbox)
    w, h = cropped.size
    side = max(w, h)
    pad = int(side * pad_ratio)
    side += 2 * pad
    out = Image.new("RGBA", (side, side), ICE)
    out.paste(cropped, ((side - w) // 2, (side - h) // 2), cropped if cropped.mode == "RGBA" else None)
    return out


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"missing source: {SRC}")
    werner = Image.open(SRC).convert("RGBA")
    square = crop_to_square(werner)

    # Favicon — 32×32, tightly cropped, on ice background
    fav = square.resize((32, 32), Image.LANCZOS)
    (HERE / "mark-32.png").write_bytes(b"")  # touch
    fav.save(HERE / "mark-32.png")

    # Apple touch icon — 180×180, ice background, slightly larger pad
    apple = square.resize((180, 180), Image.LANCZOS)
    (HERE / "mark-180.png").touch()
    apple.save(HERE / "mark-180.png")

    # Avatar 400×400 — ice background
    avatar = square.resize((400, 400), Image.LANCZOS)
    avatar.save(HERE / "avatar-400.png")

    # Social card 1200×630 with wordmark right of mark
    card = Image.new("RGBA", (1200, 630), ICE)
    # Stripe of sun along the top
    draw = ImageDraw.Draw(card)
    draw.rectangle([0, 0, 1200, 8], fill=SUN)
    draw.rectangle([0, 622, 1200, 630], fill=SUN)

    # Werner on left half (centered vertically)
    werner_card = square.resize((460, 460), Image.LANCZOS)
    card.paste(werner_card, (120, 85), werner_card)

    # Wordmark area on right half
    try:
        # Try a system bold sans
        font_big = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 88)
        font_sub = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 28)
    except OSError:
        font_big = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    draw.text((640, 240), "ANTIEK", fill=INK, font=font_big)
    draw.text((640, 350), "the unknown, mapped.", fill=(0x3C, 0x4A, 0x57, 255), font=font_sub)

    # Underline accent
    draw.rectangle([640, 410, 770, 418], fill=SUN, outline=INK, width=2)

    card.save(HERE / "social-card-1200.png")

    # Print sizes
    for f in ["mark-32.png", "mark-180.png", "avatar-400.png", "social-card-1200.png"]:
        p = HERE / f
        sz = Image.open(p).size
        print(f"  {f}  →  {sz[0]}x{sz[1]}  ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
