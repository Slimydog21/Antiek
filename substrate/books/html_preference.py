"""HTML-native view preference gate for information assets.

Operator doctrine: human-viewable assets should be consumed as HTML, not PDF.
This pure gate decides the preferred view mode given readiness signals.

It does **not** convert PDFs or read projection stores — callers inject:
* ``html_ready`` — a ready, hash-verified HTML projection exists
* ``pdf_available`` — a PDF/binary source exists
* ``require_html`` — policy: refuse non-HTML human view

Returns a structured decision with honest notes (never invents readiness).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ViewMode = Literal["html", "pdf", "metadata_only", "unavailable"]


@dataclass(frozen=True)
class ViewPreference:
    mode: ViewMode
    preferred: bool
    """True when the chosen mode matches HTML-native doctrine preference."""
    reason: str
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "preferred": self.preferred,
            "reason": self.reason,
            "notes": list(self.notes),
        }


def _as_bool(value: object, *, name: str) -> bool:
    """Strict bool: only True/False accepted (reject truthy strings like 'false')."""
    if isinstance(value, bool):
        return value
    raise TypeError(f"{name} must be bool, got {type(value).__name__}")


def prefer_html_view(
    *,
    html_ready: bool,
    pdf_available: bool = False,
    require_html: bool = True,
    asset_id: str = "",
) -> ViewPreference:
    """Choose view mode for an asset under HTML-native policy.

    Precedence:
    1. Ready HTML → always prefer ``html``
    2. No HTML, PDF available, require_html=False → ``pdf`` with honest note
    3. No HTML, PDF available, require_html=True → ``metadata_only`` (refuse PDF body)
    4. Nothing viewable → ``unavailable``
    """
    html_ready = _as_bool(html_ready, name="html_ready")
    pdf_available = _as_bool(pdf_available, name="pdf_available")
    require_html = _as_bool(require_html, name="require_html")

    notes: list[str] = []
    if asset_id:
        notes.append(f"asset_id={asset_id}")

    if html_ready:
        notes.append("ready HTML projection available — HTML-native path")
        return ViewPreference(
            mode="html",
            preferred=True,
            reason="html_ready",
            notes=tuple(notes),
        )

    notes.append("no ready HTML projection")
    if pdf_available:
        if require_html:
            notes.append(
                "PDF exists but require_html=true — refuse PDF body; metadata only"
            )
            return ViewPreference(
                mode="metadata_only",
                preferred=False,
                reason="pdf_blocked_by_html_policy",
                notes=tuple(notes),
            )
        notes.append(
            "PDF fallback permitted (require_html=false) — not HTML-native preferred"
        )
        return ViewPreference(
            mode="pdf",
            preferred=False,
            reason="pdf_fallback",
            notes=tuple(notes),
        )

    notes.append("no HTML and no PDF — nothing human-viewable")
    return ViewPreference(
        mode="unavailable",
        preferred=False,
        reason="no_viewable_representation",
        notes=tuple(notes),
    )


__all__ = ["ViewMode", "ViewPreference", "prefer_html_view"]
