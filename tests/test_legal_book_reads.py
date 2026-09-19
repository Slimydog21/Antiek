from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write
from substrate.books.model import upsert_book_asset
from substrate.graph.ops import insert_chunk_admitted, insert_document_admitted
from substrate.graph.schema import init_database_at_path
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.legal_gate.admission import admit_staged_document
from substrate.legal_gate.policy_store import account_policy_authority, append_policy_event

NOW = datetime(2026, 7, 15, tzinfo=UTC)


def test_book_metadata_html_body_and_chunks_hide_on_policy_drift(tmp_path, monkeypatch):
    path = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_LEGAL_READ_ENFORCEMENT", "1")
    init_database_at_path(path)
    authority = InvestigationAuthority("__operator__", "inv-book")
    initialize_composite_stream(authority)
    body = "A complete legally admitted book body."
    digest = hashlib.sha256(body.encode()).hexdigest()
    policy = account_policy_authority(authority)
    with connect_write(path, purpose="legal-book-test") as con:
        append_policy_event(
            con,
            policy,
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="books.example",
            decision="allow",
            citation_ref="public-domain-proof",
            issuer_id="operator-rights",
            reason_code="public_domain",
            effective_at=NOW,
        )
        receipt = admit_staged_document(
            con,
            policy,
            investigation_digest=authority.investigation_digest,
            document_id="book-1",
            provenance_class="external_network",
            canonical_url="https://books.example/book",
            content_sha256=digest,
            at=NOW,
        )
        insert_document_admitted(
            con,
            authority,
            admission_receipt_id=receipt.receipt_id,
            admitted_content_sha256=digest,
            document_id="book-1",
            source_tier=1,
            document_type="book",
            investigation_id=authority.investigation_id,
            title="Admitted Book",
            author="Author",
            raw_text=body,
            content_class="public_domain",
        )
        insert_chunk_admitted(
            con,
            authority,
            admission_receipt_id=receipt.receipt_id,
            admitted_content_sha256=digest,
            document_id="book-1",
            chunk_index=0,
            section_path="Page 1",
            text=body,
        )
        upsert_book_asset(con, document_id="book-1", page_count=1)

    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    listing = client.get("/books?investigation_id=inv-book")
    assert listing.status_code == 200
    assert [book["document_id"] for book in listing.json()["books"]] == ["book-1"]
    assert client.get("/books/book-1").status_code == 200
    full = client.get("/books/book-1/full-text")
    assert full.status_code == 200
    assert full.json()["full_text"] == body
    assert full.json()["chunks"][0]["text"] == body

    with connect_write(path, purpose="legal-book-test") as con:
        append_policy_event(
            con,
            policy,
            scope_kind="account",
            matcher_kind="domain",
            matcher_value="blocked.example",
            decision="deny",
            citation_ref="policy-change",
            issuer_id="operator-rights",
            reason_code="blocked",
            effective_at=NOW,
        )
    assert client.get("/books?investigation_id=inv-book").json()["books"] == []
    assert client.get("/books/book-1").status_code == 404
    assert client.get("/books/book-1/full-text").status_code == 404
