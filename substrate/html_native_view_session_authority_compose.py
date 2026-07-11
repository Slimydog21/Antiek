"""HTML-native view session authority pack (pure).

pdf_view_authorized, pdf_primary, store_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.html_asset_view_session_compose import (
    HtmlAssetViewSessionCompose,
    HtmlAssetViewSessionComposeError,
    compose_html_asset_view_session,
)
from substrate.html_native_view_authority import (
    HtmlNativeViewAuthorityDecision,
    HtmlNativeViewAuthorityError,
    evaluate_html_native_view_authority,
)
from substrate.reading_research_html_parity_compose import (
    ReadingResearchHtmlParityCompose,
    ReadingResearchHtmlParityComposeError,
    compose_reading_research_html_parity,
)


class HtmlNativeViewSessionAuthorityComposeError(ValueError):
    """Fail-closed validation for HTML view session authority pack."""


@dataclass(frozen=True)
class HtmlNativeViewSessionAuthorityCompose:
    session_id: str
    asset_id: str
    session: HtmlAssetViewSessionCompose
    authority: HtmlNativeViewAuthorityDecision
    parity: ReadingResearchHtmlParityCompose
    pack_ready: bool
    pdf_view_authorized: bool
    pdf_primary: bool
    store_mutated: bool
    notes: tuple[str, ...]
    pack_authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "asset_id": self.asset_id,
            "session": self.session.to_dict(),
            "authority": self.authority.to_dict(),
            "parity": self.parity.to_dict(),
            "pack_ready": self.pack_ready,
            "pdf_view_authorized": False,
            "pdf_primary": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "pack_authority": (
                "html_native_view_session_authority_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HtmlNativeViewSessionAuthorityComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _derive_format(claimed: object | None) -> str:
    if claimed is None or (isinstance(claimed, str) and not claimed.strip()):
        return "unknown"
    f = str(claimed).strip().lower()
    if f in ("html", "pdf", "epub", "markdown"):
        return f
    return "unknown"


def compose_html_native_view_session_authority(
    *,
    session_id: object,
    asset_id: object,
    html_projection_sha: object,
    view_requested: object,
    twin_bound: object,
    operator_ack: object,
    twin_substrate_ready: object | None = None,
    claimed_format: object | None = None,
    reading: object | None = None,
    research: object | None = None,
) -> HtmlNativeViewSessionAuthorityCompose:
    """Session + authority + parity. Never PDF primary; never mutates store."""
    if not isinstance(operator_ack, bool):
        raise HtmlNativeViewSessionAuthorityComposeError(
            "operator_ack must be an explicit boolean"
        )
    sid = _require_nonempty(session_id, field="session_id")
    aid = _require_nonempty(asset_id, field="asset_id")

    notes: list[str] = [
        "pdf_view_authorized=false — HTML-native doctrine",
        "pdf_primary=false",
        "store_mutated=false",
    ]

    try:
        session = compose_html_asset_view_session(
            session_id=sid,
            asset_id=aid,
            html_projection_sha=html_projection_sha,
            view_requested=view_requested,
            twin_bound=twin_bound,
            twin_substrate_ready=twin_substrate_ready,
            claimed_format=claimed_format,
        )
    except HtmlAssetViewSessionComposeError as e:
        raise HtmlNativeViewSessionAuthorityComposeError(str(e)) from e
    notes.extend(f"[session] {n}" for n in session.notes)

    source_format = _derive_format(claimed_format)
    try:
        authority = evaluate_html_native_view_authority(
            asset_id=aid,
            asset_kind="research",
            source_format=source_format,
            html_projection_sha=html_projection_sha,
            prefer_html=True,
            allow_pdf_secondary=False,
        )
    except HtmlNativeViewAuthorityError as e:
        raise HtmlNativeViewSessionAuthorityComposeError(str(e)) from e
    notes.extend(f"[authority] {n}" for n in authority.notes)

    reading_in: dict[str, Any]
    research_in: dict[str, Any]
    if reading is not None:
        if not isinstance(reading, dict):
            raise HtmlNativeViewSessionAuthorityComposeError(
                "reading must be an object when set"
            )
        reading_in = dict(reading)
    else:
        reading_in = {
            "asset_id": aid,
            "asset_kind": "book",
            "source_format": source_format,
            "html_projection_sha": html_projection_sha,
            "prefer_html": True,
            "allow_pdf_secondary": False,
        }
    if research is not None:
        if not isinstance(research, dict):
            raise HtmlNativeViewSessionAuthorityComposeError(
                "research must be an object when set"
            )
        research_in = dict(research)
    else:
        research_in = {
            "asset_id": aid,
            "asset_kind": "research",
            "source_format": source_format,
            "html_projection_sha": html_projection_sha,
            "prefer_html": True,
            "allow_pdf_secondary": False,
        }

    try:
        parity = compose_reading_research_html_parity(
            reading=reading_in,
            research=research_in,
        )
    except ReadingResearchHtmlParityComposeError as e:
        raise HtmlNativeViewSessionAuthorityComposeError(str(e)) from e
    notes.extend(f"[parity] {n}" for n in parity.notes)

    pack_ready = (
        session.session_ready is True
        and authority.human_viewable_html is True
        and parity.pdf_primary is False
        and session.pdf_view_authorized is False
        and operator_ack is True
    )
    if pack_ready:
        notes.append(
            "pack_ready=true — HTML view session + authority + parity ready; "
            "still pure"
        )
    else:
        notes.append(
            "pack_ready=false — session, authority HTML, or operator_ack gate open"
        )

    if (
        session.pdf_view_authorized is not False
        or session.store_mutated is not False
        or parity.pdf_primary is not False
    ):
        raise HtmlNativeViewSessionAuthorityComposeError(
            "invariant: PDF must never be authorized as primary view"
        )

    notes.extend(
        (
            "pdf_view_authorized=false",
            "pdf_primary=false",
            "store_mutated=false",
        )
    )

    return HtmlNativeViewSessionAuthorityCompose(
        session_id=sid,
        asset_id=aid,
        session=session,
        authority=authority,
        parity=parity,
        pack_ready=pack_ready,
        pdf_view_authorized=False,
        pdf_primary=False,
        store_mutated=False,
        notes=tuple(notes),
        pack_authority="html_native_view_session_authority_compose_advisory",
    )


def format_html_native_view_session_authority_summary(
    c: HtmlNativeViewSessionAuthorityCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · session_ready={c.session.session_ready} · "
        f"human_viewable_html={c.authority.human_viewable_html} · "
        f"both_html_ready={c.parity.both_html_ready} · "
        f"pdf_view_authorized=false · pdf_primary=false · store_mutated=false"
    )


__all__ = [
    "HtmlNativeViewSessionAuthorityCompose",
    "HtmlNativeViewSessionAuthorityComposeError",
    "compose_html_native_view_session_authority",
    "format_html_native_view_session_authority_summary",
]
