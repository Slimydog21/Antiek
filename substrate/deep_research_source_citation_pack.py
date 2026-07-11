"""Deep research source citation pack (pure, advisory).

Builds a citation pack from operator-supplied citation records and selected
publication families (arxiv, substack, …). remote_fetched always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.source_publication_registry import (
    SourcePublicationRegistryError,
    SourceSelectionPack,
    select_publication_sources,
)

VALID_FAMILIES = frozenset({"arxiv", "substack", "openalex", "web", "custom"})


class DeepResearchSourceCitationPackError(ValueError):
    """Fail-closed validation for deep research citation pack."""


@dataclass(frozen=True)
class CitationRecord:
    citation_id: str
    family: str
    title: str
    external_id: str | None
    url: str | None
    year: int | None
    authors: str | None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "citation_id": self.citation_id,
            "family": self.family,
            "title": self.title,
        }
        if self.external_id is not None:
            out["external_id"] = self.external_id
        if self.url is not None:
            out["url"] = self.url
        if self.year is not None:
            out["year"] = self.year
        if self.authors is not None:
            out["authors"] = self.authors
        return out


@dataclass(frozen=True)
class DeepResearchSourceCitationPack:
    session_id: str
    selection: SourceSelectionPack
    citations: tuple[CitationRecord, ...]
    citation_count: int
    families_present: tuple[str, ...]
    pack_ready: bool
    remote_fetched: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "selection": self.selection.to_dict(),
            "citations": [c.to_dict() for c in self.citations],
            "citation_count": self.citation_count,
            "families_present": list(self.families_present),
            "pack_ready": self.pack_ready,
            "remote_fetched": False,
            "notes": list(self.notes),
            "authority": "deep_research_source_citation_pack_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DeepResearchSourceCitationPackError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def build_deep_research_source_citation_pack(
    *,
    session_id: object,
    requested_families: object,
    citations: object,
    filter_to_selected_families: object = True,
) -> DeepResearchSourceCitationPack:
    """Build citation pack. Never invents rows; never remote-fetches."""
    sid = _require_nonempty(session_id, field="session_id")
    if not isinstance(requested_families, list):
        raise DeepResearchSourceCitationPackError(
            "requested_families must be an array"
        )
    if not isinstance(citations, list):
        raise DeepResearchSourceCitationPackError("citations must be an array")
    if not isinstance(filter_to_selected_families, bool):
        raise DeepResearchSourceCitationPackError(
            "filter_to_selected_families must be boolean when set"
        )

    notes: list[str] = [
        "remote_fetched=false — citation pack is selection + caller records only",
        "citation rows are operator-supplied only (no invent / no scrape)",
    ]

    try:
        selection = select_publication_sources(
            requested_families=requested_families,
            enabled_only=True,
        )
    except SourcePublicationRegistryError as e:
        raise DeepResearchSourceCitationPackError(str(e)) from e

    notes.extend(selection.notes)
    notes.append(
        f"selected_families={','.join(selection.families) or '(none)'}"
    )
    selected_family_set = set(selection.families)

    if selection.fetched is not False:
        raise DeepResearchSourceCitationPackError(
            "selection.fetched must be false"
        )

    seen: set[str] = set()
    accepted: list[CitationRecord] = []
    families_present: set[str] = set()

    for i, c in enumerate(citations):
        if not isinstance(c, dict):
            raise DeepResearchSourceCitationPackError(
                f"citations[{i}] must be an object"
            )
        cid = _require_nonempty(
            c.get("citation_id"), field=f"citations[{i}].citation_id"
        )
        if cid in seen:
            raise DeepResearchSourceCitationPackError(
                f"duplicate citation_id: {cid}"
            )
        seen.add(cid)

        family = c.get("family")
        if family not in VALID_FAMILIES:
            raise DeepResearchSourceCitationPackError(
                f"citations[{i}].family must be arxiv|substack|openalex|web|custom"
            )
        if filter_to_selected_families and selected_family_set and family not in selected_family_set:
            notes.append(
                f"citations[{i}] family={family} filtered out (not in selected families)"
            )
            continue
        if filter_to_selected_families and not selected_family_set:
            notes.append(
                f"citations[{i}] dropped — no families selected "
                "(filter_to_selected_families)"
            )
            continue

        title = _require_nonempty(c.get("title"), field=f"citations[{i}].title")
        external_id = c.get("external_id")
        if external_id is not None:
            external_id = _require_nonempty(
                external_id, field=f"citations[{i}].external_id"
            )
        url = c.get("url")
        if url is not None:
            url = _require_nonempty(url, field=f"citations[{i}].url")
            if not (
                url.lower().startswith("http://")
                or url.lower().startswith("https://")
                or url.startswith("arxiv:")
            ):
                raise DeepResearchSourceCitationPackError(
                    f"citations[{i}].url must be http(s) URL or arxiv: id when set"
                )
        year = c.get("year")
        if year is not None:
            if (
                isinstance(year, bool)
                or not isinstance(year, int)
                or year < 1000
                or year > 3000
            ):
                raise DeepResearchSourceCitationPackError(
                    f"citations[{i}].year must be integer year in [1000,3000] when set"
                )
        authors = c.get("authors")
        if authors is not None:
            if not isinstance(authors, str) or not authors.strip():
                raise DeepResearchSourceCitationPackError(
                    f"citations[{i}].authors must be non-empty string when set"
                )
            authors = authors.strip()

        accepted.append(
            CitationRecord(
                citation_id=cid,
                family=family,  # type: ignore[arg-type]
                title=title,
                external_id=external_id if external_id is not None else None,
                url=url if url is not None else None,
                year=year if year is not None else None,
                authors=authors if authors is not None else None,
            )
        )
        families_present.add(family)  # type: ignore[arg-type]

    if len(citations) == 0:
        notes.append("no citations supplied — empty pack (no invent citations)")
    else:
        notes.append(
            f"citations_accepted={len(accepted)} of {len(citations)} supplied"
        )

    pack_ready = len(selection.families) >= 1 and len(accepted) >= 1
    if not pack_ready:
        if len(selection.families) < 1:
            notes.append(
                "pack_ready=false — need ≥1 selected publication family"
            )
        else:
            notes.append("pack_ready=false — need ≥1 accepted citation")
    else:
        notes.append(
            f"pack_ready=true · citations={len(accepted)} · "
            f"families={','.join(sorted(families_present))}"
        )
    notes.append("remote_fetched=false")

    return DeepResearchSourceCitationPack(
        session_id=sid,
        selection=selection,
        citations=tuple(accepted),
        citation_count=len(accepted),
        families_present=tuple(sorted(families_present)),
        pack_ready=pack_ready,
        remote_fetched=False,
        notes=tuple(notes),
        authority="deep_research_source_citation_pack_advisory",
    )


__all__ = [
    "CitationRecord",
    "DeepResearchSourceCitationPack",
    "DeepResearchSourceCitationPackError",
    "build_deep_research_source_citation_pack",
]
