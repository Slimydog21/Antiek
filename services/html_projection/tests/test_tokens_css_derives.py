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

Scope note: this targets the SPR-03 widget palette (``LEMON_WIDGET_CSS``).
``TOKENS_CSS`` is the SPR-02 projection *chrome* palette (the
``--antiek-*`` set) — a deliberately separate, byte-pinned language — and is
out of scope for this constant-derivation check.
"""

from __future__ import annotations

import re

from services.html_projection import tokens

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
