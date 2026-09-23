"""Lemon-UI sketch widget — the Processing/p5 lane's projection surface.

The eighth widget kind, and a thin renderer: every byte of SVG comes from
``substrate.agent_skills.sketch_svg.sketch_svg``, the research agents'
Processing/p5-inspired generative skill, so this module holds no drawing
code of its own. What it adds is the widget contract — the ``data`` dict,
palette discipline, the never-raise placeholder — over the skill's keyword
API. It is also the first product importer of ``substrate/agent_skills``
(the reachability gate's "wiring is the constraint" condition for that
package), which is why the import below is module-level and not lazy.

Data contract:
  data: list[int|float] | None, optional. The series to sketch as bars.
    Non-numeric AND non-finite (nan/inf) entries are dropped. Empty or
    absent -> the seeded generative composition (nested circles in a grid).
  seed: int | None, optional, default 0. Same seed + data = identical bytes.
  title: str | None, optional, default "sketch". Escaped by the skill into
    the SVG <title> and the data caption.
  width: int | None, optional canvas width px, default 640.
  height: int | None, optional canvas height px, default 400.

Degenerate-case policy:
  More than MAX_VALUES values render the first MAX_VALUES (the skill's own
  cap; the mandate is a sketch, not a plot engine — the caption carries n).
  Width and height clamp to legible ranges. The palette is NOT caller-
  supplied: ground, voices and label ink all derive from ``tokens.LEMON_*``
  so the palette lint holds. The skill runs the zero-script gate live and
  raises on a title carrying a gate-flagged byte sequence
  (``src=javascript:``); the widget renders the deterministic "no sketch"
  placeholder instead of propagating an exception.
"""

from __future__ import annotations

import math

from services.html_projection import tokens
from services.html_projection.gate import ScriptViolation

# The PACKAGE, resolved to its ``sketch_svg`` re-export at call time. The
# package binds the function over its own submodule of the same name, and it
# imports this package's gate, so a name bound at import time would be the
# module in one import order and the function in the other; the package
# attribute is the same object in both once the cycle has closed.
from substrate import agent_skills as _skills

# The skill's bar cap (``sketch_svg._MAX_BARS``); the widget truncates where
# the skill would raise, because a widget never crashes on its input.
MAX_VALUES = 500

# The skill's palette contract is ``[0]`` ground + voice colors. Its data
# body draws the baseline in palette[1], bars in palette[2], negative bars
# in palette[3] and value dots in palette[1 + 2 % voices]; its generative
# body nests rings in palette[1..3] and connects nodes in palette[1]. Every
# entry is an atomic LEMON token so the output is palette-pure.
PALETTE: tuple[str, ...] = (
    tokens.LEMON_SURFACE,  # ground
    tokens.LEMON_INK,      # baseline, connectors, outer ring
    tokens.LEMON_ACCENT,   # bars, second ring
    tokens.LEMON_PRIMARY,  # negative bars, value dots, third ring
    tokens.LEMON_INFO,
)


def _num(value: object) -> float | None:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    # Non-finite values would fail the skill's data validation (a loud
    # ValueError); dropped like any non-numeric entry, as sparkline does.
    return parsed if math.isfinite(parsed) else None


def _int(value: object, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return default
    return max(low, min(high, parsed))


def _placeholder() -> str:
    return (
        f'<div class="lemon" style="border:{tokens.LEMON_BORDER};border-radius:{tokens.LEMON_RADIUS};'
        f'box-shadow:{tokens.LEMON_SHADOW};background:{tokens.LEMON_SURFACE};'
        f'padding:{tokens.LEMON_SPACING[3]};color:{tokens.LEMON_NEUTRALS[3]};">no sketch</div>'
    )


def render(data: dict) -> str:
    raw_values = data.get("data")
    values: list[float] = []
    if isinstance(raw_values, list):
        for item in raw_values:
            parsed = _num(item)
            if parsed is not None:
                values.append(parsed)
    # SeededRng masks the seed to 64 bits; clamp so a hostile seed cannot
    # reach the skill as anything but a plain non-negative int.
    seed = _int(data.get("seed"), 0, 0, (1 << 64) - 1)
    title = data.get("title")
    width = _int(data.get("width"), 640, 64, 1280)
    height = _int(data.get("height"), 400, 48, 800)
    try:
        return _skills.sketch_svg(
            width=width,
            height=height,
            seed=seed,
            title="sketch" if title is None else str(title),
            data=values[:MAX_VALUES] or None,
            palette=PALETTE,
            ink=tokens.LEMON_INK,
        )
    except (ValueError, ScriptViolation):
        # The skill validates loudly (its contract); the widget's contract is
        # a visible deterministic fallback, never a crash.
        return _placeholder()
