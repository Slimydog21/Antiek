"""Lemon-UI sparkline widget.

Data contract:
  points: list[int|float], required. Non-numeric AND non-finite (nan/inf)
    entries are dropped.
  width: int | None, optional SVG viewBox width in px, default 120.
  height: int | None, optional SVG viewBox height in px, default 32.
  stroke: str | None, optional palette stroke override, default LEMON_ACCENT.

Degenerate-case policy:
  Fewer than 2 numeric points render "no trend". At most 160 points render;
  excess points are sampled evenly with a visible "+N more" marker. Width and
  height clamp to legible ranges. Stroke overrides are accepted only when the
  value exactly matches a LEMON palette token. Padding is a deliberate 4px
  chart inset matching LEMON_SPACING[2].
"""

from __future__ import annotations

import math

from services.html_projection import tokens

MAX_POINTS = 160


def _num(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    # Reject non-finite (nan/inf): a metrics pipeline can emit them, and a
    # nan/inf coordinate would corrupt the polyline. Dropped like any
    # non-numeric entry.
    return parsed if math.isfinite(parsed) else None


def _int(value: object, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, parsed))


def _fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _palette_color(value: object) -> str:
    if not isinstance(value, str):
        return tokens.LEMON_ACCENT
    allowed = (
        tokens.LEMON_PRIMARY,
        tokens.LEMON_ACCENT,
        tokens.LEMON_INK,
        tokens.LEMON_SUCCESS,
        tokens.LEMON_WARNING,
        tokens.LEMON_DANGER,
        tokens.LEMON_INFO,
        tokens.LEMON_NEUTRALS[2],
    )
    for color in allowed:
        if value == color:
            return value
    return tokens.LEMON_ACCENT


def _sample(points: list[float]) -> list[float]:
    if len(points) <= MAX_POINTS:
        return points
    last = len(points) - 1
    return [points[round(index * last / (MAX_POINTS - 1))] for index in range(MAX_POINTS)]


def render(data: dict) -> str:
    raw_points = data.get("points")
    points: list[float] = []
    if isinstance(raw_points, list):
        for item in raw_points:
            parsed = _num(item)
            if parsed is not None:
                points.append(parsed)
    width = _int(data.get("width"), 120, 64, 640)
    height = _int(data.get("height"), 32, 24, 240)
    if len(points) < 2:
        return (
            f'<div class="lemon" style="border:{tokens.LEMON_BORDER};border-radius:{tokens.LEMON_RADIUS};'
            f'box-shadow:{tokens.LEMON_SHADOW};background:{tokens.LEMON_SURFACE};'
            f'padding:{tokens.LEMON_SPACING[3]};color:{tokens.LEMON_NEUTRALS[3]};">no trend</div>'
        )
    rendered = _sample(points)
    more = len(points) - len(rendered)
    low = min(rendered)
    high = max(rendered)
    span = high - low if high > low else 1.0
    pad = 4
    usable_w = width - pad * 2
    usable_h = height - pad * 2
    step = usable_w / (len(rendered) - 1)
    coords = []
    for index, value in enumerate(rendered):
        x = pad + index * step
        y = pad + (high - value) / span * usable_h
        coords.append(f"{_fmt(x)},{_fmt(y)}")
    marker = (
        f'<text x="{width - 4}" y="{height - 5}" text-anchor="end" fill="{tokens.LEMON_NEUTRALS[3]}" '
        f'font-size="9" font-weight="700">+{more} more</text>'
        if more
        else ""
    )
    return (
        f'<svg class="lemon" role="img" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'style="border:{tokens.LEMON_BORDER};'
        f'border-radius:{tokens.LEMON_RADIUS};box-shadow:{tokens.LEMON_SHADOW};'
        f'background:{tokens.LEMON_SURFACE};">'
        f'<polyline points="{" ".join(coords)}" fill="none" stroke="{_palette_color(data.get("stroke"))}" '
        f'stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />{marker}</svg>'
    )
