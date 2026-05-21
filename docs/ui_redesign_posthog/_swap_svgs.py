"""
One-shot helper: replace the inline-SVG pose blocks in brand_werner.html
with <img> tags pointing at the generated PNGs.

Run from this directory:
    python3 _swap_svgs.py
"""

import re
from pathlib import Path

HERE = Path(__file__).parent
TARGET = HERE / "brand_werner.html"

# All asset paths are relative from brand_werner.html (which lives in docs/ui_redesign_posthog/)
ASSETS = "../../apps/reading/src/brand/werner"

# Map: aria-label substring → (img_path, alt, css_class)
LABEL_TO_IMG = {
    "Werner the penguin walking away into a vast white horizon": (
        f"{ASSETS}/poses/anchor/werner_hero_v5_nano_corrected.png",
        "Werner walking alone into the Antarctic horizon — Werner Herzog homage",
        "hero",
    ),
    "Werner default avatar": (
        f"{ASSETS}/poses/anchor/werner_default_v5_nano_corrected.png",
        "Werner — default pose, front-facing", "pose"),
    "Werner tobogganing on his belly": (
        f"{ASSETS}/poses/werner_tobogganing_v1_corrected.png",
        "Werner tobogganing", "pose"),
    "Werner curious head tilt": (
        f"{ASSETS}/poses/werner_head_tilt_v1_corrected.png",
        "Werner head-tilt", "pose"),
    "Werner alone in vast white space": (
        f"{ASSETS}/poses/werner_lost_v1_corrected.png",
        "Werner lost in vast space", "pose"),
    "Werner holding a fish, success": (
        f"{ASSETS}/poses/werner_caught_a_fish_v1_corrected.png",
        "Werner with a fish", "pose"),
    "Werner asleep": (
        f"{ASSETS}/poses/werner_sleeping_v1_corrected.png",
        "Werner asleep", "pose"),
    "Werner thinking, in the abyss": (
        f"{ASSETS}/poses/werner_thinking_v1_corrected.png",
        "Werner thinking", "pose"),
    "Mark — Werner head only, framed": (
        f"{ASSETS}/marks/mark-180.png",
        "Antiek mark", "logo-framed"),
    "Wordmark — Werner head + Antiek": (
        f"{ASSETS}/marks/avatar-400.png",
        "Antiek wordmark", "logo-wordmark"),
    "Wordmark — night version": (
        f"{ASSETS}/marks/avatar-400.png",
        "Antiek wordmark (night)", "logo-wordmark-night"),
}

SVG_PATTERN = re.compile(
    r'<svg viewBox="[^"]+" aria-label="([^"]+)">.*?</svg>',
    re.DOTALL,
)

html = TARGET.read_text()

def replace(match: re.Match) -> str:
    label = match.group(1)
    if label not in LABEL_TO_IMG:
        print(f"  ! unmatched: {label!r} — keeping SVG")
        return match.group(0)
    src, alt, kind = LABEL_TO_IMG[label]
    if kind == "hero":
        return f'<img class="pose-img-hero" src="{src}" alt="{alt}" />'
    if kind == "pose":
        return f'<img class="pose-img" src="{src}" alt="{alt}" />'
    if kind == "logo-framed":
        return f'<img class="lockup-mark" src="{src}" alt="{alt}" />'
    if kind == "logo-wordmark":
        return (
            f'<div class="lockup-row">'
            f'<img class="lockup-mark-sm" src="{src}" alt="{alt}" />'
            f'<span class="lockup-text">ANTIEK</span>'
            f'</div>'
        )
    if kind == "logo-wordmark-night":
        return (
            f'<div class="lockup-row night">'
            f'<img class="lockup-mark-sm" src="{src}" alt="{alt}" />'
            f'<span class="lockup-text">ANTIEK</span>'
            f'</div>'
        )
    return match.group(0)

new_html, n = SVG_PATTERN.subn(replace, html)
print(f"swapped {n} SVG blocks")

# Add CSS for the new img classes (one-time append into a <style> block at <head>)
extra_css = """
<style>
  /* Werner mascot images — replace inline SVGs */
  .pose-img-hero { width: 100%; max-width: 880px; height: auto; display: block; margin: 0 auto; }
  .pose-img      { width: 100%; height: auto; max-height: 220px; object-fit: contain; }
  .lockup-mark   { width: 80%; max-width: 160px; height: auto; }
  .lockup-mark-sm{ width: 56px; height: 56px; }
  .lockup-row    { display: flex; align-items: center; gap: 14px; padding: 16px;
                   background: var(--ice-0); border: var(--edge-width) solid var(--sun);
                   border-radius: var(--edge-radius); box-shadow: var(--shadow-z2); }
  .lockup-row.night { background: var(--ink); }
  .lockup-row.night .lockup-text { color: var(--ice-1); }
  .lockup-text   { font-family: var(--display); font-weight: 800; font-size: 32px;
                   letter-spacing: -0.5px; color: var(--ink); }
  @media (prefers-color-scheme: dark) {
    .lockup-row { background: var(--charcoal-2, #1B202A); }
    .lockup-row.night { background: #060810; }
  }
</style>
"""

if 'class="pose-img-hero"' in new_html and "/* Werner mascot images" not in new_html:
    new_html = new_html.replace("</head>", extra_css + "</head>", 1)
    print("injected pose-img CSS")

TARGET.write_text(new_html)
print(f"wrote {TARGET}")
