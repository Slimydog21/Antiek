"""Seeded PA01 rights and direct-reader boundary; no upload or provider."""
from __future__ import annotations

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from interfaces.research.api.books import _admit_private_document
from runtime.db_lock import connect_read, connect_write
from substrate.books.ingest import register_book
from substrate.books.serve_guard import serve_full_text_guarded
from substrate.graph import ensure_initialized
from substrate.graph.ops import (
    insert_document,
    replace_document_body,
    update_document_gate_columns,
)
from substrate.rights.register import resolve_content_class

PRIVATE = "user_authored_private"
BODY = "A private passage that must never become a foreign snippet."


def seed(db: str, *, document_id: str = "private-a", owner: str = "owner-a") -> None:
    with connect_write(db, purpose="pa01-seed") as con:
        insert_document(
            con, document_id=document_id, source_tier=2, document_type="book",
            title="Private title", raw_text=BODY, content_class=PRIVATE,
            owner_user_id=owner,
        )
        register_book(con, document_id=document_id, content_class=PRIVATE)


def owner_id(email: str) -> str:
    from substrate.multi_user.auth import subject_owner_id

    return subject_owner_id("magic_link", email)


def session(email: str) -> dict[str, str]:
    from substrate.multi_user.auth import mint_session_cookie

    return {"ANTIEK_SESSION": mint_session_cookie("magic_link", email, email)}


def client(db: str, monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "pa01-serving-session-secret-" + "x" * 48)
    monkeypatch.setenv(
        "ANTIEK_OPERATOR_EMAIL", "owner-a@example.test,owner-b@example.test"
    )
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    from interfaces.research.api.app import create_app

    return TestClient(
        create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    )


def test_canonical_registration_and_exact_owner_serve(tmp_path):
    db = str(tmp_path / "graph.duckdb")
    ensure_initialized(db)
    assert resolve_content_class(PRIVATE) == PRIVATE
    seed(db)
    con = connect_read(db)
    try:
        public = serve_full_text_guarded(con, "private-a")
        owner = serve_full_text_guarded(con, "private-a", owner=True, owner_user_id="owner-a")
        foreign = serve_full_text_guarded(con, "private-a", owner=True, owner_user_id="owner-b")
        absent = serve_full_text_guarded(con, "private-a", owner=True)
        fallback = serve_full_text_guarded(con, "private-a", owner=True, owner_user_id="__operator__")
    finally:
        con.close()
    assert public.full_text is public.snippet is None
    assert foreign.full_text is foreign.snippet is None
    assert absent.full_text is absent.snippet is None
    assert fallback.full_text is fallback.snippet is None
    assert owner.full_text == BODY and owner.ad_eligible is False
    assert owner.servability.value == "private_authored"


def test_private_twin_declaration_matches_owner_serve(tmp_path):
    from substrate.twin_recursion.source_registration import (
        _envelope_from_served_fields,
        backfill_twin_source_envelopes,
        verify_twin_source_envelopes,
    )

    db = str(tmp_path / "graph.duckdb")
    ensure_initialized(db)
    seed(db)
    with connect_write(db, purpose="pa01-verify-twin") as con:
        envelopes = verify_twin_source_envelopes(con, account_id="owner-a")
        preloaded = con.execute(
            "SELECT d.document_id,d.title,d.document_type,d.owner_user_id,d.raw_text,"
            "d.content_class,d.metadata,COALESCE(b.taken_down,FALSE) "
            "FROM documents d LEFT JOIN book_assets b ON d.document_id=b.document_id "
            "WHERE d.document_id=?", ["private-a"],
        ).fetchone()
        projected, _ = _envelope_from_served_fields(preloaded)
        assert projected == envelopes[0]
        con.execute(
            "UPDATE documents SET twin_source_envelope=NULL WHERE document_id=?",
            ["private-a"],
        )
        assert backfill_twin_source_envelopes(con) == 1
        assert verify_twin_source_envelopes(con, account_id="owner-a") == envelopes
    assert len(envelopes) == 1
    assert envelopes[0].body_sha256 is not None


def test_default_owner_cannot_declare_private_twin_body(tmp_path):
    from substrate.twin_recursion.source_registration import verify_twin_source_envelopes

    db = str(tmp_path / "graph.duckdb")
    ensure_initialized(db)
    seed(db, document_id="private-default", owner="__operator__")
    with connect_write(db, purpose="pa01-default-twin") as con:
        envelopes = verify_twin_source_envelopes(con, account_id="__operator__")
    assert len(envelopes) == 1
    assert envelopes[0].body_sha256 is None


def test_missing_principal_never_matches_malformed_private_owner():
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    for stored_owner in (None, "", "__operator__"):
        with pytest.raises(HTTPException) as exc:
            _admit_private_document(
                None, "private-malformed", request,
                row=(PRIVATE, stored_owner),
            )
        assert exc.value.status_code == 404
        assert exc.value.detail == "book_not_found"


def test_twin_projection_rejects_missing_or_blank_stored_owner(tmp_path):
    from substrate.twin_recursion.source_registration import (
        TwinSourceEnvelopeError,
        _envelope_from_served_fields,
        _row_envelope,
    )

    db = str(tmp_path / "graph.duckdb")
    ensure_initialized(db)
    seed(db)
    with connect_write(db, purpose="pa01-malformed-owner") as con:
        insert_document(
            con, document_id="public-control", source_tier=2,
            document_type="book", title="Public control", raw_text=BODY,
            content_class="public_domain", owner_user_id="owner-a",
        )
        for malformed in (None, "", " "):
            with pytest.raises(TwinSourceEnvelopeError):
                _row_envelope(con, ("private-a", "Private title", "book", malformed))
            with pytest.raises(TwinSourceEnvelopeError):
                _envelope_from_served_fields(
                    ("private-a", "Private title", "book", malformed,
                     BODY, PRIVATE, "{}", False)
                )
        # Historical malformed-owner projection for other classes is unchanged.
        public_live, _ = _row_envelope(
            con, ("public-control", "Public control", "book", None)
        )
        public_preloaded, _ = _envelope_from_served_fields(
            ("public-control", "Public control", "book", None,
             BODY, "public_domain", "{}", False)
        )
        assert public_live == public_preloaded


def test_private_class_update_and_body_replace_keep_twin_in_sync(tmp_path):
    from substrate.twin_recursion.source_registration import verify_twin_source_envelopes

    db = str(tmp_path / "graph.duckdb")
    ensure_initialized(db)
    with connect_write(db, purpose="pa01-update-seed") as con:
        insert_document(
            con, document_id="mutable-private", source_tier=2,
            document_type="book", title="Mutable private", raw_text=BODY,
            content_class="public_domain", owner_user_id="owner-a",
        )
        register_book(con, document_id="mutable-private", content_class="public_domain")
        update_document_gate_columns(
            con, "mutable-private", content_class=PRIVATE, set_content_class=True,
        )
        assert verify_twin_source_envelopes(con, account_id="owner-a")[0].body_sha256
        replace_document_body(con, "mutable-private", raw_text="Private replacement body")
        assert verify_twin_source_envelopes(con, account_id="owner-a")[0].body_sha256


def test_private_license_tier_still_refuses_t3_and_never_enables_ads(tmp_path):
    from substrate.rights import T3BodyServeError

    db = str(tmp_path / "graph.duckdb")
    ensure_initialized(db)
    with connect_write(db, purpose="pa01-license") as con:
        with pytest.raises(T3BodyServeError):
            insert_document(
                con, document_id="private-t3", source_tier=2,
                document_type="book", title="Denied license", raw_text=BODY,
                content_class=PRIVATE, owner_user_id="owner-a",
                metadata={
                    "license_uri": "http://arxiv.org/licenses/nonexclusive-distrib/1.0/",
                    "arxiv_id": "2401.12345",
                },
            )
        assert con.execute(
            "SELECT 1 FROM documents WHERE document_id='private-t3'"
        ).fetchone() is None
        insert_document(
            con, document_id="private-t1", source_tier=2,
            document_type="book", title="Private licensed", raw_text=BODY,
            content_class=PRIVATE, owner_user_id="owner-a",
            metadata={
                "license_uri": "http://creativecommons.org/licenses/by/4.0/",
                "arxiv_id": "2401.12345",
            },
        )
        result = serve_full_text_guarded(
            con, "private-t1", owner=True, owner_user_id="owner-a"
        )
        assert result.full_text == BODY
        assert result.tier == "T1"
        assert result.ad_eligible is False


def test_taken_down_private_t1_hides_metadata_and_ads(tmp_path):
    from substrate.books.takedown import take_down

    db = str(tmp_path / "graph.duckdb")
    ensure_initialized(db)
    with connect_write(db, purpose="pa01-taken-t1") as con:
        insert_document(
            con, document_id="private-taken-t1", source_tier=2,
            document_type="book", title="Secret title", author="Secret author",
            raw_text=BODY, content_class=PRIVATE, owner_user_id="owner-a",
            metadata={
                "license_uri": "http://creativecommons.org/licenses/by/4.0/",
                "arxiv_id": "2401.12345",
            },
        )
        register_book(con, document_id="private-taken-t1", content_class=PRIVATE)
        assert take_down(con, "private-taken-t1", reason="PA01 test")
        foreign = serve_full_text_guarded(
            con, "private-taken-t1", owner=True, owner_user_id="owner-b"
        )
        owner = serve_full_text_guarded(
            con, "private-taken-t1", owner=True, owner_user_id="owner-a"
        )
        assert foreign.title is foreign.author is None
        assert foreign.full_text is foreign.snippet is None
        assert foreign.ad_eligible is False
        assert foreign.canonical_url is foreign.license is foreign.tier is None
        assert owner.servability.value == "taken_down"
        assert owner.full_text is owner.snippet is None
        assert owner.ad_eligible is False
        assert owner.canonical_url == "https://arxiv.org/abs/2401.12345"


@pytest.mark.parametrize("stored_owner", [" __operator__ ", "owner-a "])
def test_noncanonical_private_owner_never_declares_body(tmp_path, stored_owner):
    from substrate.twin_recursion.source_registration import verify_twin_source_envelopes

    db = str(tmp_path / "graph.duckdb")
    ensure_initialized(db)
    seed(db, document_id="private-padded", owner=stored_owner)
    with connect_write(db, purpose="pa01-padded-owner") as con:
        result = serve_full_text_guarded(
            con, "private-padded", owner=True, owner_user_id=stored_owner
        )
        assert result.full_text is result.snippet is None
        envelope = verify_twin_source_envelopes(con, account_id=stored_owner)[0]
        assert envelope.body_sha256 is None


def test_book_detail_and_body_foreign_equal_missing(tmp_path, monkeypatch):
    db = str(tmp_path / "graph.duckdb")
    ensure_initialized(db)
    seed(db, owner=owner_id("owner-a@example.test"))
    api = client(db, monkeypatch, tmp_path)
    for path in ("/books/private-a", "/books/private-a/full-text", "/books/private-a/owner-full-text"):
        foreign = api.get(path, cookies=session("owner-b@example.test"))
        missing = api.get(
            path.replace("private-a", "absent"),
            cookies=session("owner-b@example.test"),
        )
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json() == {"detail": "book_not_found"}
    own = api.get(
        "/books/private-a/owner-full-text",
        cookies=session("owner-a@example.test"),
    )
    assert own.status_code == 200, own.text
    assert own.json()["full_text"] == BODY
    assert own.json()["ad_eligible"] is False


def test_signed_session_cannot_read_foreign_private_book(tmp_path, monkeypatch):
    from interfaces.research.api.app import create_app

    db = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "pa01-signed-cookie-secret-" + "x" * 48)
    monkeypatch.setenv(
        "ANTIEK_OPERATOR_EMAIL", "owner-a@example.test,owner-b@example.test"
    )
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    ensure_initialized(db)
    seed(db, owner=owner_id("owner-a@example.test"))
    api = TestClient(create_app(register_wrestling=False, register_providers=False, cors_origins=[]))

    for path in ("/books/private-a", "/books/private-a/owner-full-text", "/books/private-a/ask"):
        if path.endswith("/ask"):
            foreign = api.post(
                path, cookies=session("owner-b@example.test"),
                json={"question": "private?"},
            )
        else:
            foreign = api.get(path, cookies=session("owner-b@example.test"))
        assert foreign.status_code == 404, foreign.text
        assert foreign.json() == {"detail": "book_not_found"}
    own = api.get(
        "/books/private-a/owner-full-text",
        cookies=session("owner-a@example.test"),
    )
    assert own.status_code == 200, own.text
    assert own.json()["full_text"] == BODY
    anonymous = api.get("/books/private-a/owner-full-text")
    assert anonymous.status_code == 401
    assert BODY not in anonymous.text


def test_private_html_sidecar_and_takedown(tmp_path, monkeypatch):
    from substrate.books.takedown import reinstate, take_down
    from substrate.reader_html.store import store_reader_html

    db = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    ensure_initialized(db)
    seed(db, owner=owner_id("owner-a@example.test"))
    with connect_write(db, purpose="pa01-sidecar") as con:
        store_reader_html(
            con, document_id="private-a",
            main_html="<article><h1>Private title</h1><p>Private HTML passage.</p></article>",
            source_kind="upload",
        )
    api = client(db, monkeypatch, tmp_path)
    owner = session("owner-a@example.test")
    foreign = session("owner-b@example.test")
    own = api.get("/books/private-a/owner-full-text", cookies=owner)
    assert own.status_code == 200
    assert own.json()["content_format"] == "html"
    assert "Private HTML passage" in own.json()["full_text"]
    denied = api.get("/books/private-a/owner-full-text", cookies=foreign)
    assert denied.status_code == 404
    assert "Private HTML passage" not in denied.text
    with connect_write(db, purpose="pa01-takedown") as con:
        assert take_down(con, "private-a", reason="PA01 test")
    taken = api.get("/books/private-a/owner-full-text", cookies=owner)
    assert taken.status_code == 200
    assert taken.json()["full_text"] is None
    assert taken.json()["snippet"] is None
    assert taken.json()["servability"] == "taken_down"
    for path in ("/books/private-a", "/books/private-a/full-text", "/books/private-a/owner-full-text"):
        denied = api.get(path, cookies=foreign)
        missing = api.get(path.replace("private-a", "absent"), cookies=foreign)
        assert denied.status_code == missing.status_code == 404
        assert denied.json() == missing.json() == {"detail": "book_not_found"}
    with connect_write(db, purpose="pa01-reinstate") as con:
        assert reinstate(con, "private-a")
    restored = api.get("/books/private-a/owner-full-text", cookies=owner)
    assert restored.status_code == 200
    assert restored.json()["servability"] == "private_authored"
    assert restored.json()["full_text"] is None  # takedown purged stored bytes
    assert api.get("/books/private-a", cookies=foreign).status_code == 404
