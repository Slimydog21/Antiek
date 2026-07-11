"""Reading ↔ research HTML parity compose (pure, advisory).

Reading and research share HTML-native view path. pdf_primary always False.
Never invents projection shas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.html_native_view_authority import (
    HtmlNativeViewAuthorityDecision,
    HtmlNativeViewAuthorityError,
    evaluate_html_native_view_authority,
)


class ReadingResearchHtmlParityComposeError(ValueError):
    """Fail-closed validation for reading/research HTML parity."""


@dataclass(frozen=True)
class ReadingResearchHtmlParityCompose:
    reading: HtmlNativeViewAuthorityDecision
    research: HtmlNativeViewAuthorityDecision
    both_html_ready: bool
    primary_format_aligned: bool
    parity_ready: bool
    pdf_primary: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "reading": self.reading.to_dict(),
            "research": self.research.to_dict(),
            "both_html_ready": self.both_html_ready,
            "primary_format_aligned": self.primary_format_aligned,
            "parity_ready": self.parity_ready,
            "pdf_primary": False,
            "notes": list(self.notes),
            "authority": "reading_research_html_parity_compose_advisory",
        }


def compose_reading_research_html_parity(
    *,
    reading: object,
    research: object,
) -> ReadingResearchHtmlParityCompose:
    """Compose dual-mode HTML authority into a parity snapshot."""
    if not isinstance(reading, dict):
        raise ReadingResearchHtmlParityComposeError("reading must be an object")
    if not isinstance(research, dict):
        raise ReadingResearchHtmlParityComposeError("research must be an object")

    try:
        reading_d = evaluate_html_native_view_authority(
            asset_id=reading.get("asset_id"),
            asset_kind=reading.get("asset_kind"),
            source_format=reading.get("source_format"),
            html_projection_sha=reading.get("html_projection_sha"),
            prefer_html=reading.get("prefer_html", True),
            allow_pdf_secondary=reading.get("allow_pdf_secondary", True),
        )
        research_d = evaluate_html_native_view_authority(
            asset_id=research.get("asset_id"),
            asset_kind=research.get("asset_kind"),
            source_format=research.get("source_format"),
            html_projection_sha=research.get("html_projection_sha"),
            prefer_html=research.get("prefer_html", True),
            allow_pdf_secondary=research.get("allow_pdf_secondary", True),
        )
    except HtmlNativeViewAuthorityError as e:
        raise ReadingResearchHtmlParityComposeError(str(e)) from e

    notes: list[str] = [
        "pdf_primary=false — HTML doctrine; PDF never primary",
        "projection shas are caller-supplied only (no invent)",
    ]

    if (
        reading_d.primary_format == "html"
        and research_d.primary_format == "html"
    ):
        notes.append("both modes primary_format=html")
    else:
        notes.append(
            f"primary_format reading={reading_d.primary_format} "
            f"research={research_d.primary_format}"
        )

    both_html_ready = (
        reading_d.human_viewable_html and research_d.human_viewable_html
    )
    primary_format_aligned = (
        reading_d.primary_format == research_d.primary_format
    )

    parity_ready = False
    if both_html_ready and primary_format_aligned:
        r_sha = reading_d.html_projection_sha
        s_sha = research_d.html_projection_sha
        if r_sha and s_sha and r_sha == s_sha:
            parity_ready = True
            notes.append(
                "parity_ready=true — both HTML ready with matching projection sha"
            )
        elif r_sha and s_sha and r_sha != s_sha:
            notes.append(
                "parity_ready=false — both HTML ready but projection sha differs "
                "(no invent merge)"
            )
        else:
            notes.append(
                "parity_ready=false — human_viewable_html true without both "
                "non-empty shas"
            )
    elif (
        not reading_d.human_viewable_html
        and not research_d.human_viewable_html
        and primary_format_aligned
    ):
        notes.append(
            "parity_ready=false — both unavailable (aligned but not viewable; "
            "no invent sha)"
        )
    else:
        notes.append(
            "parity_ready=false — modes not both HTML-ready or formats diverge"
        )

    notes.append("pdf_primary=false")

    return ReadingResearchHtmlParityCompose(
        reading=reading_d,
        research=research_d,
        both_html_ready=both_html_ready,
        primary_format_aligned=primary_format_aligned,
        parity_ready=parity_ready,
        pdf_primary=False,
        notes=tuple(notes),
        authority="reading_research_html_parity_compose_advisory",
    )


__all__ = [
    "ReadingResearchHtmlParityCompose",
    "ReadingResearchHtmlParityComposeError",
    "compose_reading_research_html_parity",
]
