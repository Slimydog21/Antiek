"""Book acquisition path — PDF → markdown → graph.

Sprint 10 day 3-4. Requires the ``[pdf]`` extra:
``pip install -e '.[pdf]'`` to pick up ``pypdf``.
"""

from .adapter import IngestBookResult, book_doc_id, ingest_pdf
from .reader import PdfPage, ReadResult, read_pdf

__all__ = [
    "IngestBookResult",
    "PdfPage",
    "ReadResult",
    "book_doc_id",
    "ingest_pdf",
    "read_pdf",
]
