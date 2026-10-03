"""arXiv bulk-dataset mass path (SPR-07 M5b).

Mass arXiv ingest reads SPR-03's bulk metadata snapshot — the local
``arxiv-metadata-oai-snapshot.json`` (JSON-Lines) — via
``acquisition.arxiv.bulk``. It NEVER touches the arXiv export API: that
endpoint 429-banned the box's IP on the first run and is reserved for small
incremental pulls. This module maps records from the SPR-03 bulk reader
(``iter_bulk_candidates`` / ``bulk_candidates_from_path``) into PaperRecords.
It does not fetch PDFs.

Per-paper license is the snapshot's ``license`` field (the SAME rights anchor
the export Atom ``<license>`` carries). It is PER-RECORD and author-chosen: arXiv
papers carry CC variants (servable) OR the arXiv "non-exclusive license to
distribute" / nothing (gated). The license string is passed VERBATIM to the
chokepoint — no inline CC parsing here. The arXiv default-terms URI resolves to
gated through the same chokepoint that the CC URIs flow through (the chokepoint
composes the canonical CC table; the arXiv-specific default-terms row is
recognized as redistributable=False there, deny-by-defaulting it).

Identity: the arXiv id (version-stripped by the dedup ladder), with the
snapshot's ``doi`` taking precedence when present, so a bulk record collapses
with the same paper from CORE/S2 on a shared DOI.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import IO

from acquisition.arxiv.bulk import (
    bulk_candidates_from_path,
    iter_bulk_candidates,
)
from acquisition.arxiv.client import ArxivPaper
from acquisition.papers._pipeline import PaperRecord

ARXIV_BULK_SOURCE = "arxiv_bulk"
# The arXiv default-terms URI is recognized by the chokepoint's table (via the
# arXiv-specific row composed in licenses_core consumers) — but to be safe and
# self-contained, the bulk record passes whatever ``license`` the snapshot
# carried. When the snapshot carries the arXiv default-terms URI it gates; when
# it carries a CC URI it is servable. We make NO decision here.


def paper_to_record(paper: ArxivPaper) -> PaperRecord:
    """Map ONE bulk-discovered ``ArxivPaper`` into the shared PaperRecord.

    ``paper.license_uri`` is the snapshot's declared license — passed verbatim
    to classify(). ``metadata['doi']`` (when the snapshot carried one) drives
    cross-source dedup precedence above the arXiv id. This mapping does not
    fetch the PDF."""
    doi = None
    md = paper.metadata or {}
    if isinstance(md, dict) and md.get("doi"):
        doi = str(md["doi"]).strip() or None
    return PaperRecord(
        source=ARXIV_BULK_SOURCE,
        source_id=paper.arxiv_id,
        title=paper.title,
        license=paper.license_uri,  # verbatim -> classify(); never interpreted
        license_field="bulk metadata license",
        doi=doi,
        arxiv_id=paper.arxiv_id,
        abstract=paper.abstract or None,
        authors=tuple(paper.authors or ()),
        pdf_url=paper.pdf_url,
        has_servable_body=True,  # the PDF host serves the body (export-free fetch)
        legitimate_source=True,  # the open bulk dump is a legitimate source
        metadata={
            "categories": list(paper.categories),
            "version": paper.version,
            "published_at": (
                paper.published_at.isoformat() if paper.published_at else None
            ),
            "updated_at": paper.updated_at.isoformat() if paper.updated_at else None,
        },
    )


def iter_bulk_records(
    snapshot: IO[str],
    *,
    category: str | None = None,
    limit: int | None = None,
) -> Iterator[PaperRecord]:
    """Stream PaperRecords from an open JSON-Lines snapshot via the SPR-03 bulk
    reader. NO export-API request is ever made on this path — discovery is the
    local snapshot only."""
    for paper in iter_bulk_candidates(snapshot, category=category, limit=limit):
        yield paper_to_record(paper)


def bulk_records_from_path(
    snapshot_path: str,
    *,
    category: str | None = None,
    limit: int | None = None,
) -> list[PaperRecord]:
    """Open the snapshot at ``snapshot_path`` and materialize up to ``limit``
    PaperRecords. Composes the SPR-03 ``bulk_candidates_from_path`` (which
    streams line-by-line, bounded by ``limit``) — no export call, no full
    in-memory load beyond ``limit``."""
    papers = bulk_candidates_from_path(snapshot_path, category=category, limit=limit)
    return [paper_to_record(p) for p in papers]
