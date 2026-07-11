"""Source publication DR attach + citation + quality pack (pure).

remote_fetched, pdf_view_authorized, store_mutated, live_dispatch always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.deep_research_quality_budget_gate_compose import (
    DeepResearchQualityBudgetGateCompose,
    DeepResearchQualityBudgetGateComposeError,
    compose_deep_research_quality_budget_gate,
)
from substrate.deep_research_source_citation_pack import (
    DeepResearchSourceCitationPack,
    DeepResearchSourceCitationPackError,
    build_deep_research_source_citation_pack,
)
from substrate.html_native_source_attach_compose import (
    HtmlNativeSourceAttachCompose,
    HtmlNativeSourceAttachComposeError,
    compose_html_native_source_attach,
)


class SourcePublicationDrAttachQualityComposeError(ValueError):
    """Fail-closed validation for source publication DR attach quality pack."""


@dataclass(frozen=True)
class SourcePublicationDrAttachQualityCompose:
    session_id: str
    parent_asset_id: str
    attach: HtmlNativeSourceAttachCompose
    citation_pack: DeepResearchSourceCitationPack
    quality_gate: DeepResearchQualityBudgetGateCompose
    pack_ready: bool
    remote_fetched: bool
    pdf_view_authorized: bool
    store_mutated: bool
    live_dispatch_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "attach": self.attach.to_dict(),
            "citation_pack": self.citation_pack.to_dict(),
            "quality_gate": self.quality_gate.to_dict(),
            "pack_ready": self.pack_ready,
            "remote_fetched": False,
            "pdf_view_authorized": False,
            "store_mutated": False,
            "live_dispatch_authorized": False,
            "notes": list(self.notes),
            "authority": (
                "source_publication_dr_attach_quality_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourcePublicationDrAttachQualityComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _derive_citations(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in sources:
        sid = str(s.get("source_id", "")).strip()
        out.append(
            {
                "citation_id": f"cite-{sid}",
                "family": s.get("family"),
                "title": s.get("title"),
                "external_id": s.get("external_id"),
                "url": s.get("url"),
            }
        )
    return out


def compose_source_publication_dr_attach_quality(
    *,
    session_id: object,
    parent_asset_id: object,
    requested_families: object,
    sources: object,
    quality_overall: object,
    would_exceed: object,
    operator_ack: object,
    citations: object | None = None,
    derive_citations_from_sources: object | None = None,
    quality_floor: object | None = None,
    operator_override: object | None = None,
) -> SourcePublicationDrAttachQualityCompose:
    """arxiv/substack attach + citations + quality. Never fetches/dispatches."""
    if not isinstance(operator_ack, bool):
        raise SourcePublicationDrAttachQualityComposeError(
            "operator_ack must be an explicit boolean"
        )
    sid = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")

    notes: list[str] = [
        "remote_fetched=false — no live arxiv/substack scrape",
        "pdf_view_authorized=false — HTML-native only",
        "store_mutated=false",
        "live_dispatch_authorized=false — quality DR readiness pack only",
    ]

    try:
        attach = compose_html_native_source_attach(
            session_id=sid,
            parent_asset_id=parent,
            requested_families=requested_families,
            sources=sources,
            operator_ack=operator_ack,
        )
    except HtmlNativeSourceAttachComposeError as e:
        raise SourcePublicationDrAttachQualityComposeError(str(e)) from e
    notes.extend(f"[attach] {n}" for n in attach.notes)

    derive = (
        True
        if derive_citations_from_sources is None
        else derive_citations_from_sources
    )
    if not isinstance(derive, bool):
        raise SourcePublicationDrAttachQualityComposeError(
            "derive_citations_from_sources must be boolean when set"
        )

    if citations is not None:
        if not isinstance(citations, list):
            raise SourcePublicationDrAttachQualityComposeError(
                "citations must be an array when set"
            )
        cite_list = citations
        notes.append(f"citations={len(cite_list)} caller-supplied")
    elif derive:
        if not isinstance(sources, list):
            raise SourcePublicationDrAttachQualityComposeError(
                "sources must be an array"
            )
        cite_list = _derive_citations(
            [s for s in sources if isinstance(s, dict)]
        )
        notes.append(
            f"citations={len(cite_list)} derived from HTML source refs "
            "(no invent titles)"
        )
    else:
        cite_list = []
        notes.append("citations empty — neither supplied nor derived")

    try:
        citation_pack = build_deep_research_source_citation_pack(
            session_id=sid,
            requested_families=requested_families,
            citations=cite_list,
            filter_to_selected_families=True,
        )
    except DeepResearchSourceCitationPackError as e:
        raise SourcePublicationDrAttachQualityComposeError(str(e)) from e
    notes.extend(f"[citation] {n}" for n in citation_pack.notes)

    try:
        quality_gate = compose_deep_research_quality_budget_gate(
            session_id=sid,
            quality_overall=quality_overall,
            would_exceed=would_exceed,
            operator_ack=operator_ack,
            quality_floor=quality_floor,
            operator_override=operator_override,
            citation_pack_ready=citation_pack.pack_ready,
        )
    except DeepResearchQualityBudgetGateComposeError as e:
        raise SourcePublicationDrAttachQualityComposeError(str(e)) from e
    notes.extend(f"[quality] {n}" for n in quality_gate.notes)

    pack_ready = (
        attach.attach_ready is True
        and citation_pack.pack_ready is True
        and quality_gate.gate_ready is True
        and operator_ack is True
    )
    if pack_ready:
        notes.append(
            "pack_ready=true — source attach + citations + quality gate ready; "
            "still pure"
        )
    else:
        notes.append(
            "pack_ready=false — attach, citation, quality, or operator_ack "
            "gate open"
        )

    if (
        attach.remote_fetched is not False
        or attach.pdf_view_authorized is not False
        or attach.store_mutated is not False
        or citation_pack.remote_fetched is not False
        or quality_gate.live_dispatch_authorized is not False
    ):
        raise SourcePublicationDrAttachQualityComposeError(
            "invariant: honesty flags must remain false"
        )

    notes.extend(
        (
            "remote_fetched=false",
            "pdf_view_authorized=false",
            "store_mutated=false",
            "live_dispatch_authorized=false",
        )
    )

    return SourcePublicationDrAttachQualityCompose(
        session_id=sid,
        parent_asset_id=parent,
        attach=attach,
        citation_pack=citation_pack,
        quality_gate=quality_gate,
        pack_ready=pack_ready,
        remote_fetched=False,
        pdf_view_authorized=False,
        store_mutated=False,
        live_dispatch_authorized=False,
        notes=tuple(notes),
        authority="source_publication_dr_attach_quality_compose_advisory",
    )


def format_source_publication_dr_attach_quality_summary(
    c: SourcePublicationDrAttachQualityCompose,
) -> str:
    return (
        f"pack_ready={c.pack_ready} · attach={c.attach.source_count} · "
        f"citations={c.citation_pack.citation_count} · "
        f"html_ready={c.attach.html_ready_count} · "
        f"remote_fetched=false · pdf_view_authorized=false · "
        f"live_dispatch_authorized=false"
    )


__all__ = [
    "SourcePublicationDrAttachQualityCompose",
    "SourcePublicationDrAttachQualityComposeError",
    "compose_source_publication_dr_attach_quality",
    "format_source_publication_dr_attach_quality_summary",
]
