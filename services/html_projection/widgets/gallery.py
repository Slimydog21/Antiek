"""Widget gallery generator (HPRJ SPR-03 M3).

Renders every widget at every fixture shape into a single self-contained,
script-free ``gallery.html`` — the living visual-review surface. It eats its
own dogfood: the page is built from the same widgets + tokens it documents, so
a regeneration test (``tests/test_gallery.py``) keeps the committed file from
ever drifting from the code.

Determinism: widgets are walked in ``WIDGET_KINDS`` order, shapes in a fixed
order; no wall-clock, no randomness. The frame styling derives entirely from
``tokens.LEMON_*`` so the gallery stays inside the widget palette.

Regenerate:  ``./.venv/bin/python -m services.html_projection.widgets.gallery``
"""

from __future__ import annotations

import importlib
import pathlib

from services.html_projection import tokens
from services.html_projection.escape import escape_text
from services.html_projection.widgets import WIDGET_KINDS
from services.html_projection.widgets._fixtures import FIXTURES

_SHAPES = ("empty", "typical", "degenerate")
_GALLERY_PATH = pathlib.Path(__file__).parent / "gallery.html"

# Page frame — every value derives from an atomic LEMON_* token so the gallery
# stays inside the widget palette (no chrome --antiek-* colors leak in).
_PAGE_CSS = f"""\
body{{margin:0;background:{tokens.LEMON_NEUTRALS[0]};color:{tokens.LEMON_INK};\
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;\
padding:{tokens.LEMON_SPACING[6]};line-height:1.5;}}
h1{{font-size:1.5rem;margin:0 0 {tokens.LEMON_SPACING[5]};}}
h2{{font-size:1rem;text-transform:uppercase;letter-spacing:.05em;\
color:{tokens.LEMON_NEUTRALS[3]};margin:{tokens.LEMON_SPACING[6]} 0 \
{tokens.LEMON_SPACING[3]};border-bottom:{tokens.LEMON_BORDER};\
padding-bottom:{tokens.LEMON_SPACING[2]};}}
.gallery-row{{display:flex;flex-wrap:wrap;gap:{tokens.LEMON_SPACING[5]};\
align-items:flex-start;}}
figure{{margin:0;border:{tokens.LEMON_BORDER};background:{tokens.LEMON_SURFACE};\
border-radius:{tokens.LEMON_RADIUS};box-shadow:{tokens.LEMON_SHADOW};\
padding:{tokens.LEMON_SPACING[4]};max-width:340px;overflow:hidden;}}
figcaption{{font-size:.75rem;text-transform:uppercase;letter-spacing:.05em;\
color:{tokens.LEMON_NEUTRALS[3]};margin-bottom:{tokens.LEMON_SPACING[3]};}}
"""


def _render(kind: str, data: dict) -> str:
    mod = importlib.import_module(f"services.html_projection.widgets.{kind}")
    return mod.render(data)


def build_gallery() -> str:
    """Build the full gallery HTML string (deterministic, script-free)."""
    parts: list[str] = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Antiek widget gallery</title>",
        f"<style>\n{tokens.LEMON_WIDGET_CSS}{_PAGE_CSS}</style>",
        "</head>",
        "<body>",
        "<h1>Antiek HTML Projection — widget gallery</h1>",
    ]
    for kind in WIDGET_KINDS:
        parts.append(f"<h2>{escape_text(kind)}</h2>")
        parts.append('<div class="gallery-row">')
        for shape in _SHAPES:
            parts.append("<figure>")
            parts.append(f"<figcaption>{escape_text(shape)}</figcaption>")
            parts.append(_render(kind, FIXTURES[kind][shape]))
            parts.append("</figure>")
        parts.append("</div>")
    parts.extend(["</body>", "</html>", ""])
    return "\n".join(parts)


def write_gallery(path: pathlib.Path | None = None) -> pathlib.Path:
    target = path or _GALLERY_PATH
    target.write_text(build_gallery(), encoding="utf-8")
    return target


def main() -> None:  # pragma: no cover - thin CLI
    written = write_gallery()
    print(f"wrote {written}")


if __name__ == "__main__":  # pragma: no cover
    main()
