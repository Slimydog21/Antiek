"""Book asset model over the documents table (SPR-01 M1 + M7).

A *book* is a ``documents`` row of ``document_type='book'`` carrying the
full text in ``raw_text`` and the license in ``content_class``. This
module adds the book-specific structure — TOC, pagination scheme, cover,
and the takedown override — on the ``book_assets`` row keyed 1:1 to the
document.

What lives here vs. on the document:

- ``documents.content_class`` / ``documents.ip_holder_id`` — the
  authoritative license + rights-holder. The serve gate keys off
  content_class; ``book_assets`` never duplicates it (no drift).
- ``book_assets.taken_down`` + ``pre_takedown_content_class`` — the
  takedown override, orthogonal to the license so takedown is reversible.
- ``book_assets.toc_json`` / ``page_count`` / ``pagination_scheme`` /
  ``cover_uri`` — the reading structure.
- ``book_assets.provenance`` / ``license_basis`` — defensibility prose.

Every write goes through a ``LockedConnection`` (single-writer invariant,
master-spec §16; ``runtime/db_lock.connect_write``). Reads take any
connection. The :class:`BookAsset` returned by reads carries the DERIVED
:class:`ServabilityStatus` so callers never re-implement the projection.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from runtime.db_lock import LockedConnection

from .servability import ServabilityStatus, is_servable_full_text, servability_of


@dataclass(frozen=True)
class TocItem:
    """One table-of-contents entry as stored on the book asset. Mirrors
    ``acquisition.books.reader.TocEntry`` but lives in substrate so this
    layer carries no upward dependency on acquisition."""

    title: str
    page_index: int | None
    level: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "page_index": self.page_index, "level": self.level}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TocItem:
        return cls(
            title=str(d.get("title", "")),
            page_index=d.get("page_index"),
            level=int(d.get("level", 0)),
        )


@dataclass(frozen=True)
class BookAsset:
    """A book joined to its license + derived servability. The fields
    above the line come from ``book_assets``; ``content_class`` / ``title``
    / ``author`` are joined from ``documents``; ``servability`` and
    ``servable_full_text`` are DERIVED (never stored) so the data layer
    and the UI cannot disagree about whether a book may be served."""

    document_id: str
    title: str | None
    author: str | None
    content_class: str | None
    ip_holder_id: str | None
    page_count: int
    pagination_scheme: str
    cover_uri: str | None
    toc: list[TocItem]
    provenance: str | None
    license_basis: str | None
    taken_down: bool
    taken_down_at: str | None
    takedown_reason: str | None
    pre_takedown_content_class: str | None
    # Derived — resolved once at read time from (content_class, taken_down).
    servability: ServabilityStatus = field(init=False)
    servable_full_text: bool = field(init=False)

    def __post_init__(self) -> None:
        status = servability_of(self.content_class, taken_down=self.taken_down)
        object.__setattr__(self, "servability", status)
        object.__setattr__(self, "servable_full_text", is_servable_full_text(status))


# ---------------------------------------------------------------------------
# Writes — single-writer (LockedConnection required)
# ---------------------------------------------------------------------------


def _require_locked(con: Any) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"book_assets writes require a LockedConnection (got {type(con).__name__}). "
            "Use runtime.db_lock.connect_write(db_path)."
        )


def upsert_book_asset(
    con: LockedConnection,
    *,
    document_id: str,
    toc: list[TocItem] | None = None,
    page_count: int = 0,
    pagination_scheme: str = "pdf_page",
    cover_uri: str | None = None,
    provenance: str | None = None,
    license_basis: str | None = None,
) -> str:
    """Create or update the ``book_assets`` row for ``document_id``.

    Idempotent on ``document_id`` (PK). Does NOT touch takedown state —
    that is owned exclusively by ``substrate.books.takedown`` so a book
    can't be silently un-taken-down by a metadata re-write. Returns the
    document_id.
    """
    _require_locked(con)
    toc_json = json.dumps([t.to_dict() for t in (toc or [])])
    exists = con.execute(
        "SELECT 1 FROM book_assets WHERE document_id = ?", [document_id]
    ).fetchone()
    if exists:
        con.execute(
            """
            UPDATE book_assets
            SET toc_json = ?, page_count = ?, pagination_scheme = ?,
                cover_uri = ?, provenance = ?, license_basis = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE document_id = ?
            """,
            [toc_json, int(page_count), pagination_scheme, cover_uri,
             provenance, license_basis, document_id],
        )
    else:
        con.execute(
            """
            INSERT INTO book_assets (
                document_id, toc_json, page_count, pagination_scheme,
                cover_uri, provenance, license_basis
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [document_id, toc_json, int(page_count), pagination_scheme,
             cover_uri, provenance, license_basis],
        )
    return document_id


# ---------------------------------------------------------------------------
# Reads — any connection
# ---------------------------------------------------------------------------


# The canonical SELECT joining book_assets to its document. One projection,
# reused by get_book_asset and list_book_assets, so the BookAsset shape has
# a single source.
_BOOK_SELECT = """
    SELECT
        b.document_id, d.title, d.author, d.content_class, d.ip_holder_id,
        b.page_count, b.pagination_scheme, b.cover_uri, b.toc_json,
        b.provenance, b.license_basis,
        b.taken_down, b.taken_down_at, b.takedown_reason,
        b.pre_takedown_content_class
    FROM book_assets b
    JOIN documents d ON b.document_id = d.document_id
"""


def _row_to_asset(row: tuple[Any, ...]) -> BookAsset:
    (document_id, title, author, content_class, ip_holder_id,
     page_count, pagination_scheme, cover_uri, toc_json,
     provenance, license_basis,
     taken_down, taken_down_at, takedown_reason,
     pre_takedown_content_class) = row
    toc: list[TocItem] = []
    if toc_json:
        try:
            toc = [TocItem.from_dict(d) for d in json.loads(toc_json)]
        except (TypeError, ValueError):
            toc = []
    return BookAsset(
        document_id=document_id,
        title=title,
        author=author,
        content_class=content_class,
        ip_holder_id=ip_holder_id,
        page_count=int(page_count or 0),
        pagination_scheme=pagination_scheme or "pdf_page",
        cover_uri=cover_uri,
        toc=toc,
        provenance=provenance,
        license_basis=license_basis,
        taken_down=bool(taken_down),
        taken_down_at=str(taken_down_at) if taken_down_at else None,
        takedown_reason=takedown_reason,
        pre_takedown_content_class=pre_takedown_content_class,
    )


def get_book_asset(con: Any, document_id: str) -> BookAsset | None:
    """Read one book joined to its license + derived servability. None if
    the document_id has no ``book_assets`` row (not a registered book)."""
    row = con.execute(
        _BOOK_SELECT + " WHERE b.document_id = ?", [document_id]
    ).fetchone()
    return _row_to_asset(row) if row is not None else None


def list_book_assets(
    con: Any,
    *,
    servable_only: bool = False,
    include_taken_down: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> list[BookAsset]:
    """List registered books, newest first.

    ``servable_only`` filters to books whose full text may be served
    (the deny-by-default allowlist, applied at the SQL layer via
    ``SERVABLE_CONTENT_CLASSES`` so the filter can't drift from the
    serve gate). ``include_taken_down`` is False by default — taken-down
    books are excluded from listings unless an operator/audit caller asks.
    """
    from substrate.constants import SERVABLE_CONTENT_CLASSES

    sql = _BOOK_SELECT
    clauses: list[str] = []
    params: list[Any] = []
    if not include_taken_down:
        clauses.append("b.taken_down = FALSE")
    if servable_only:
        placeholders = ",".join("?" for _ in SERVABLE_CONTENT_CLASSES)
        clauses.append(f"d.content_class IN ({placeholders})")
        params.extend(sorted(SERVABLE_CONTENT_CLASSES))
        clauses.append("b.taken_down = FALSE")  # servable ⇒ not taken down
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if offset < 0:
        raise ValueError("offset must be >= 0")
    # The document-id tie-breaker makes adjacent offset pages deterministic
    # when multiple assets share a creation timestamp.
    sql += " ORDER BY b.created_at DESC, b.document_id DESC LIMIT ? OFFSET ?"
    params.extend([int(limit), int(offset)])
    rows = con.execute(sql, params).fetchall()
    return [_row_to_asset(r) for r in rows]
