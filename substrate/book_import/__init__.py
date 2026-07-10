"""Book import — the real epub → Antiek-HTML conversion engine (SPR-02).

The legacy import-funnel PRs (#490/#492/#493) receipted a conversion that
never existed; this package IS the engine. Pipeline:

    read_epub (fail-closed OCF/zip reader, stdlib only)
      → convert_epub_to_antiek_html (structure-preserving, sanitized via the
        SPR-01 floor — output cannot contain executable HTML)
      → publish_converted_book (sanitize-on-write into the EXISTING books
        substrate: insert_document + the native chunker + register_book's
        rights chokepoint, deny-by-default gated)

Boundaries (non-negotiable, see module docstrings + WIRING.md):

- Input is a LOCAL, legally-held file — never a URL fetch, never a payment.
- DRM is refused (``DrmLockedError``), never bypassed.
- Conversion never upgrades rights: ``content_class`` defaults to the gated
  class; the operator's declaration is passed through explicitly.
- Every failure is a typed :class:`~substrate.book_import.errors.BookImportError`;
  a hollow/hostile input publishes NOTHING.
"""

from __future__ import annotations

from .convert import (
    CONVERTER_VERSION,
    ConvertedBook,
    TocHeading,
    convert_epub_to_antiek_html,
)
from .epub import DEFAULT_LIMITS, EpubBook, EpubChapter, EpubLimits, read_epub
from .errors import (
    BookImportError,
    DrmLockedError,
    ExternalEntityBlockedError,
    MalformedEpubError,
    MissingPublishedChunksError,
    NotAnEpubError,
    NoTextContentError,
    RepublishRightsChangeError,
    StoredBodyMismatchError,
    UnsafeArchivePathError,
    ZipBombSuspectedError,
)
from .publish import (
    BOOK_IMPORT_SOURCE_TIER,
    CHAPTER_PAGINATION_SCHEME,
    PublishedBookImport,
    publish_converted_book,
)

__all__ = [
    "BOOK_IMPORT_SOURCE_TIER",
    "CHAPTER_PAGINATION_SCHEME",
    "CONVERTER_VERSION",
    "DEFAULT_LIMITS",
    "BookImportError",
    "ConvertedBook",
    "DrmLockedError",
    "EpubBook",
    "EpubChapter",
    "EpubLimits",
    "ExternalEntityBlockedError",
    "MalformedEpubError",
    "MissingPublishedChunksError",
    "NoTextContentError",
    "NotAnEpubError",
    "PublishedBookImport",
    "RepublishRightsChangeError",
    "StoredBodyMismatchError",
    "TocHeading",
    "UnsafeArchivePathError",
    "ZipBombSuspectedError",
    "convert_epub_to_antiek_html",
    "publish_converted_book",
    "read_epub",
]
