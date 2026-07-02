"""Lemon-UI vertical timeline widget.

Data contract:
  events: list[dict], required. Each item has label: str, at: str,
    detail: str | None, and tone: str | None.
  title: str | None, optional heading.

Degenerate-case policy:
  Empty/missing events render "no events". Missing required label/at render
  "—". Events render in list order with no sorting. At most 12 events render;
  additional events are summarized with a visible "+N more" marker. The spine
  is the Lemon 2px ink line; spacing and card geometry come from LEMON_*.
"""

from __future__ import annotations

from services.html_projection import tokens
from services.html_projection.escape import escape_text

MAX_EVENTS = 12


def _tone_color(tone: object) -> str:
    if tone == "primary":
        return tokens.LEMON_PRIMARY
    if tone == "success":
        return tokens.LEMON_SUCCESS
    if tone == "warning":
        return tokens.LEMON_WARNING
    if tone == "danger":
        return tokens.LEMON_DANGER
    if tone == "info":
        return tokens.LEMON_INFO
    if tone == "neutral":
        return tokens.LEMON_NEUTRALS[2]
    return tokens.LEMON_ACCENT


def render(data: dict) -> str:
    raw_events = data.get("events")
    events = raw_events if isinstance(raw_events, list) else []
    title = data.get("title")
    heading = (
        f'<div style="font-weight:800;margin-bottom:{tokens.LEMON_SPACING[3]};">{escape_text(str(title))}</div>'
        if title is not None
        else ""
    )
    if not events:
        return (
            f'<div class="lemon lemon-card" style="border:{tokens.LEMON_BORDER};'
            f'border-radius:{tokens.LEMON_RADIUS};box-shadow:{tokens.LEMON_SHADOW};'
            f'background:{tokens.LEMON_SURFACE};padding:{tokens.LEMON_SPACING[4]};'
            f'color:{tokens.LEMON_NEUTRALS[3]};">{heading}no events</div>'
        )
    rows: list[str] = []
    for item in events[:MAX_EVENTS]:
        if not isinstance(item, dict):
            label = at = "—"
            detail = None
            tone = None
        else:
            label = item.get("label") if item.get("label") is not None else "—"
            at = item.get("at") if item.get("at") is not None else "—"
            detail = item.get("detail")
            tone = item.get("tone")
        detail_html = (
            f'<div style="color:{tokens.LEMON_NEUTRALS[3]};font-size:.88rem;margin-top:{tokens.LEMON_SPACING[1]};">'
            f"{escape_text(str(detail))}</div>"
            if detail is not None
            else ""
        )
        rows.append(
            f'<div style="position:relative;padding-left:28px;margin-bottom:{tokens.LEMON_SPACING[4]};">'
            f'<span style="position:absolute;left:0;top:3px;width:14px;height:14px;'
            f'background:{_tone_color(tone)};border:{tokens.LEMON_BORDER};border-radius:9999px;"></span>'
            f'<div style="font-weight:800;">{escape_text(str(label))}</div>'
            f'<div style="font-size:.82rem;color:{tokens.LEMON_NEUTRALS[3]};">{escape_text(str(at))}</div>'
            f"{detail_html}</div>"
        )
    more = len(events) - MAX_EVENTS
    if more > 0:
        rows.append(
            f'<div style="position:relative;padding-left:28px;color:{tokens.LEMON_NEUTRALS[3]};'
            f'font-weight:700;">+{more} more</div>'
        )
    return (
        f'<div class="lemon lemon-card" style="border:{tokens.LEMON_BORDER};'
        f'border-radius:{tokens.LEMON_RADIUS};box-shadow:{tokens.LEMON_SHADOW};'
        f'background:{tokens.LEMON_SURFACE};padding:{tokens.LEMON_SPACING[4]};'
        f'color:{tokens.LEMON_INK};">{heading}'
        f'<div style="position:relative;"><div style="position:absolute;left:7px;top:5px;bottom:5px;'
        f'width:2px;background:{tokens.LEMON_INK};"></div>{"".join(rows)}</div></div>'
    )
