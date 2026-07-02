"""Lemon-UI horizontal bar chart widget.

Data contract:
  bars: list[dict], required. Each item has label: str and value: int|float.
  unit: str | None, optional suffix for displayed values.
  max: int | float | None, optional scale maximum.
  title: str | None, optional heading.

Degenerate-case policy:
  Empty/missing bars render "no data". Non-numeric/non-finite values become 0. Negative
  values clamp to 0. At most 12 bars render; additional bars are summarized
  by a visible "+N more" row. Scale max falls back to 1 to avoid division by
  zero. SVG dimensions use deliberate chart judgment calls; colors, border,
  shadow, radius, and spacing come from LEMON_* tokens.
"""

from __future__ import annotations

import math

from services.html_projection import tokens
from services.html_projection.escape import escape_text

MAX_BARS = 12


def _num(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    # Non-finite (nan/inf) -> 0: never let an upstream nan/inf become an
    # unbounded bar width or a "nan"/"inf" token in the SVG.
    return parsed if (math.isfinite(parsed) and parsed > 0) else 0.0


def _fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def render(data: dict) -> str:
    raw_bars = data.get("bars")
    bars = raw_bars if isinstance(raw_bars, list) else []
    rows: list[tuple[str, float]] = []
    for item in bars[:MAX_BARS]:
        if not isinstance(item, dict):
            rows.append(("—", 0.0))
            continue
        rows.append((str(item.get("label") if item.get("label") is not None else "—"), _num(item.get("value"))))
    more = max(0, len(bars) - MAX_BARS)
    title = data.get("title")
    heading = (
        f'<div style="font-weight:800;margin-bottom:{tokens.LEMON_SPACING[3]};">'
        f"{escape_text(str(title))}</div>"
        if title is not None
        else ""
    )
    if not rows:
        return (
            f'<div class="lemon lemon-card" style="border:{tokens.LEMON_BORDER};'
            f'border-radius:{tokens.LEMON_RADIUS};box-shadow:{tokens.LEMON_SHADOW};'
            f'background:{tokens.LEMON_SURFACE};padding:{tokens.LEMON_SPACING[4]};'
            f'color:{tokens.LEMON_NEUTRALS[3]};">{heading}no data</div>'
        )
    max_override = data.get("max")
    scale_max = _num(max_override) if max_override is not None else max((value for _, value in rows), default=0.0)
    if scale_max <= 0:
        scale_max = 1.0
    unit = "" if data.get("unit") is None else str(data.get("unit"))
    width = 560
    row_h = 34
    top = 20
    left = 132
    bar_w = 340
    height = top + len(rows) * row_h + (28 if more else 12)
    svg_rows: list[str] = []
    for index, (label, value) in enumerate(rows):
        y = top + index * row_h
        fill = tokens.LEMON_CATEGORY_COLORS[index % len(tokens.LEMON_CATEGORY_COLORS)]
        # Clamp to the track: a caller-supplied max smaller than a value
        # would otherwise overrun bar_w and clip at the viewBox edge.
        w = min(bar_w, max(1.0, (value / scale_max) * bar_w)) if value > 0 else 0.0
        svg_rows.append(
            f'<text x="0" y="{y + 15}" fill="{tokens.LEMON_INK}" font-size="12" font-weight="700">'
            f"{escape_text(label)}</text>"
            f'<rect x="{left}" y="{y}" width="{bar_w}" height="18" fill="{tokens.LEMON_NEUTRALS[0]}" '
            f'stroke="{tokens.LEMON_INK}" stroke-width="2" />'
            f'<rect x="{left}" y="{y}" width="{_fmt(w)}" height="18" fill="{fill}" '
            f'stroke="{tokens.LEMON_INK}" stroke-width="2" />'
            f'<text x="{left + bar_w + 12}" y="{y + 15}" fill="{tokens.LEMON_NEUTRALS[3]}" '
            f'font-size="12">{escape_text(_fmt(value) + unit)}</text>'
        )
    if more:
        svg_rows.append(
            f'<text x="0" y="{top + len(rows) * row_h + 14}" fill="{tokens.LEMON_NEUTRALS[3]}" '
            f'font-size="12" font-weight="700">+{more} more</text>'
        )
    return (
        f'<div class="lemon lemon-card" style="border:{tokens.LEMON_BORDER};'
        f'border-radius:{tokens.LEMON_RADIUS};box-shadow:{tokens.LEMON_SHADOW};'
        f'background:{tokens.LEMON_SURFACE};padding:{tokens.LEMON_SPACING[4]};'
        f'color:{tokens.LEMON_INK};">{heading}'
        f'<svg role="img" viewBox="0 0 {width} {height}" width="100%" height="{height}">'
        f'{"".join(svg_rows)}</svg></div>'
    )
