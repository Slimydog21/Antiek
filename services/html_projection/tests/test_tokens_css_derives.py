"""M1 "single source of truth" gate (HPRJ SPR-03).

Every color in the widget CSS block (``LEMON_WIDGET_CSS``) must DERIVE from
an atomic palette constant — there must be no hex literal duplicated into
the CSS string by hand. This is what keeps the palette coherent when seven
widget files evolve independently: change ``LEMON_INK`` once and every
surface follows; a hand-copied ``#0F1419`` would silently drift.

The check: extract every ``#rrggbb`` from ``LEMON_WIDGET_CSS`` and assert
each one traces to a non-``_CSS`` ``LEMON_*`` constant. We exclude the
``*_CSS`` aggregates from the source set so the test is meaningful (a hex
must trace to an *atomic* constant, not merely appear in some CSS string).

Scope note: the derivation check targets the SPR-03 widget palette
(``LEMON_WIDGET_CSS``). ``TOKENS_CSS`` is the SPR-02 projection *chrome*
palette (the ``--antiek-*`` set) — a deliberately separate language — and is
out of scope for the constant-derivation check. It has its own single-source
contract, enforced below: every colour literal lives in the ``:root`` token
block, the day/night/print blocks only re-point tokens, and a theme that
redefines a token (slate) actually changes what a block resolves to.
"""

from __future__ import annotations

import re

from services.html_projection import tokens
from services.html_projection.context import RenderContext
from services.html_projection.renderer import render

_HEX = re.compile(r"#[0-9a-fA-F]{6}")


def _atomic_constant_hexes() -> set[str]:
    """All hex values reachable from atomic LEMON_* constants (strings,
    tuples, and tuples-of-tuples), excluding the ``*_CSS`` aggregates."""
    found: set[str] = set()
    for name in dir(tokens):
        if not name.startswith("LEMON_") or name.endswith("_CSS"):
            continue
        value = getattr(tokens, name)
        # str() flattens nested tuples/pairs into one searchable blob.
        for hex_match in _HEX.findall(str(value)):
            found.add(hex_match.lower())
    return found


def test_widget_css_hexes_all_derive_from_atomic_constants() -> None:
    css_hexes = {h.lower() for h in _HEX.findall(tokens.LEMON_WIDGET_CSS)}
    assert css_hexes, "expected at least one color in LEMON_WIDGET_CSS"
    atomic = _atomic_constant_hexes()
    orphans = css_hexes - atomic
    assert not orphans, (
        "LEMON_WIDGET_CSS contains hex literal(s) not derived from any "
        f"atomic LEMON_* constant: {sorted(orphans)}"
    )


def test_widget_css_carries_the_load_bearing_palette() -> None:
    # Guard against the inverse failure: the CSS deriving from constants but
    # silently dropping the brand-defining ink. The Lemon-UI ink is the
    # 2px-border / hard-shadow signature; if it vanished, the derivation
    # test could still pass on a hollowed-out stylesheet.
    assert tokens.LEMON_INK.lower() in tokens.LEMON_WIDGET_CSS.lower()
    assert tokens.LEMON_SURFACE.lower() in tokens.LEMON_WIDGET_CSS.lower()


# ── Projection chrome: day / night / print (SPR-06 task 3) ──
#
# The chrome palette used to hard-code ``#fafaff`` on five block backgrounds
# and ``#f6f6fa`` on two code surfaces, outside the token block. A theme
# (slate) could re-skin the page but not those blocks, so they rendered as
# near-white boxes on a dark surface, and there was no night or print form at
# all. The contract now: colour literals live ONLY in the ``:root`` block;
# the inset and code tints are derived from the surface by ``color-mix``; the
# dark-scheme and print media blocks re-point tokens; and a block's
# background follows the token a theme can redefine.

_ROOT_BLOCK = re.compile(r":root\s*\{[^}]*\}")
_ANY_HEX = re.compile(r"#[0-9a-fA-F]{3,8}")
# An ``@media`` block with one level of nested rule blocks inside it.
_MEDIA_BLOCK = re.compile(r"@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", re.DOTALL)
_STYLE_ELEMENT = re.compile(r"<style>\n(.*?)</style>", re.DOTALL)
_VAR_REF = re.compile(r"var\((--[a-z0-9-]+)\)")
_COLOR_MIX = re.compile(r"color-mix\(in srgb,\s*(.+?),\s*(.+)\s+([0-9.]+)%\)")


def test_no_raw_hex_outside_root_token_block() -> None:
    css = tokens.TOKENS_CSS
    root = _ROOT_BLOCK.search(css)
    assert root is not None, "TOKENS_CSS has no :root token block"
    orphans = _ANY_HEX.findall(css.replace(root.group(0), ""))
    assert not orphans, (
        "TOKENS_CSS carries colour literal(s) outside the :root token block, "
        f"where no theme can reach them: {sorted(set(orphans))}"
    )
    # The inverse failure: an empty token block would also pass the check above.
    assert "--antiek-inset:" in root.group(0)
    assert "--antiek-code-bg:" in root.group(0)


def test_exactly_one_dark_and_one_print_block() -> None:
    css = tokens.TOKENS_CSS
    assert css.count("prefers-color-scheme") == 1, css.count("prefers-color-scheme")
    assert css.count("@media print") == 1, css.count("@media print")
    dark = re.search(r"@media \(prefers-color-scheme: dark\)\s*\{(.*?)\n\}", css, re.DOTALL)
    assert dark is not None
    # The night block must redefine the palette, not be an empty gesture.
    for token in ("--antiek-surface", "--antiek-ink", "--antiek-rule", "--antiek-accent"):
        assert f"{token}:var(--antiek-night-" in dark.group(1), token
    assert "--antiek-lift:var(--antiek-night-lift)" in dark.group(1)
    # Print comes AFTER the dark block so it wins at equal specificity: paper
    # gets the day palette even on a dark-scheme machine.
    assert css.index("@media print") > css.index("prefers-color-scheme")


def _last_declared(css: str, name: str) -> str:
    decls = re.findall(rf"{re.escape(name)}\s*:\s*([^;]+);", css)
    assert decls, f"{name} is never declared"
    return decls[-1].strip()


def _substitute(css: str, expr: str, depth: int = 0) -> str:
    """Replace every ``var(--x)`` in ``expr`` with its last declared value.

    Later rules win, and a theme is appended after the base, so "last
    declared" is the cascade for every declaration in play here: they all sit
    on ``:root`` or on the theme's ``.antiek-doc`` block, which is both later
    and more specific.
    """
    assert depth < 16, f"var() chain too deep in {expr!r}"
    return _VAR_REF.sub(
        lambda m: _substitute(css, _last_declared(css, m.group(1)), depth + 1), expr
    )


def _rgb(expr: str) -> tuple[float, float, float]:
    """Evaluate a ``#rrggbb`` literal or a ``color-mix(in srgb, A, B P%)``
    with every ``var()`` already substituted. ``in srgb`` interpolates the
    gamma-encoded channels, which is exactly the arithmetic below."""
    expr = expr.strip()
    if expr.startswith("#"):
        digits = expr[1:]
        if len(digits) == 3:
            digits = "".join(ch * 2 for ch in digits)
        r, g, b = (float(int(digits[i : i + 2], 16)) for i in (0, 2, 4))
        return r, g, b
    mix = _COLOR_MIX.fullmatch(expr)
    assert mix is not None, f"unsupported colour expression {expr!r}"
    base, other, share = _rgb(mix.group(1)), _rgb(mix.group(2)), float(mix.group(3)) / 100
    r, g, b = (b0 * (1 - share) + o * share for b0, o in zip(base, other, strict=True))
    return r, g, b


def _screen_light_rgb(stylesheet: str, name: str) -> tuple[float, float, float]:
    """The colour ``name`` cascades to on a light-scheme screen: drop the
    ``@media`` blocks (dark scheme, print), substitute, evaluate."""
    return _rgb(_substitute(_MEDIA_BLOCK.sub("", stylesheet), f"var({name})"))


def _luminance(rgb: tuple[float, float, float]) -> float:
    """sRGB relative luminance (0 = black, 1 = white) of 0-255 channels."""

    def linear(channel: float) -> float:
        c = channel / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b)


def _rendered_stylesheet(style: str) -> str:
    doc = {"title": "t", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "x"}]}]}
    match = _STYLE_ELEMENT.search(render(doc, RenderContext(), style=style))
    assert match is not None
    return match.group(1)


def test_slate_render_has_no_lighter_inset() -> None:
    sheet = _rendered_stylesheet("slate")
    # The blocks must reference the token; a literal here is what slate could
    # never override.
    for block in (".antiek-voice{", ".antiek-region{", ".antiek-note{", ".antiek-image{", ".antiek-table th{"):
        rule = sheet[sheet.index(block):]
        rule = rule[: rule.index("}")]
        assert "background:var(--antiek-inset)" in rule, block
    inset = _screen_light_rgb(sheet, "--antiek-inset")
    surface = _screen_light_rgb(sheet, "--antiek-surface")
    assert _luminance(surface) < 0.05, f"slate page is not dark: {surface}"
    assert _luminance(inset) < 0.2, (
        f"under slate a block inset resolves to {inset}, a light box on a "
        f"{surface} page"
    )
    # A dark inset that is not lifted off the page at all would pass the
    # check above and read as no inset; slate lifts by its own share.
    assert _luminance(inset) > _luminance(surface)
    # And the default wheel style keeps its day inset: the token, not slate,
    # is what moved.
    day_inset = _screen_light_rgb(_rendered_stylesheet("antiek"), "--antiek-inset")
    assert _luminance(day_inset) > 0.8, day_inset
