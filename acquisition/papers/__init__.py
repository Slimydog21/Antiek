"""More paper aggregators (SPR-07): CORE, Semantic Scholar, bioRxiv/medRxiv,
PLOS, and the arXiv bulk-dataset mass path.

Every connector here is a thin *consumer* of the Wave-1 foundations — it does
NOT own dedup, license semantics, the staging write, or the throttle:

  * rights:    ``acquisition.licenses_core.classify`` (the ONE chokepoint —
               every content_class decision routes through it; no connector
               assigns a class by any other route);
  * dedup:     ``substrate.dedup`` (DOI > arXiv-id > source-id precedence) via
               ``acquisition.corpus_quality.CandidateRef``;
  * throttle:  ``substrate.source_throttle.SourceThrottle`` + the shared
               ``acquisition.openaccess.pdf_detect.assert_pdf`` PDF-vs-HTML gate;
  * ingest:    the servable path ``acquisition.books.adapter.ingest_servable_book``
               (gated/servable both flow through it; the resolved content_class +
               license_basis are passed EXPLICITLY).

The shared discovery→classify→stage pipeline lives in
:mod:`acquisition.papers._pipeline`; each source module supplies only its own
record shape + discovery + the license string it reads per record. The CORE
connector is :mod:`acquisition.papers.core`.
"""

from __future__ import annotations

from ._pipeline import (
    PaperClassification,
    PaperIngestResult,
    PaperRecord,
    classify_paper,
    ingest_servable_paper,
    paper_candidate_ref,
)

__all__ = [
    "PaperRecord",
    "PaperClassification",
    "PaperIngestResult",
    "classify_paper",
    "paper_candidate_ref",
    "ingest_servable_paper",
]
