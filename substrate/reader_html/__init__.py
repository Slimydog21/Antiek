"""Reader-HTML sidecar substrate (doc→HTML S1).

``store_reader_html`` is the ONLY write path for the ``document_reader_html``
sidecar; ``serve_reader_html`` is its fail-closed serve gate. The trust
contract mirrors ``substrate/books/html_sanitizer``: a body may be emitted
AS HTML only when the sidecar row carries the exact current
``SANITIZER_VERSION``, stamped at the same write that ran
``sanitize_book_html``.
"""

from __future__ import annotations

from .store import (
    MAX_READER_HTML_CHARS,
    ReaderHtmlResult,
    serve_reader_html,
    store_reader_html,
)

__all__ = [
    "MAX_READER_HTML_CHARS",
    "ReaderHtmlResult",
    "serve_reader_html",
    "store_reader_html",
]
