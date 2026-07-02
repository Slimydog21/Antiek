"""Lemon-UI stat chip widget.

Data contract:
  label: str, required. Missing renders "—".
  value: str | int | float, required. Missing renders "—".
  delta: str | int | float | None, optional. Absent/None omits the pill.
  delta_label: str | None, optional. When present, overrides pill text.
  tone: str | None, optional. One of primary, accent, success, warning,
    danger, info, neutral. Unknown tones fall back to neutral.

Degenerate-case policy:
  Missing required fields render visible placeholders. Delta tone is inferred
  from a numeric value or leading sign, otherwise neutral. Layout dimensions
  come from LEMON_SPACING, LEMON_BORDER, LEMON_SHADOW, and LEMON_RADIUS.
"""

from __future__ import annotations

from services.html_projection import tokens
from services.html_projection.escape import escape_text


def _text(value: object, placeholder: str = "—") -> str:
    if value is None:
        return placeholder
    return str(value)


def _tone_color(tone: object, default: str = "accent") -> str:
    name = str(tone) if tone is not None else default
    if name == "primary":
        return tokens.LEMON_PRIMARY
    if name == "accent":
        return tokens.LEMON_ACCENT
    if name == "success":
        return tokens.LEMON_SUCCESS
    if name == "warning":
        return tokens.LEMON_WARNING
    if name == "danger":
        return tokens.LEMON_DANGER
    if name == "info":
        return tokens.LEMON_INFO
    return tokens.LEMON_NEUTRALS[2]


def _delta_tone(delta: object) -> str:
    if delta is None:
        return tokens.LEMON_NEUTRALS[2]
    raw = str(delta).strip()
    try:
        value = float(raw.replace("%", ""))
    except ValueError:
        if raw.startswith("+"):
            return tokens.LEMON_SUCCESS
        if raw.startswith("-"):
            return tokens.LEMON_DANGER
        return tokens.LEMON_NEUTRALS[2]
    if value > 0:
        return tokens.LEMON_SUCCESS
    if value < 0:
        return tokens.LEMON_DANGER
    return tokens.LEMON_NEUTRALS[2]


def render(data: dict) -> str:
    label = escape_text(_text(data.get("label")))
    value = escape_text(_text(data.get("value")))
    accent = _tone_color(data.get("tone"))
    delta = data.get("delta")
    delta_html = ""
    if delta is not None:
        pill_text = data.get("delta_label")
        if pill_text is None:
            pill_text = delta
        delta_html = (
            f'<div style="margin-top:{tokens.LEMON_SPACING[3]};"><span style="display:inline-block;'
            f'padding:{tokens.LEMON_SPACING[1]} '
            f'{tokens.LEMON_SPACING[3]};border:{tokens.LEMON_BORDER};'
            f'border-radius:9999px;background:{tokens.LEMON_SURFACE};'
            f'color:{_delta_tone(delta)};font-size:.75rem;font-weight:700;">'
            f"{escape_text(str(pill_text))}</span></div>"
        )
    return (
        f'<div class="lemon lemon-card" style="border:{tokens.LEMON_BORDER};border-left:8px solid {accent};'
        f'border-radius:{tokens.LEMON_RADIUS};box-shadow:{tokens.LEMON_SHADOW};'
        f'background:{tokens.LEMON_SURFACE};color:{tokens.LEMON_INK};'
        f'padding:{tokens.LEMON_SPACING[4]};display:inline-block;min-width:148px;">'
        f'<div style="font-size:.8rem;font-weight:700;color:{tokens.LEMON_NEUTRALS[3]};'
        f'text-transform:uppercase;letter-spacing:.04em;">{label}</div>'
        f'<div style="font-size:1.6rem;font-weight:800;line-height:1.1;'
        f'margin-top:{tokens.LEMON_SPACING[2]};">{value}</div>'
        f"{delta_html}"
        "</div>"
    )
