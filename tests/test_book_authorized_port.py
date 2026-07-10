from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from runtime.db_lock import LockedConnection, connect_write
from substrate.book_acquisition import (
    AcquisitionIntegrityError,
    AuthorizationDecision,
    authorize_purchase_intent,
    create_purchase_intent,
    ensure_schema,
)
from substrate.book_acquisition.port import (
    PortReceiptIntegrityError,
    ensure_port_schema,
    port_authorized_epub,
    verify_port_receipt,
)
from substrate.books.serve import serve_full_text
from substrate.graph.schema import init_database

KEY = b"antiek-authorized-port-test-key-32-bytes"


def _epub(body: str = "Turbofan engines compress incoming air.") -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        archive.writestr(
            "OEBPS/content.opf",
            '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/" version="3.0"><metadata><dc:title>Aircraft Engines</dc:title><dc:creator>A. Researcher</dc:creator></metadata><manifest><item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="c1"/></spine></package>',
        )
        archive.writestr("OEBPS/c1.xhtml", f"<html><body><h1>Chapter</h1><p>{body}</p></body></html>")
    return out.getvalue()


@pytest.fixture
def writer(tmp_path: Path):
    with connect_write(str(tmp_path / "port.duckdb"), purpose="book-port-test") as con:
        init_database(con)
        ensure_schema(con)
        ensure_port_schema(con)
        yield con


def _authorization(writer: LockedConnection, decision=AuthorizationDecision.AUTHORIZED):
    intent = create_purchase_intent(
        writer, operator_id="alice", title="Aircraft Engines",
        author="A. Researcher", store="publisher.example",
        max_price_usd_cents=3000, signing_key=KEY,
    )
    return authorize_purchase_intent(
        writer, intent_receipt_id=intent.intent_receipt_id, operator_id="alice",
        decision=decision,
        authorized_price_ceiling_usd_cents=2500 if decision is AuthorizationDecision.AUTHORIZED else 0,
        signing_key=KEY,
    )


def test_authorized_epub_ports_to_owner_only_html(writer: LockedConnection) -> None:
    authorization = _authorization(writer)
    result = port_authorized_epub(
        writer, authorization_receipt_id=authorization.authorization_receipt_id,
        operator_id="alice", signing_key=KEY, epub_bytes=_epub(),
    )
    assert result.reader_route == f"/read/{result.document_id}"
    assert result.content_class == "personal_reading"
    owner = serve_full_text(writer, result.document_id, owner=True)
    public = serve_full_text(writer, result.document_id)
    assert owner.full_text and "Turbofan" in owner.full_text
    assert public.full_text is None
    assert public.servable is False


def test_exact_replay_returns_same_receipt_and_document(writer: LockedConnection) -> None:
    authorization = _authorization(writer)
    kwargs = dict(
        authorization_receipt_id=authorization.authorization_receipt_id,
        operator_id="alice", signing_key=KEY, epub_bytes=_epub(),
    )
    first = port_authorized_epub(writer, **kwargs)
    second = port_authorized_epub(writer, **kwargs)
    assert second.port_receipt_id == first.port_receipt_id
    assert second.document_id == first.document_id
    assert first.was_new is True
    assert second.was_new is False
    assert writer.execute("SELECT COUNT(*) FROM book_authorized_ports").fetchone() == (1,)


def test_same_authorization_cannot_port_different_epub(writer: LockedConnection) -> None:
    authorization = _authorization(writer)
    first = port_authorized_epub(
        writer,
        authorization_receipt_id=authorization.authorization_receipt_id,
        operator_id="alice",
        signing_key=KEY,
        epub_bytes=_epub(),
    )
    with pytest.raises(PortReceiptIntegrityError):
        port_authorized_epub(
            writer,
            authorization_receipt_id=authorization.authorization_receipt_id,
            operator_id="alice",
            signing_key=KEY,
            epub_bytes=_epub("A materially different legally-held edition."),
        )
    assert writer.execute("SELECT COUNT(*) FROM documents").fetchone() == (1,)
    assert writer.execute("SELECT COUNT(*) FROM book_assets").fetchone() == (1,)
    assert writer.execute("SELECT COUNT(*) FROM book_authorized_ports").fetchone() == (
        1,
    )
    assert verify_port_receipt(
        writer,
        port_receipt_id=first.port_receipt_id,
        authorization_receipt_id=authorization.authorization_receipt_id,
        operator_id="alice",
        signing_key=KEY,
    ).document_id == first.document_id


def test_denied_and_fabricated_authorizations_publish_nothing(writer: LockedConnection) -> None:
    denied = _authorization(writer, AuthorizationDecision.DENIED)
    with pytest.raises(AcquisitionIntegrityError):
        port_authorized_epub(
            writer, authorization_receipt_id=denied.authorization_receipt_id,
            operator_id="alice", signing_key=KEY, epub_bytes=_epub(),
        )
    with pytest.raises(AcquisitionIntegrityError):
        port_authorized_epub(
            writer, authorization_receipt_id="bookauth-deadbeef",
            operator_id="alice", signing_key=KEY, epub_bytes=_epub(),
        )
    assert writer.execute("SELECT COUNT(*) FROM documents").fetchone() == (0,)


def test_port_receipt_tamper_fails_closed(writer: LockedConnection) -> None:
    authorization = _authorization(writer)
    result = port_authorized_epub(
        writer, authorization_receipt_id=authorization.authorization_receipt_id,
        operator_id="alice", signing_key=KEY, epub_bytes=_epub(),
    )
    writer.execute(
        "UPDATE book_authorized_ports SET port_mac='forged' WHERE port_receipt_id=?",
        [result.port_receipt_id],
    )
    with pytest.raises(PortReceiptIntegrityError, match="tampered"):
        verify_port_receipt(
            writer, port_receipt_id=result.port_receipt_id,
            authorization_receipt_id=authorization.authorization_receipt_id,
            operator_id="alice", signing_key=KEY,
        )


def test_ported_document_tamper_fails_closed(writer: LockedConnection) -> None:
    authorization = _authorization(writer)
    result = port_authorized_epub(
        writer,
        authorization_receipt_id=authorization.authorization_receipt_id,
        operator_id="alice",
        signing_key=KEY,
        epub_bytes=_epub(),
    )
    writer.execute(
        "UPDATE documents SET raw_text = '<p>forged</p>' WHERE document_id = ?",
        [result.document_id],
    )
    with pytest.raises(PortReceiptIntegrityError, match="integrity"):
        verify_port_receipt(
            writer,
            port_receipt_id=result.port_receipt_id,
            authorization_receipt_id=authorization.authorization_receipt_id,
            operator_id="alice",
            signing_key=KEY,
        )


def test_taken_down_document_receipt_is_refused(writer: LockedConnection) -> None:
    authorization = _authorization(writer)
    result = port_authorized_epub(
        writer,
        authorization_receipt_id=authorization.authorization_receipt_id,
        operator_id="alice",
        signing_key=KEY,
        epub_bytes=_epub(),
    )
    writer.execute(
        "UPDATE book_assets SET taken_down = TRUE WHERE document_id = ?",
        [result.document_id],
    )
    with pytest.raises(PortReceiptIntegrityError, match="taken down"):
        verify_port_receipt(
            writer,
            port_receipt_id=result.port_receipt_id,
            authorization_receipt_id=authorization.authorization_receipt_id,
            operator_id="alice",
            signing_key=KEY,
        )


def test_receipt_verification_rejects_different_key(writer: LockedConnection) -> None:
    authorization = _authorization(writer)
    result = port_authorized_epub(
        writer,
        authorization_receipt_id=authorization.authorization_receipt_id,
        operator_id="alice",
        signing_key=KEY,
        epub_bytes=_epub(),
    )
    with pytest.raises(AcquisitionIntegrityError, match="signature"):
        verify_port_receipt(
            writer,
            port_receipt_id=result.port_receipt_id,
            authorization_receipt_id=authorization.authorization_receipt_id,
            operator_id="alice",
            signing_key=b"different-antiek-port-key-32-bytes",
        )


def test_input_is_bytes_only(writer: LockedConnection) -> None:
    authorization = _authorization(writer)
    with pytest.raises(ValueError, match="bytes"):
        port_authorized_epub(
            writer, authorization_receipt_id=authorization.authorization_receipt_id,
            operator_id="alice", signing_key=KEY, epub_bytes="/tmp/book.epub",  # type: ignore[arg-type]
        )
