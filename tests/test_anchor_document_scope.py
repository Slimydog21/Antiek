"""An anchor is reachable only through its own document's URI (B4).

``DELETE`` and ``PATCH /books/{document_id}/anchors/{anchor_id}`` scoped the
row by anchor and owner but ignored the ``document_id`` in their own path, so
an anchor pinned on book A could be deleted or linked to a thread through book
B's URI (combined-tree review of #3512, REVIEW-combined:117-123). Both now
match the document too: the delete stays an idempotent 204 that reveals
nothing, and the link answers 404, the same as an anchor that does not exist.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.books.highlights.store import HighlightsStore
from substrate.graph import ensure_initialized
from tests.test_book_anchor_routes import BODY_TEXT, _client, _pin_payload, _seed_book


@pytest.fixture
def api_env(monkeypatch):
    # The anchor route suite's real-DuckDB environment (test_book_anchor_routes.py).
    tmpdir = tempfile.mkdtemp(prefix="anchor-scope-")
    db = os.path.join(tmpdir, "t.duckdb")
    events = os.path.join(tmpdir, "events")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", os.path.join(tmpdir, "artifacts"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ensure_initialized(db)
    return {"db": db, "events": events}


@pytest.fixture(autouse=True)
def _no_ambient_operator(monkeypatch):
    # An inherited operator identity makes these routes answer 401; the proofs
    # run as the single-operator default the rest of the anchor suite assumes.
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)


def _two_books_and_an_anchor_on_a(api_env) -> tuple[object, str]:
    db = api_env["db"]
    _seed_book(db, document_id="doc-a", chunks=[("c-a1", BODY_TEXT, "Page 1")])
    _seed_book(db, document_id="doc-b", chunks=[("c-b1", BODY_TEXT, "Page 1")])
    client = _client()
    created = client.post("/books/doc-a/anchors", json=_pin_payload())
    assert created.status_code == 201, created.text
    return client, created.json()["anchor_id"]


def test_an_anchor_cannot_be_deleted_through_another_documents_uri(api_env) -> None:
    client, anchor_id = _two_books_and_an_anchor_on_a(api_env)
    # The wrong document answers the same idempotent 204 a missing anchor does…
    assert client.delete(f"/books/doc-b/anchors/{anchor_id}").status_code == 204
    # …and the anchor on doc-a survives it.
    listed = client.get("/books/doc-a/anchors").json()
    assert [a["anchor_id"] for a in listed["anchors"]] == [anchor_id]
    # Its own URI still deletes it.
    assert client.delete(f"/books/doc-a/anchors/{anchor_id}").status_code == 204
    assert client.get("/books/doc-a/anchors").json()["count"] == 0


def test_an_anchor_cannot_be_linked_through_another_documents_uri(api_env) -> None:
    client, anchor_id = _two_books_and_an_anchor_on_a(api_env)
    wrong = client.patch(
        f"/books/doc-b/anchors/{anchor_id}", json={"investigation_id": "inv-foreign"}
    )
    assert wrong.status_code == 404
    assert wrong.json()["detail"] == "anchor_not_found"
    # First link still wins through the right URI: the foreign attempt took nothing.
    right = client.patch(
        f"/books/doc-a/anchors/{anchor_id}", json={"investigation_id": "inv-own"}
    )
    assert right.status_code == 200
    assert right.json()["investigation_id"] == "inv-own"


def test_the_store_requires_and_matches_the_document(api_env) -> None:
    client, anchor_id = _two_books_and_an_anchor_on_a(api_env)
    owner = client.get("/books/doc-a/anchors").json()["anchors"][0]
    store = HighlightsStore()
    with connect_write(api_env["db"], purpose="test/anchor-scope") as con:
        row = store.get(con, anchor_id)
        assert row is not None
        assert store.set_investigation_link(
            con, anchor_id, row.owner_user_id, "inv-x", document_id="doc-b"
        ) == "not_found"
        assert store.delete(con, anchor_id, row.owner_user_id, document_id="doc-b") is False
        assert store.delete(con, anchor_id, row.owner_user_id, document_id="doc-a") is True
    assert owner["document_id"] == "doc-a"
    # No unscoped call remains possible: document_id is keyword-only and required.
    with pytest.raises(TypeError):
        store.delete(None, anchor_id, "owner")  # type: ignore[call-arg]
