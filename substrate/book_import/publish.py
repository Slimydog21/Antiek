"""Publish a ConvertedBook into the books substrate (SPR-02, sanitize-on-write).

This is the FIRST real consumer of the SPR-01 floor: the one write path on
this branch that stores an HTML body into ``documents``, and it stores that
body only after ``sanitize_book_html`` and stamps the trusted-HTML provenance
(``content_sanitized`` + pinned sanitizer version) in the SAME write —
the sanitize-on-write contract, enforced here rather than hoped for.

It composes EXISTING substrate seams, inventing nothing downstream:

- ``substrate.graph.ops.insert_document`` / ``insert_chunk`` — the same
  writes the native books path uses.
- ``processing.chunking.chunker.chunk_markdown`` — the SAME chunker
  ``acquisition/books/adapter.ingest_pdf`` feeds, over the converter's
  markdown projection, so an imported book chunks/grounds identically to a
  natively-published one (substrate→processing imports have precedent:
  ``substrate/graph/embedding_meta.py``).
- ``substrate.books.ingest.register_book`` — the rights chokepoint:
  ``content_class=None`` lands DENY-BY-DEFAULT gated
  (``restricted_pending_opt_in``); converting a file never upgrades its
  rights. The operator's declared class is passed through explicitly.

Single-writer invariant: every write requires a ``LockedConnection``
(``runtime.db_lock.connect_write``), same as every other books write.

Deliberately NOT emitted: a ``document.loaded`` event —
``DocumentLoadedPayload.media_type`` is a closed Literal without ``"epub"``
(``substrate/schemas/events.py``); widening it belongs to the events-schema
owner. See WIRING.md (W6). Mislabelling the media type was rejected.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from processing.chunking.chunker import chunk_markdown
from runtime.db_lock import LockedConnection
from substrate.books.html_sanitizer import sanitize_book_html, sanitized_html_provenance
from substrate.books.ingest import register_book
from substrate.books.model import TocItem
from substrate.graph.ops import insert_chunk, insert_document

from .convert import ConvertedBook
from .errors import NoTextContentError

# Books are higher-signal than general web — same tier the native books
# adapter uses (acquisition/books/adapter.DEFAULT_BOOK_SOURCE_TIER).
BOOK_IMPORT_SOURCE_TIER = 2

# book_assets.pagination_scheme for imported HTML books: pagination anchors
# are chapter indices (TocItem.page_index = chapter_index), not PDF pages.
CHAPTER_PAGINATION_SCHEME = "chapter"


class SupportsEncode(Protocol):
    """The embedding surface ``insert_chunk`` needs — satisfied by the real
    provider (``processing.embedding.default_embedding_provider``) and by
    test stubs alike."""

    def encode(self, text: str) -> Sequence[float]: ...


@dataclass(frozen=True)
class PublishedBookImport:
    """What one publish produced. ``was_new`` is False on an idempotent
    re-publish (same converted bytes → same content-addressed document)."""

    document_id: str
    was_new: bool
    chunk_ids: tuple[str, ...]
    chunk_count: int
    content_class: str | None
    servability: str
    title: str | None


def _require_locked(con: Any) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"book-import publish requires a LockedConnection (got "
            f"{type(con).__name__}). Use runtime.db_lock.connect_write(db_path)."
        )


def publish_converted_book(
    con: LockedConnection,
    converted: ConvertedBook,
    *,
    investigation_id: str | None = None,
    content_class: str | None = None,
    rights_holder_name: str | None = None,
    source_uri: str | None = None,
    license_basis: str | None = None,
    embedder: SupportsEncode | None = None,
) -> PublishedBookImport:
    """Land one converted book: sanitized document row (+ trusted-HTML
    provenance), chunks through the native chunker, and the ``book_assets``
    registration through the rights chokepoint.

    ``content_class=None`` (the default) lands the book GATED
    (deny-by-default); pass the operator-declared class explicitly to make it
    servable/personal. ``embedder=None`` writes chunks without embeddings
    (retrievable after a re-embed pass); pass a provider for immediate vector
    retrieval. Idempotent on identical converted content.
    """
    _require_locked(con)

    # No-passthrough guarantee AT THE WRITE: even a hand-built ConvertedBook
    # cannot smuggle unsanitized HTML into raw_text. For engine output this is
    # a no-op (html is already a sanitizer fixed point).
    body = sanitize_book_html(converted.html)
    if not body.strip() or not converted.markdown.strip():
        raise NoTextContentError("refusing to publish an empty book body")

    body_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    document_id = f"doc-bookimport-{body_sha[:16]}"
    was_new = (
        con.execute(
            "SELECT 1 FROM documents WHERE document_id = ? LIMIT 1", [document_id]
        ).fetchone()
        is None
    )

    insert_document(
        con,
        document_id=document_id,
        source_tier=BOOK_IMPORT_SOURCE_TIER,
        document_type="book",
        source_uri=source_uri or f"antiek://book-import/{body_sha[:16]}",
        title=converted.title,
        author=converted.author,
        investigation_id=investigation_id,
        raw_text=body,
        metadata={
            # The trusted-HTML contract bits, stamped in the SAME write that
            # stores the sanitized body (SPR-01).
            **sanitized_html_provenance(),
            "book_import": {
                "converter_version": converted.converter_version,
                "source_format": converted.source_format,
                "chapter_count": converted.chapter_count,
                "markdown_sha256": hashlib.sha256(
                    converted.markdown.encode("utf-8")
                ).hexdigest(),
            },
        },
        on_conflict="ignore",
    )

    chunk_ids: list[str] = []
    if was_new:
        for index, chunk in enumerate(chunk_markdown(converted.markdown)):
            chunk_ids.append(
                insert_chunk(
                    con,
                    document_id=document_id,
                    chunk_index=index,
                    text=chunk.text,
                    section_path=chunk.section or None,
                    embedding=list(embedder.encode(chunk.text)) if embedder else None,
                    token_count=chunk.token_count,
                )
            )

    asset = register_book(
        con,
        document_id=document_id,
        content_class=content_class,
        rights_holder_name=rights_holder_name,
        toc=[
            TocItem(title=h.title, page_index=h.chapter_index, level=h.level - 1)
            for h in converted.toc
        ],
        page_count=converted.chapter_count,
        pagination_scheme=CHAPTER_PAGINATION_SCHEME,
        provenance=(
            f"book_import {converted.source_format} {converted.converter_version} "
            f"(sanitizer {converted.sanitizer_version})"
        ),
        license_basis=license_basis,
    )

    return PublishedBookImport(
        document_id=document_id,
        was_new=was_new,
        chunk_ids=tuple(chunk_ids),
        chunk_count=len(chunk_ids),
        content_class=asset.content_class,
        servability=asset.servability.value,
        title=asset.title,
    )


__all__ = [
    "BOOK_IMPORT_SOURCE_TIER",
    "CHAPTER_PAGINATION_SCHEME",
    "PublishedBookImport",
    "SupportsEncode",
    "publish_converted_book",
]
