"""Open-access resolved-item → substrate ingest (SPR-03 M5).

Routes a resolved OA full-text item (a DOI + best-OA PDF URL + license
verdict) through the shared servable-book path
(``acquisition.books.ingest_servable_book`` -> substrate's deny-by-default
``register_book``), so the OA channel has the SAME single home for the legal
classification as arXiv. There is no parallel ingest path.

The flow mirrors ``acquisition.arxiv.adapter.ingest_paper_with_rights``:
resolve license -> build a ``license_basis`` audit string naming source +
license + how determined -> fetch PDF -> ingest with the resolved
content_class passed EXPLICITLY (so a gated item is an auditable decision,
not a silent None).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from processing.embedding.embed import EmbeddingProvider

from .licenses import LicenseResolution, license_basis_string

# OA full text from publisher/repository sources is peer-reviewed primary or
# repository copies; tier 2 matches the books default (higher signal than web,
# below an explicitly-curated tier-1 set). Caller can override.
DEFAULT_OA_SOURCE_TIER = 2

# arxiv_id -> not relevant; OA fetchers take a PDF URL.
PdfUrlFetcher = Callable[[str], bytes]


@dataclass(frozen=True)
class OAIngestResult:
    """What ``ingest_oa_item`` returns. ``servable_full_text`` is the derived
    deny-by-default answer; ``content_class`` + ``license_basis`` are echoed
    so a dry-run can report the decision without re-querying the substrate."""

    document_id: str
    content_class: str
    redistributable: bool
    servability: str
    servable_full_text: bool
    doi: Optional[str]
    license_uri: Optional[str]
    license_basis: str


def build_license_basis(
    resolution: LicenseResolution, *, source: str, how: str
) -> str:
    """Compose the OA ``license_basis`` audit string: it names the SOURCE +
    license + HOW the license was determined, e.g.
    "Unpaywall best-OA-location; CC BY (...); per best_oa_location.license".
    Wraps the shared ``license_basis_string`` (which states the license/why)
    with the source-provenance prefix."""
    return f"{source}; {how}; {license_basis_string(resolution)}"


def ingest_oa_item(
    *,
    investigation_id: str,
    doi: Optional[str],
    pdf_url: str,
    resolution: LicenseResolution,
    license_basis: str,
    source_uri: Optional[str] = None,
    pdf_bytes: Optional[bytes] = None,
    fetch_pdf: Optional[PdfUrlFetcher] = None,
    source_tier: int = DEFAULT_OA_SOURCE_TIER,
    db_path: Optional[str] = None,
    embedder: Optional[EmbeddingProvider] = None,
) -> OAIngestResult:
    """Ingest one resolved OA item's full text through the shared servable
    path, gated on ``resolution``.

    ``pdf_bytes`` short-circuits the fetch (CI passes fixture bytes). When
    omitted, ``fetch_pdf(pdf_url)`` is called. The resolved ``content_class``
    is passed EXPLICITLY so a gated item lands as an auditable decision.
    """
    from acquisition.books.adapter import ingest_servable_book

    if pdf_bytes is None:
        if fetch_pdf is None:
            raise ValueError("ingest_oa_item needs pdf_bytes or fetch_pdf")
        pdf_bytes = fetch_pdf(pdf_url)
    if not pdf_bytes:
        # An empty PDF would land a 0-word husk that looks like a rights
        # decision; surface the fetch failure instead.
        raise ValueError(
            f"empty PDF bytes for {doi or pdf_url} — fetch failed or the OA "
            "URL was a landing page, not a PDF"
        )

    result = ingest_servable_book(
        pdf_bytes,
        investigation_id=investigation_id,
        content_class=resolution.content_class,
        license_basis=license_basis,
        source_uri=source_uri or pdf_url,
        source_tier=int(source_tier),
        provenance=pdf_url,
        db_path=db_path,
        embedder=embedder,
    )

    return OAIngestResult(
        document_id=result.document_id,
        content_class=resolution.content_class,
        redistributable=resolution.redistributable,
        servability=result.servability,
        servable_full_text=result.servable_full_text,
        doi=doi,
        license_uri=resolution.license_uri,
        license_basis=license_basis,
    )
