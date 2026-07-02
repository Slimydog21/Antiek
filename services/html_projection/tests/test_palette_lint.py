"""Palette lint (HPRJ SPR-03 M4): every widget color traces to tokens.py.

This is what keeps the visual language coherent as seven widget files evolve
independently. It scans every widget's rendered output for color values and
fails on any hex that is not derived from an atomic ``LEMON_*`` constant. A
seeded off-palette color is proven to turn it red (then removed), so the lint
is known to actually bite — not a green rubber stamp.

Scope: the SPR-03 widget palette. The SPR-02 projection *chrome*
(``--antiek-*`` in ``TOKENS_CSS``) is a separate language and is not scanned
here.
"""

from __future__ import annotations

import importlib
import re

import pytest

from services.html_projection import tokens
from services.html_projection.widgets._fixtures import FIXTURES

# 6- and 3-digit hex; also catch rgb()/rgba() which would bypass a hex scan.
_HEX = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")
_RGB = re.compile(r"rgba?\(", re.IGNORECASE)
KINDS = sorted(FIXTURES)
SHAPES = ("empty", "typical", "degenerate")


def _render(kind: str, data: dict) -> str:
    mod = importlib.import_module(f"services.html_projection.widgets.{kind}")
    return mod.render(data)


def _atomic_palette() -> set[str]:
    """Every hex reachable from a non-``_CSS`` ``LEMON_*`` constant, lowercased.
    Excludes the ``*_CSS`` aggregates so a color must trace to an ATOMIC token,
    not merely appear in some CSS blob."""
    found: set[str] = set()
    for name in dir(tokens):
        if not name.startswith("LEMON_") or name.endswith("_CSS"):
            continue
        for hit in _HEX.findall(str(getattr(tokens, name))):
            found.add(hit.lower())
    return found


def offending_colors(html: str) -> list[str]:
    """Return colors in ``html`` not derived from the atomic palette. A pure
    function so the red-proof can exercise it directly."""
    palette = _atomic_palette()
    bad = [h for h in _HEX.findall(html) if h.lower() not in palette]
    if _RGB.search(html):
        # rgb()/rgba() are off-palette by construction (the tokens are hex).
        bad.append("rgb()/rgba()")
    return bad


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("shape", SHAPES)
def test_widget_output_is_palette_pure(kind: str, shape: str) -> None:
    offenders = offending_colors(_render(kind, FIXTURES[kind][shape]))
    assert not offenders, (
        f"{kind}/{shape} uses off-palette color(s) {offenders}; every color "
        f"must derive from a tokens.LEMON_* constant"
    )


def test_lint_is_not_a_rubber_stamp() -> None:
    # Red-proof: a seeded off-palette color and an rgb() call must both be
    # caught. If this passes while the per-widget tests are green, the lint is
    # known to actually discriminate.
    seeded = '<rect fill="#ff00ff" stroke="rgb(1,2,3)"/>'
    offenders = offending_colors(seeded)
    assert "#ff00ff" in offenders
    assert "rgb()/rgba()" in offenders
    # And a known-good color is accepted.
    assert offending_colors(f'<rect fill="{tokens.LEMON_ACCENT}"/>') == []
