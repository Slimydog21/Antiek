"""HTML-native view authority for any information asset (pure).

Every human-viewable asset uses HTML as primary surface. Never invents a
ready HTML projection sha. PDF is never primary human view.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

AssetKind = Literal["book", "research", "twin", "analysis", "paper", "other"]
SourceFormat = Literal["html", "pdf", "epub", "markdown", "unknown"]

VALID_KINDS = frozenset({"book", "research", "twin", "analysis", "paper", "other"})
VALID_FORMATS = frozenset({"html", "pdf", "epub", "markdown", "unknown"})


class HtmlNativeViewAuthorityError(ValueError):
    """Fail-closed validation for HTML view authority."""


@dataclass(frozen=True)
class HtmlNativeViewAuthorityDecision:
    asset_id: str
    asset_kind: AssetKind
    human_viewable_html: bool
    primary_format: Literal["html", "unavailable"]
    pdf_secondary_allowed: bool
    html_projection_sha: str | None
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "asset_kind": self.asset_kind,
            "human_viewable_html": self.human_viewable_html,
            "primary_format": self.primary_format,
            "pdf_secondary_allowed": self.pdf_secondary_allowed,
            "html_projection_sha": self.html_projection_sha,
            "notes": list(self.notes),
            "authority": "html_native_view_authority_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HtmlNativeViewAuthorityError(f"{field} must be a non-empty string")
    return value.strip()


def evaluate_html_native_view_authority(
    *,
    asset_id: object,
    asset_kind: object,
    source_format: object,
    html_projection_sha: object | None = None,
    prefer_html: object = True,
    allow_pdf_secondary: object = True,
) -> HtmlNativeViewAuthorityDecision:
    """Decide HTML-native human view authority. Never invents ready projection."""
    aid = _require_nonempty(asset_id, field="asset_id")
    if not isinstance(asset_kind, str) or asset_kind not in VALID_KINDS:
        raise HtmlNativeViewAuthorityError(
            "asset_kind must be book|research|twin|analysis|paper|other"
        )
    if not isinstance(source_format, str) or source_format not in VALID_FORMATS:
        raise HtmlNativeViewAuthorityError(
            "source_format must be html|pdf|epub|markdown|unknown"
        )
    if not isinstance(prefer_html, bool):
        raise HtmlNativeViewAuthorityError("prefer_html must be an explicit boolean")
    if not isinstance(allow_pdf_secondary, bool):
        raise HtmlNativeViewAuthorityError(
            "allow_pdf_secondary must be an explicit boolean"
        )

    notes: list[str] = [
        "HTML is the primary human-viewable surface (Antiek doctrine)",
        "PDF is never primary human view under this authority",
    ]

    html_sha: str | None = None
    if html_projection_sha is not None:
        if not isinstance(html_projection_sha, str):
            raise HtmlNativeViewAuthorityError(
                "html_projection_sha must be string or null"
            )
        t = html_projection_sha.strip()
        html_sha = t or None

    if source_format == "pdf":
        notes.append(
            "source is pdf — requires HTML projection before human primary view"
        )
    if source_format == "html" and not html_sha:
        notes.append(
            "source_format=html but html_projection_sha unknown — not inventing ready projection"
        )

    human_viewable_html = False
    primary_format: Literal["html", "unavailable"] = "unavailable"

    if not prefer_html:
        notes.append("prefer_html=false — human_viewable_html=false (operator override)")
    elif not html_sha:
        notes.append(
            "html_projection_sha missing — human_viewable_html=false (no invent ready)"
        )
    else:
        human_viewable_html = True
        primary_format = "html"
        notes.append(f"HTML projection ready sha={html_sha[:16]}…")

    pdf_secondary_allowed = allow_pdf_secondary and source_format in ("pdf", "epub")
    if pdf_secondary_allowed and not human_viewable_html:
        notes.append(
            "pdf/epub secondary download may be offered; primary human view still "
            "unavailable until HTML ready"
        )

    return HtmlNativeViewAuthorityDecision(
        asset_id=aid,
        asset_kind=asset_kind,  # type: ignore[arg-type]
        human_viewable_html=human_viewable_html,
        primary_format=primary_format,
        pdf_secondary_allowed=pdf_secondary_allowed,
        html_projection_sha=html_sha,
        notes=tuple(notes),
        authority="html_native_view_authority_advisory",
    )


__all__ = [
    "HtmlNativeViewAuthorityDecision",
    "HtmlNativeViewAuthorityError",
    "evaluate_html_native_view_authority",
]
