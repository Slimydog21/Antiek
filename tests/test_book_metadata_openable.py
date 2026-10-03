"""Reader metadata openability proofs (audit R6: servable text implies openable).

The reader opens a document through ``GET /books/{document_id}``. A
reformatted (derived) document — and a lawful web/URL ingest — writes a
``documents`` row, chunks and provenance, never a ``book_assets`` row, so
the endpoint's bare ``get_book_asset`` lookup answered 404
``book_not_found`` for a document whose ``/full-text`` the very next call
served. These tests pin the repaired contract against a REAL DuckDB
fixture, the real reformat pipeline and the real app:

- a derived document with servable full text is openable (200 BookDetail
  projected from its own rows, chunk-indexed TOC);
- a genuinely missing document id still answers ``book_not_found``;
- the gate is not weakened: a gated, personal, or empty-body document
  without a ``book_assets`` row still answers ``book_not_found``;
- a registered book resolves through ``book_assets`` exactly as before.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write
from substrate.books.ingest import register_book
from substrate.graph.ops import insert_document
from substrate.graph.schema import init_database_at_path
from substrate.reformat.pipeline import reformat_document
from tests.test_reformat_pipeline import (
    ACCEPTANCE_PROMPT,
    _fixture_generator,
    _seed_source,
)


@pytest.fixture
def api_env(tmp_path, monkeypatch):
    db = tmp_path / "t.duckdb"
    events = tmp_path / "events"
    arts = tmp_path / "artifacts"
    events.mkdir()
    arts.mkdir()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(arts))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    init_database_at_path(str(db))
    return {"db": str(db), "events": str(events), "arts": str(arts)}


@pytest.fixture(autouse=True)
def _scrub_operator_auth_env(monkeypatch):
    """Environment invariance: these suites must pass on the operator's own
    Mac, where the login shell exports the operator-auth env — otherwise the
    middleware answers 401 and CI-clean tests fail locally."""
    for key in (
        "ANTIEK_AUTH_SECRET",
        "ANTIEK_OPERATOR_TOKEN",
        "ANTIEK_DEV_LOGIN_TOKEN",
        "ANTIEK_OPERATOR_EMAIL",
        "ANTIEK_COOKIE_INSECURE",
    ):
        monkeypatch.delenv(key, raising=False)


def _client() -> TestClient:
    return TestClient(create_app(register_wrestling=False))


def _insert_web_document(
    db: str,
    document_id: str,
    *,
    content_class: str,
    raw_text: str | None,
) -> None:
    """A web/URL-ingest-shaped row: a documents row with NO book_assets row."""
    with connect_write(db, purpose="test/seed-web-doc") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="web",
            title=f"Web doc {document_id}",
            raw_text=raw_text,
            content_class=content_class,
            on_conflict="error",
        )


def test_derived_document_with_servable_full_text_is_openable(api_env) -> None:
    """The audit's reproducer as a regression test: reformat writes a
    derived document + chunks + provenance and NO book_assets row; the
    reader metadata endpoint must open it (servable text implies openable)."""
    _seed_source(api_env["db"])
    result = reformat_document(
        api_env["db"],
        owner_user_id="__operator__",
        source_document_id="doc-1",
        prompt=ACCEPTANCE_PROMPT,
        generate_fn=_fixture_generator,
    )
    derived_id = result.derived_document_id

    client = _client()
    full = client.get(f"/books/{derived_id}/full-text")
    assert full.status_code == 200
    assert full.json()["servable"] is True
    assert full.json()["full_text"]

    detail = client.get(f"/books/{derived_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["document_id"] == derived_id
    assert body["servable_full_text"] is True
    assert body["taken_down"] is False
    # Reading structure is projected from the document's own chunks — the
    # derived document paginates bite-aligned.
    assert body["pagination_scheme"] == "chunk_index"
    assert body["page_count"] == len(body["toc"]) > 0
    assert [t["page_index"] for t in body["toc"]] == list(range(len(body["toc"])))
    # No book_assets row was invented: the defensibility prose stays absent.
    assert body["provenance"] is None
    assert body["license_basis"] is None

    provenance = client.get(f"/documents/{derived_id}/provenance")
    assert provenance.status_code == 200


def test_missing_document_still_answers_book_not_found(api_env) -> None:
    """Negative control: an id that exists NOWHERE keeps the exact refusal."""
    client = _client()
    resp = client.get("/books/doc-id-exists-nowhere")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "book_not_found"}


def test_gated_document_without_asset_still_answers_book_not_found(api_env) -> None:
    """Gate control: a restricted web document with a body but no
    book_assets row has nothing publicly servable — still a 404, and the
    body reaches no payload."""
    gated_body = "gated body text that must never be served in full"
    _insert_web_document(
        api_env["db"], "doc-gated",
        content_class="restricted_pending_opt_in", raw_text=gated_body,
    )
    client = _client()
    resp = client.get("/books/doc-gated")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "book_not_found"}
    assert gated_body not in resp.text
    full = client.get("/books/doc-gated/full-text")
    assert full.status_code == 200
    assert full.json()["full_text"] is None


def test_personal_reading_document_without_asset_still_answers_book_not_found(api_env) -> None:
    """Gate control: a personal_reading web document is owner-only; the
    public metadata path keeps answering book_not_found."""
    _insert_web_document(
        api_env["db"], "doc-personal",
        content_class="personal_reading", raw_text="private third-party reading",
    )
    client = _client()
    resp = client.get("/books/doc-personal")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "book_not_found"}


def test_empty_body_document_without_asset_still_answers_book_not_found(api_env) -> None:
    """Gate control: a servable-class document with no stored body has
    nothing to serve — the reader stays closed."""
    _insert_web_document(
        api_env["db"], "doc-empty",
        content_class="public_domain", raw_text=None,
    )
    client = _client()
    resp = client.get("/books/doc-empty")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "book_not_found"}


def test_registered_book_resolves_through_book_assets_unchanged(api_env) -> None:
    """Regression control: a real book with a book_assets row resolves
    through the registered-book path exactly as before."""
    with connect_write(api_env["db"], purpose="test/seed-registered-book") as con:
        insert_document(
            con,
            document_id="doc-registered",
            source_tier=2,
            document_type="book",
            title="A Registered Book",
            raw_text="registered book body",
            content_class="public_domain",
            on_conflict="error",
        )
        register_book(con, document_id="doc-registered", content_class="public_domain")
    client = _client()
    resp = client.get("/books/doc-registered")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "A Registered Book"
    assert body["pagination_scheme"] == "pdf_page"
    assert body["servable_full_text"] is True
