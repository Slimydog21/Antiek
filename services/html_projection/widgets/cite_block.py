"""Lemon-UI citation block widget.

Data contract:
  title: str, required. Missing renders "—".
  url: str | None, optional. Rendered only when its scheme is not
    javascript:/vbscript:/data: after collapsing control chars + whitespace
    (so obfuscated schemes like "java\tscript:" cannot slip into the href).
  quote: str | None, optional pull quote.
  accessed: str | None, optional display string; the widget does not parse it.
  tone: str | None, optional accent rule tone, default accent.

Degenerate-case policy:
  Missing title renders a visible placeholder. Unsafe URLs are dropped and
  render title-only. Quote text is clamped to 600 characters with a visible
  ellipsis marker. All colors, border, shadow, radius, and spacing derive
  from LEMON_* tokens.
"""

from __future__ import annotations

import re

from services.html_projection import tokens
from services.html_projection.escape import escape_attr, escape_text

MAX_QUOTE_CHARS = 600

# Dangerous URL schemes for an href the reader may click. The value is
# lower-cased and ALL control chars + whitespace are collapsed before the
# match, so "java\tscript:", "java script:", and leading-control
# obfuscations cannot slip a live scheme into the href. ``data:`` is
# included because a data:text/html href is a click-time script vector and
# a real citation source never uses one. The zero-script gate is the
# backstop; the widget rejects early and deterministically.
_BAD_URL_SCHEME = re.compile(r"^(?:java\s*script|vbscript|data)\s*:", re.IGNORECASE)


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


def _safe_url(value: object) -> str | None:
    if value is None:
        return None
    url = str(value)
    collapsed = re.sub(r"[\x00-\x1f\x7f\s]+", "", url.lower())
    if _BAD_URL_SCHEME.search(collapsed):
        return None
    return url


def render(data: dict) -> str:
    title = data.get("title")
    title_text = "—" if title is None else str(title)
    url = _safe_url(data.get("url"))
    link = (
        f'<a href="{escape_attr(url)}" style="color:{tokens.LEMON_PRIMARY};font-weight:700;">'
        f"{escape_text(url)}</a>"
        if url is not None
        else ""
    )
    quote = data.get("quote")
    quote_html = ""
    if quote is not None:
        quote_text = str(quote)
        if len(quote_text) > MAX_QUOTE_CHARS:
            quote_text = quote_text[:MAX_QUOTE_CHARS] + "..."
        quote_html = (
            f'<blockquote style="margin:{tokens.LEMON_SPACING[4]} 0 0;'
            f'padding-left:{tokens.LEMON_SPACING[4]};border-left:{tokens.LEMON_BORDER};'
            f'font-style:italic;color:{tokens.LEMON_INK};">{escape_text(quote_text)}</blockquote>'
        )
    accessed = data.get("accessed")
    accessed_html = (
        f'<div style="color:{tokens.LEMON_NEUTRALS[3]};font-size:.82rem;'
        f'margin-top:{tokens.LEMON_SPACING[3]};">accessed {escape_text(str(accessed))}</div>'
        if accessed is not None
        else ""
    )
    meta = (
        f'<div style="margin-top:{tokens.LEMON_SPACING[2]};font-size:.88rem;">{link}</div>'
        if link
        else ""
    )
    return (
        f'<div class="lemon lemon-card" style="border:{tokens.LEMON_BORDER};'
        f'border-left:8px solid {_tone_color(data.get("tone"))};'
        f'border-radius:{tokens.LEMON_RADIUS};box-shadow:{tokens.LEMON_SHADOW};'
        f'background:{tokens.LEMON_SURFACE};padding:{tokens.LEMON_SPACING[4]};'
        f'color:{tokens.LEMON_INK};">'
        f'<div style="font-weight:800;">{escape_text(title_text)}</div>{meta}{quote_html}{accessed_html}</div>'
    )
