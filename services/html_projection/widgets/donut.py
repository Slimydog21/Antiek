"""Lemon-UI donut widget.

Data contract:
  categories: list[dict], required. Each item has label: str and value:
    int|float. Values are proportions, not percentages.
  size: int | None, optional square SVG size in px, default 120.
  thickness: int | None, optional ring stroke width in px, default 16.
  title: str | None, optional heading.

Degenerate-case policy:
  Empty/missing/all-zero categories render "no data". Non-numeric or
  non-finite (nan/inf) values become 0 and negatives clamp to 0. At most 8 categories render; excess
  positive values are folded into a visible "+N more" slice. Color assignment
  walks LEMON_CATEGORY_COLORS in index order. Geometry uses deliberate donut
  ratios, with token-derived colors, border, shadow, radius, and spacing.
"""

from __future__ import annotations

import math

from services.html_projection import tokens
from services.html_projection.escape import escape_text

MAX_CATEGORIES = 8


def _num(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    # Non-finite (nan/inf) -> 0 (no contribution to the total).
    return parsed if (math.isfinite(parsed) and parsed > 0) else 0.0


def _int(value: object, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, parsed))


def _fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def render(data: dict) -> str:
    raw_categories = data.get("categories")
    categories = raw_categories if isinstance(raw_categories, list) else []
    rows: list[tuple[str, float]] = []
    for item in categories[:MAX_CATEGORIES]:
        if isinstance(item, dict):
            rows.append((str(item.get("label") if item.get("label") is not None else "—"), _num(item.get("value"))))
        else:
            rows.append(("—", 0.0))
    more = max(0, len(categories) - MAX_CATEGORIES)
    if more:
        folded = 0.0
        for item in categories[MAX_CATEGORIES:]:
            if isinstance(item, dict):
                folded += _num(item.get("value"))
        rows.append((f"+{more} more", folded))
    total = sum(value for _, value in rows)
    title = data.get("title")
    heading = (
        f'<div style="font-weight:800;margin-bottom:{tokens.LEMON_SPACING[3]};">{escape_text(str(title))}</div>'
        if title is not None
        else ""
    )
    if total <= 0:
        return (
            f'<div class="lemon lemon-card" style="border:{tokens.LEMON_BORDER};'
            f'border-radius:{tokens.LEMON_RADIUS};box-shadow:{tokens.LEMON_SHADOW};'
            f'background:{tokens.LEMON_SURFACE};padding:{tokens.LEMON_SPACING[4]};'
            f'color:{tokens.LEMON_NEUTRALS[3]};">{heading}no data</div>'
        )
    size = _int(data.get("size"), 120, 72, 320)
    thickness = _int(data.get("thickness"), 16, 8, max(8, size // 3))
    center = size / 2
    radius = max(4.0, (size - thickness - 8) / 2)
    circumference = 2 * math.pi * radius
    offset = 0.0
    circles: list[str] = []
    legend: list[str] = []
    for index, (label, value) in enumerate(rows):
        fraction = value / total
        dash = fraction * circumference
        color = tokens.LEMON_CATEGORY_COLORS[index % len(tokens.LEMON_CATEGORY_COLORS)]
        circles.append(
            f'<circle cx="{_fmt(center)}" cy="{_fmt(center)}" r="{_fmt(radius)}" fill="none" '
            f'stroke="{color}" stroke-width="{thickness}" stroke-dasharray="{_fmt(dash)} {_fmt(circumference - dash)}" '
            f'stroke-dashoffset="-{_fmt(offset)}" transform="rotate(-90 {_fmt(center)} {_fmt(center)})" />'
        )
        pct_s = _fmt(fraction * 100)
        legend.append(
            f'<div style="display:flex;align-items:center;gap:{tokens.LEMON_SPACING[2]};font-size:.82rem;">'
            f'<span style="display:inline-block;width:10px;height:10px;background:{color};'
            f'border:{tokens.LEMON_BORDER};"></span>'
            f'<span>{escape_text(label)} '
            f'<span style="color:{tokens.LEMON_NEUTRALS[3]};">({escape_text(pct_s)}%)</span>'
            f"</span></div>"
        )
        offset += dash
    return (
        f'<div class="lemon lemon-card" style="border:{tokens.LEMON_BORDER};'
        f'border-radius:{tokens.LEMON_RADIUS};box-shadow:{tokens.LEMON_SHADOW};'
        f'background:{tokens.LEMON_SURFACE};padding:{tokens.LEMON_SPACING[4]};'
        f'color:{tokens.LEMON_INK};">{heading}'
        f'<div style="display:flex;align-items:center;gap:{tokens.LEMON_SPACING[5]};">'
        f'<svg role="img" viewBox="0 0 {size} {size}" width="{size}" height="{size}">'
        f'<circle cx="{_fmt(center)}" cy="{_fmt(center)}" r="{_fmt(radius)}" fill="none" '
        f'stroke="{tokens.LEMON_NEUTRALS[1]}" stroke-width="{thickness}" />'
        f'{"".join(circles)}</svg><div>{"".join(legend)}</div></div></div>'
    )
