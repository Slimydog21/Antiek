"""arXiv acquisition path — first real corpus channel for Antiek.

Surface:

- ``client.search(query=..., max_results=...)`` — query the arXiv Atom
  API; return a list of ``ArxivPaper`` records.
- ``client.fetch_by_id(arxiv_id)`` — fetch a single paper by id.
- ``adapter.ingest_paper(paper, *, investigation_id, ...)`` — emit
  ``document.loaded`` for the abstract, chunk it via
  ``processing.chunking``, insert into ``substrate.graph`` (document
  row + chunks + nodes). Returns ``IngestResult`` with the assigned
  ``document_id`` + chunk ids.

Abstract-only ingestion is ``ingest_paper``. SPR-02 adds the rights
layer: ``ingest_paper_with_rights`` resolves the paper's declared license
(``acquisition.arxiv.licenses``) and routes the full-text PDF through the
shared servable-book gate; ``ArxivThrottle`` provides the cross-process
conservative throttle + 429 ban sentinel.
"""

from .adapter import (
    IngestPaperWithRightsResult,
    IngestResult,
    arxiv_doc_id,
    ingest_paper,
    ingest_paper_with_rights,
)
from .bulk import (
    bulk_candidates_from_path,
    fetch_bulk_pdf,
    iter_bulk_candidates,
    record_to_paper,
)
from .client import ArxivPaper, fetch_by_id, search
from .licenses import LicenseResolution, license_basis_string, resolve_license
from .throttle import ArxivBanned, ArxivThrottle

__all__ = [
    "ArxivBanned",
    "ArxivPaper",
    "ArxivThrottle",
    "IngestPaperWithRightsResult",
    "IngestResult",
    "LicenseResolution",
    "arxiv_doc_id",
    "bulk_candidates_from_path",
    "fetch_by_id",
    "fetch_bulk_pdf",
    "ingest_paper",
    "ingest_paper_with_rights",
    "iter_bulk_candidates",
    "license_basis_string",
    "record_to_paper",
    "resolve_license",
    "search",
]
