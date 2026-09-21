"""Lemon-UI sketch widget — the eighth kind, a p5-flavored generative SVG.

This widget owns NO SVG generation. It is a thin adapter over the agent
kernel skill ``substrate.agent_skills.sketch_svg.sketch_svg`` — the same
deterministic generator a research agent calls directly — so an agent's
sketch and a projection's sketch are byte-identical for identical inputs.
Writing a second renderer here would fork that guarantee; do not.

Data contract:
  seed: int | None, optional PRNG seed for the GENERATIVE composition,
    default 0. Coerced; non-integers fall back to the default.
  title: str | None, optional sketch title, default "sketch". Escaped by
    the skill into ``<title>`` and the data caption.
  data: list[int|float] | None, optional. When the key is ABSENT (or
    None), the widget renders the seeded generative composition. When it
    is present, the widget renders a faithful bar sketch of the series —
    a deterministic VIEW OF THE DATA, which is why ``seed`` has no effect
    in this mode. That is by design, not a bug: see
    ``test_data_mode_is_seed_invariant_by_design``.
  ink: not a caller key. The widget always passes ``tokens.LEMON_INK``
    as the skill's caption/label color, because the widget's ground is
    the pale ``LEMON_NEUTRALS[0]`` and the skill's own default ink is a
    near-white chosen for its dark standalone ground.
  palette: list[str] | None, optional ``#RRGGBB`` colors, >= 2 —
    palette[0] is the ground, the rest are voices. Accepted ONLY when
    every entry is an atomic ``tokens.LEMON_*`` color; any other value
    falls back to ``LEMON_SKETCH_PALETTE`` whole. This is what keeps the
    widget inside invariant 4 (no bare hex, no off-palette color) while
    the skill keeps its own standalone default for non-projection use.
  width: int | None, optional canvas width px, default 480, clamped
    64..960.
  height: int | None, optional canvas height px, default 300, clamped
    64..640.

Degenerate-case policy:
  A ``data`` key that yields no usable numeric values — an empty list, a
  non-list, or a list of only non-numeric/non-finite entries — renders
  the deterministic "no sketch" placeholder rather than silently falling
  back to a generative composition, because a caller that asked for a
  data sketch and got abstract circles would be misled. Non-numeric and
  non-finite (nan/inf) entries are dropped individually, matching
  ``sparkline``. More than ``MAX_VALUES`` values are evenly sampled down
  with the dropped count recorded in the title, matching ``sparkline``'s
  "+N more" bound; the cap is strictly below the skill's own 500-value
  ceiling, so the skill's ValueError is unreachable from this path.

  Any ``ValueError``/``ScriptViolation`` the skill still raises is caught
  and rendered as the same placeholder. The skill is deliberately loud
  (failing at generation beats shipping a poisoned artifact); a widget
  must never crash the projection, so the boundary is defended here. In
  particular a hostile ``title`` can trip the position-conservative gate
  even after escaping — that renders the placeholder, not an exception.
"""

from __future__ import annotations

import math

from services.html_projection import tokens
from services.html_projection.gate import ScriptViolation


def _skill():
    """Return ``substrate.agent_skills.sketch_svg.sketch_svg``, imported
    at CALL time.

    This deferral is load-bearing, not a style choice. The two packages
    are mutually dependent at import time:
    ``substrate.agent_skills.sketch_svg`` imports this package's ``gate``
    (line 49), and ``services.html_projection.__init__`` imports the
    renderer (line 48), which eagerly imports the widget partial
    (``renderer.py:110``), which imports this widgets package. A
    module-level import here therefore raises ``ImportError: cannot
    import name 'sketch_svg' from partially initialized module`` for any
    process that imports ``substrate.agent_skills`` FIRST — which
    ``tests/test_agent_skills.py:33`` does. Deferring to call time breaks
    the cycle: by the time a widget renders, both packages are fully
    initialized. ``test_import_order_independence`` in
    ``tests/test_widgets_render.py`` is the regression gate; it fails if
    this is ever hoisted back to module scope.

    Cost is a ``sys.modules`` dict lookup per render, and determinism is
    untouched (the resolved function is the same object either way).
    """
    from substrate.agent_skills.sketch_svg import sketch_svg

    return sketch_svg


# Bounded output: a projection widget is smaller than a standalone 640px
# sketch, and 160 matches sparkline's MAX_POINTS — the established
# in-repo bound for "how many values stay legible in a widget". It is
# also strictly below the skill's own _MAX_BARS (500), so this widget can
# never hand the skill an over-cap series.
MAX_VALUES = 160

# The projection palette, built from atomic LEMON_* tokens only (invariant
# 4). Index meaning is the skill's: [0] ground, [1] the baseline/outline
# voice, [2] the bar voice, [3] the value-dot / negative-bar voice, the
# rest fill out the generative ring cycle. The skill's own DEFAULT_PALETTE
# is for standalone agent use and is off-palette here on purpose.
LEMON_SKETCH_PALETTE: tuple[str, ...] = (
    tokens.LEMON_NEUTRALS[0],  # ground
    tokens.LEMON_INK,  # baseline + outline rings
    tokens.LEMON_PRIMARY,  # bars / first ring voice
    tokens.LEMON_ACCENT,  # value dots + negative bars
    tokens.LEMON_INFO,
    tokens.LEMON_SUCCESS,
)

_ALLOWED_COLORS: frozenset[str] = frozenset(
    color.lower() for color in LEMON_SKETCH_PALETTE
) | frozenset(
    color.lower()
    for color in (
        tokens.LEMON_DANGER,
        tokens.LEMON_WARNING,
        tokens.LEMON_SURFACE,
        *tokens.LEMON_NEUTRALS,
        *tokens.LEMON_CATEGORY_COLORS,
    )
)


def _num(value: object) -> float | None:
    """Parse one series entry; drop non-numeric and non-finite. ``bool``
    is rejected explicitly — ``float(True)`` is 1.0, and a boolean in a
    numeric series is a caller bug, not a data point."""
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _int(value: object, default: int, low: int, high: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError, OverflowError):
        return default
    return max(low, min(high, parsed))


def _seed(value: object) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError, OverflowError):
        return 0


def _palette(value: object) -> tuple[str, ...]:
    """Accept a caller palette only when every entry is an atomic LEMON
    color. A partially-valid palette falls back WHOLE rather than being
    patched entry by entry: index position carries meaning here (ground
    vs. voices), so a silently repaired palette would render a
    composition the caller never asked for."""
    if not isinstance(value, list) or len(value) < 2:
        return LEMON_SKETCH_PALETTE
    for entry in value:
        if not isinstance(entry, str) or entry.lower() not in _ALLOWED_COLORS:
            return LEMON_SKETCH_PALETTE
    return tuple(value)


def _sample(values: list[float]) -> list[float]:
    """Even-sample down to MAX_VALUES, preserving the first and last
    value so the series' endpoints still read true."""
    if len(values) <= MAX_VALUES:
        return values
    last = len(values) - 1
    return [values[round(i * last / (MAX_VALUES - 1))] for i in range(MAX_VALUES)]


def _placeholder() -> str:
    """The deterministic no-sketch block, styled like every other widget's
    empty state so the visual language stays consistent."""
    return (
        f'<div class="lemon" style="border:{tokens.LEMON_BORDER};'
        f"border-radius:{tokens.LEMON_RADIUS};box-shadow:{tokens.LEMON_SHADOW};"
        f"background:{tokens.LEMON_SURFACE};padding:{tokens.LEMON_SPACING[3]};"
        f'color:{tokens.LEMON_NEUTRALS[3]};">no sketch</div>'
    )


def render(data: dict) -> str:
    width = _int(data.get("width"), 480, 64, 960)
    height = _int(data.get("height"), 300, 64, 640)
    seed = _seed(data.get("seed"))
    raw_title = data.get("title")
    title = raw_title if isinstance(raw_title, str) and raw_title.strip() else "sketch"
    palette = _palette(data.get("palette"))

    raw_series = data.get("data")
    series: list[float] | None = None
    if raw_series is not None:
        # The key was supplied: this is a DATA-mode request. An unusable
        # series renders the placeholder, never a generative fallback.
        if not isinstance(raw_series, list):
            return _placeholder()
        parsed = [v for v in (_num(item) for item in raw_series) if v is not None]
        if not parsed:
            return _placeholder()
        series = _sample(parsed)
        dropped = len(parsed) - len(series)
        if dropped:
            title = f"{title} (+{dropped} more)"

    try:
        return _skill()(
            width=width,
            height=height,
            seed=seed,
            title=title,
            data=series,
            palette=palette,
            ink=tokens.LEMON_INK,
        )
    except (ValueError, ScriptViolation):
        # The skill is loud by contract; the widget is not allowed to be.
        # A hostile title that trips the position-conservative gate, or an
        # input the skill rejects outright, degrades to the placeholder.
        return _placeholder()
