"""Book acquisition path — PDF → markdown → graph.

Sprint 10 day 3-4. Requires the ``[pdf]`` extra:
``pip install -e '.[pdf]'`` to pick up ``pypdf``.
"""

from .adapter import (
    IngestBookResult,
    IngestServableBookResult,
    book_doc_id,
    ingest_pdf,
    ingest_servable_book,
)

# SPR-06 Wave-2 PD connectors + their shared spine glue. Imported here so the
# "connectors importable/registered" gate is a single package import and SPR-09
# can rotate over the registry.
from .pd_connector_base import (
    BookCandidate,
    FetchError,
    ThrottledFetcher,
    classify_and_ingest,
)
from .pd_connector_base import (
    IngestOutcome as PdConnectorIngestOutcome,
)
from .public_domain import (
    IngestOutcome,
    PublicDomainWork,
    SourceClient,
    SourceError,
    archive_candidate,
    gutenberg_candidates,
    ingest_work,
    strip_gutenberg_boilerplate,
    text_to_pdf,
)
from .reader import PdfPage, ReadResult, read_pdf

__all__ = [
    "IngestBookResult",
    "IngestServableBookResult",
    "IngestOutcome",
    "PdfPage",
    "PublicDomainWork",
    "ReadResult",
    "SourceClient",
    "SourceError",
    "archive_candidate",
    "book_doc_id",
    "gutenberg_candidates",
    "ingest_pdf",
    "ingest_servable_book",
    "ingest_work",
    "read_pdf",
    "strip_gutenberg_boilerplate",
    "text_to_pdf",
    # SPR-06
    "BookCandidate",
    "FetchError",
    "PdConnectorIngestOutcome",
    "ThrottledFetcher",
    "classify_and_ingest",
]
