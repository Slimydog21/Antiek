"""Authorized, bytes-only EPUB port into Antiek's personal-reading corpus.

Two-phase design:

1. ``convert_authorized_epub`` — pure CPU, no DB, thread-safe.  Runs
   *outside* the writer lock (via ``asyncio.to_thread`` in the route
   handler) so bounded conversion never blocks the global DuckDB writer.

2. ``commit_authorized_port`` — one DB transaction: verify authorization,
   publish converted book, mint signed port receipt.  Runs *inside* the
   writer lock via ``connect_write``.

``port_authorized_epub`` is the backward-compatible convenience wrapper
that chains both phases on a single ``LockedConnection`` (used by tests
that already hold the writer lock).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass

from runtime.db_lock import LockedConnection
from substrate.book_import import (
    ConvertedBook,
    book_publication_transaction,
    convert_epub_to_antiek_html,
    publish_converted_book,
)
from substrate.books.model import get_book_asset
from substrate.books.serve_guard import serve_full_text_guarded

from .authorization import BookAcquisitionConnection, verify_authorization


class PortReceiptIntegrityError(RuntimeError):
    """A stored port receipt does not match the signed port result."""


@dataclass(frozen=True)
class AuthorizedBookPort:
    port_receipt_id: str
    authorization_receipt_id: str
    epub_sha256: str
    document_id: str
    reader_route: str
    content_class: str
    servability: str
    was_new: bool
    port_hash: str


_PREPARED_EPUB_CAPABILITY = object()


@dataclass(frozen=True)
class _PreparedAuthorizedEpub:
    """Opaque in-process result that binds conversion to its source digest."""

    converted: ConvertedBook
    epub_sha256: str
    _capability: object


_DDL = """
CREATE TABLE IF NOT EXISTS book_authorized_ports (
    port_receipt_id TEXT PRIMARY KEY,
    authorization_receipt_id TEXT NOT NULL UNIQUE
        REFERENCES book_purchase_authorizations(authorization_receipt_id),
    epub_sha256 TEXT NOT NULL,
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    reader_route TEXT NOT NULL,
    content_class TEXT NOT NULL CHECK (content_class = 'personal_reading'),
    servability TEXT NOT NULL CHECK (servability = 'personal_readable'),
    port_hash TEXT NOT NULL UNIQUE,
    port_mac TEXT NOT NULL
)
"""


def ensure_port_schema(con: LockedConnection) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError("book port writes require LockedConnection")
    con.execute(_DDL)


def _canonical(values: dict[str, object]) -> str:
    return json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _signed_payload(signing_key: bytes, values: dict[str, object]) -> tuple[str, str]:
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        raise ValueError("signing_key must contain at least 32 bytes")
    canonical = _canonical(values).encode("utf-8")
    return (
        hashlib.sha256(canonical).hexdigest(),
        hmac.new(signing_key, canonical, hashlib.sha256).hexdigest(),
    )


def _payload(
    *,
    authorization_receipt_id: str,
    epub_sha256: str,
    document_id: str,
    servability: str,
) -> dict[str, object]:
    return {
        "authorization_receipt_id": authorization_receipt_id,
        "content_class": "personal_reading",
        "document_id": document_id,
        "epub_sha256": epub_sha256,
        "reader_route": f"/read/{document_id}",
        "servability": servability,
    }


# ── Phase 1: pure conversion, no DB ─────────────────────────────────


def convert_authorized_epub(
    epub_bytes: bytes,
) -> _PreparedAuthorizedEpub:
    """Convert EPUB bytes into Antiek-HTML outside the writer lock.

    Returns an opaque conversion result bound to the source digest. Pure CPU,
    no database access,
    safe to run via ``asyncio.to_thread`` on the event loop.  Raises the
    typed :mod:`substrate.book_import.errors` vocabulary on hostile or
    unreadable input — the caller translates those to HTTP 422/413/409.

    The returned ``epub_sha256`` is the content hash of the *raw* EPUB
    bytes (not the converted HTML), used as the stable port receipt key.
    """
    if not isinstance(epub_bytes, bytes) or not epub_bytes:
        raise ValueError("epub_bytes must be non-empty bytes")
    converted = convert_epub_to_antiek_html(epub_bytes)
    epub_sha256 = hashlib.sha256(epub_bytes).hexdigest()
    return _PreparedAuthorizedEpub(
        converted=converted,
        epub_sha256=epub_sha256,
        _capability=_PREPARED_EPUB_CAPABILITY,
    )


# ── Phase 2: one DB transaction ─────────────────────────────────────


def commit_authorized_port(
    con: LockedConnection,
    *,
    authorization_receipt_id: str,
    operator_id: str,
    signing_key: bytes,
    prepared: _PreparedAuthorizedEpub,
) -> AuthorizedBookPort:
    """Commit the authorized port inside the writer lock.

    One atomic transaction: verify authorization, publish the converted
    book, mint the signed port receipt.  Authorization verification
    happens *inside* this transaction so it cannot be bypassed.
    """
    if not isinstance(con, LockedConnection):
        raise TypeError("book port writes require LockedConnection")
    if (
        not isinstance(prepared, _PreparedAuthorizedEpub)
        or prepared._capability is not _PREPARED_EPUB_CAPABILITY
    ):
        raise TypeError("prepared must come from convert_authorized_epub")
    converted = prepared.converted
    epub_sha256 = prepared.epub_sha256

    with book_publication_transaction(con) as transaction:
        # Verification and publication share one transaction. The global
        # writer lock prevents concurrent writers; the transaction also
        # guarantees rollback if publication or receipt insertion fails.
        verify_authorization(
            con,
            authorization_receipt_id=authorization_receipt_id,
            expected_operator_id=operator_id,
            signing_key=signing_key,
        )
        published = publish_converted_book(
            con,
            converted,
            content_class="personal_reading",
            source_uri=f"antiek://authorized-book/{authorization_receipt_id}",
            license_basis="operator-authorized legally-held personal copy",
            transaction=transaction,
        )
        values = _payload(
            authorization_receipt_id=authorization_receipt_id,
            epub_sha256=epub_sha256,
            document_id=published.document_id,
            servability=published.servability,
        )
        port_hash, port_mac = _signed_payload(signing_key, values)
        port_receipt_id = f"bookport-{port_hash}"
        expected = (
            port_receipt_id,
            authorization_receipt_id,
            epub_sha256,
            published.document_id,
            values["reader_route"],
            "personal_reading",
            published.servability,
            port_hash,
            port_mac,
        )
        existing = con.execute(
            "SELECT * FROM book_authorized_ports WHERE authorization_receipt_id = ?",
            [authorization_receipt_id],
        ).fetchone()
        if existing is None:
            con.execute(
                "INSERT INTO book_authorized_ports VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                list(expected),
            )
        elif tuple(existing) != expected:
            raise PortReceiptIntegrityError(
                "authorization already has a different or tampered port receipt"
            )

    return AuthorizedBookPort(
        port_receipt_id=port_receipt_id,
        authorization_receipt_id=authorization_receipt_id,
        epub_sha256=epub_sha256,
        document_id=published.document_id,
        reader_route=str(values["reader_route"]),
        content_class="personal_reading",
        servability=published.servability,
        was_new=published.was_new,
        port_hash=port_hash,
    )


# ── Convenience: one-call path for tests that already hold writer ────


def port_authorized_epub(
    con: LockedConnection,
    *,
    authorization_receipt_id: str,
    operator_id: str,
    signing_key: bytes,
    epub_bytes: bytes,
) -> AuthorizedBookPort:
    """Convert + commit in one call.

    Backward-compatible entry point for callers that already hold the
    writer lock (e.g. unit tests).  The route handler uses the split
    ``convert_authorized_epub`` → ``commit_authorized_port`` path
    instead, so conversion runs outside the writer lock.
    """
    prepared = convert_authorized_epub(epub_bytes)
    return commit_authorized_port(
        con,
        authorization_receipt_id=authorization_receipt_id,
        operator_id=operator_id,
        signing_key=signing_key,
        prepared=prepared,
    )


# ── Verification (read-only) ─────────────────────────────────────────


def verify_port_receipt(
    con: BookAcquisitionConnection,
    *,
    port_receipt_id: str,
    authorization_receipt_id: str,
    operator_id: str,
    signing_key: bytes,
) -> AuthorizedBookPort:
    verify_authorization(
        con,
        authorization_receipt_id=authorization_receipt_id,
        expected_operator_id=operator_id,
        signing_key=signing_key,
    )
    row = con.execute(
        "SELECT * FROM book_authorized_ports WHERE port_receipt_id = ?",
        [port_receipt_id],
    ).fetchone()
    if row is None:
        raise PortReceiptIntegrityError("port receipt does not exist")
    (
        stored_id,
        stored_auth,
        epub_sha256,
        document_id,
        reader_route,
        content_class,
        servability,
        stored_hash,
        stored_mac,
    ) = row
    if stored_auth != authorization_receipt_id:
        raise PortReceiptIntegrityError("port receipt authorization binding is invalid")
    values = _payload(
        authorization_receipt_id=str(stored_auth),
        epub_sha256=str(epub_sha256),
        document_id=str(document_id),
        servability=str(servability),
    )
    port_hash, port_mac = _signed_payload(signing_key, values)
    if (
        stored_id != f"bookport-{port_hash}"
        or stored_hash != port_hash
        or not hmac.compare_digest(str(stored_mac), port_mac)
        or reader_route != values["reader_route"]
        or content_class != "personal_reading"
    ):
        raise PortReceiptIntegrityError("port receipt is tampered")
    asset = get_book_asset(con, str(document_id))
    if asset is None:
        raise PortReceiptIntegrityError("ported document or book asset is missing")
    if asset.taken_down:
        raise PortReceiptIntegrityError("ported document has been taken down")
    served = serve_full_text_guarded(con, str(document_id), owner=True)
    if served.full_text is None:
        raise PortReceiptIntegrityError("ported document body is not owner-servable")
    expected_document_id = (
        "doc-bookimport-"
        + hashlib.sha256(served.full_text.encode("utf-8")).hexdigest()[:32]
    )
    if (
        expected_document_id != document_id
        or asset.content_class != "personal_reading"
        or asset.servability.value != servability
    ):
        raise PortReceiptIntegrityError("ported document integrity is invalid")
    return AuthorizedBookPort(
        str(stored_id),
        str(stored_auth),
        str(epub_sha256),
        str(document_id),
        str(reader_route),
        str(content_class),
        str(servability),
        False,
        port_hash,
    )


__all__ = [
    "AuthorizedBookPort",
    "PortReceiptIntegrityError",
    "commit_authorized_port",
    "convert_authorized_epub",
    "ensure_port_schema",
    "port_authorized_epub",
    "verify_port_receipt",
]
