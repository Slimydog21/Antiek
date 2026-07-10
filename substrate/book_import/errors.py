"""Typed, fail-closed failure vocabulary for the book-import engine (SPR-02).

Every failure mode of the epub → Antiek-HTML pipeline maps to exactly one
exception class carrying a stable machine-readable ``reason`` code. The
contract the parent spec demands: a hostile or unreadable input NEVER
produces a silent empty book or a fabricated body — it raises one of these,
and nothing is published.

``reason`` codes are API surface (a future ``/books/import/conversion-job``
route returns them verbatim); do not rename without a deprecation note.
"""

from __future__ import annotations

from typing import ClassVar


class BookImportError(Exception):
    """Base of every typed book-import failure. ``reason`` is the stable
    machine-readable code; the exception message carries the human detail."""

    reason: ClassVar[str] = "book_import_error"

    def __init__(self, detail: str) -> None:
        super().__init__(f"[{self.reason}] {detail}")
        self.detail = detail


class NotAnEpubError(BookImportError):
    """The input is not an epub at all (not a zip, or wrong mimetype)."""

    reason: ClassVar[str] = "not_an_epub"


class MalformedEpubError(BookImportError):
    """A zip that claims to be an epub but violates the OCF/OPF structure
    (missing container.xml, dangling spine refs, unparseable XML, corrupt
    entries)."""

    reason: ClassVar[str] = "malformed_epub"


class ZipBombSuspectedError(BookImportError):
    """Resource-exhaustion posture tripped: too many entries, an entry or the
    archive exceeding the byte budget, or an extreme compression ratio."""

    reason: ClassVar[str] = "zip_bomb_suspected"


class UnsafeArchivePathError(BookImportError):
    """An archive member name attempts path traversal (``..``), an absolute
    path, a Windows drive, or embedded NUL — refused before any read."""

    reason: ClassVar[str] = "path_traversal"


class ExternalEntityBlockedError(BookImportError):
    """An XML document inside the epub declares a DOCTYPE/ENTITY (XXE /
    billion-laughs surface). We never resolve entities — the file is refused
    outright."""

    reason: ClassVar[str] = "external_entity_blocked"


class DrmLockedError(BookImportError):
    """The epub carries ``META-INF/encryption.xml`` — DRM/encrypted content.
    Never bypassed; the import is refused."""

    reason: ClassVar[str] = "drm_locked"


class NoTextContentError(BookImportError):
    """The book converted to nothing readable (empty spine, or all content
    stripped). An empty body is refused, never published as a hollow book.
    A future PDF arm maps scanned/no-text-layer inputs here too."""

    reason: ClassVar[str] = "no_text_content"


class StoredBodyMismatchError(BookImportError):
    """A document row already exists under this content-addressed id but its
    stored ``raw_text`` is NOT byte-equal to the body being published — an id
    shadow (collision or tampering). Refused: publish never overwrites or
    silently adopts a body it did not write (judge r1 F1/F2)."""

    reason: ClassVar[str] = "stored_body_mismatch"


class RepublishRightsChangeError(BookImportError):
    """A re-publish of already-published content requested different rights
    state (content_class / rights holder / license basis / provenance) than
    what is stored. Refused: converting or re-importing a file NEVER changes
    rights — rights transitions go through the dedicated rights path
    (``substrate.rights.register`` / ``substrate.books.ingest.register_book``
    under an explicit operator decision), not through an import re-run
    (judge r1 F1)."""

    reason: ClassVar[str] = "republish_rights_change"


__all__ = [
    "BookImportError",
    "DrmLockedError",
    "ExternalEntityBlockedError",
    "MalformedEpubError",
    "NoTextContentError",
    "NotAnEpubError",
    "RepublishRightsChangeError",
    "StoredBodyMismatchError",
    "UnsafeArchivePathError",
    "ZipBombSuspectedError",
]
