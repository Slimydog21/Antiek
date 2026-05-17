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

Sprint 10 day 2-3 scope: abstract-only ingestion. Full-text PDF
fetch + extraction lives in ``acquisition/books/`` (day 3-4).
"""

from .adapter import IngestResult, arxiv_doc_id, ingest_paper
from .client import ArxivPaper, fetch_by_id, search

__all__ = [
    "ArxivPaper",
    "IngestResult",
    "arxiv_doc_id",
    "fetch_by_id",
    "ingest_paper",
    "search",
]
