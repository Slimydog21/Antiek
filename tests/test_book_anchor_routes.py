"""Anchor-first SPR-03 route proofs — /books/{id}/anchors + anchor-map.

FastAPI TestClient against a REAL DuckDB fixture (the api_env shape from
tests/test_artifact_routes.py): full POST → GET → DELETE lifecycle, honest
422s, owner boundaries, metadata-only persistence on a non-servable
document, and the anchor-map gating/no-body contract. The auth middleware's
enforcement-disabled default stamps the single-operator identity, so the
requesting owner is the substrate's "__operator__" unless a test says
otherwise.
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api import books as books_api
from interfaces.research.api.app import create_app
from runtime.db_lock import connect_read, connect_write
from substrate.graph import ensure_initialized
from substrate.graph.ops import insert_document

BODY_TEXT = (
    "The first passage holds a sentence worth remembering. "
    "A middle stretch of ordinary prose follows here. "
    "The last passage closes the book quietly."
)

PRIVATE_BODY = "An owner-only sentence about their private reading habits."


@pytest.fixture
def api_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="anchor-api-")
    db = os.path.join(tmpdir, "t.duckdb")
    events = os.path.join(tmpdir, "events")
    arts = os.path.join(tmpdir, "artifacts")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", arts)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ensure_initialized(db)
    return {"db": db, "events": events, "arts": arts}


def _client() -> TestClient:
    return TestClient(create_app(register_wrestling=False))


def _seed_book(
    db: str,
    *,
    document_id: str = "doc-anchor",
    content_class: str | None = "public_domain",
    body: str = BODY_TEXT,
    chunks: list[tuple[str, str, str | None]] | None = None,
) -> None:
    with connect_write(db, purpose="test/seed-anchor-book") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="book",
            title="Anchor Book",
            raw_text=body,
            content_class=content_class,
            on_conflict="ignore",
        )
        for index, (chunk_id, text, section_path) in enumerate(chunks or []):
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, "
                "section_path, text, token_count) VALUES (?, ?, ?, ?, ?, ?)",
                [chunk_id, document_id, index, section_path, text, len(text.split())],
            )


def _pin_payload(**over: object) -> dict:
    body = {
        "quote": "sentence worth remembering",
        "prefix": "holds a ",
        "suffix": ". A middle",
        "source": "pin",
    }
    body.update(over)
    return body


def _seed_default_chunks(db: str, document_id: str = "doc-anchor") -> None:
    _seed_book(
        db,
        document_id=document_id,
        chunks=[("c-1", BODY_TEXT, "Page 1")],
    )


# ── Proof 1: the full lifecycle + honest 422s + owner boundaries ───────────


def test_post_get_delete_lifecycle(api_env) -> None:
    db = api_env["db"]
    _seed_default_chunks(db)
    client = _client()

    # POST resolves the unique (chunk_id, offsets) and persists the pin.
    created = client.post("/books/doc-anchor/anchors", json=_pin_payload())
    assert created.status_code == 201
    anchor = created.json()
    assert anchor["anchor"]["node_id"] == "c-1"
    assert anchor["anchor"]["quote"] == "sentence worth remembering"
    assert anchor["status"] == "active"
    assert anchor["exact_valid"] is True
    assert anchor["source"] == "pin"
    assert anchor["page_index_hint"] == 0
    # The SPR-04 seam: present and null from day one.
    assert "investigation_id" in anchor
    assert anchor["investigation_id"] is None
    anchor_id = anchor["anchor_id"]

    # GET lists it with the live exact-validity flag.
    listing = client.get("/books/doc-anchor/anchors")
    assert listing.status_code == 200
    body = listing.json()
    assert body["count"] == 1
    assert body["anchors"][0]["anchor_id"] == anchor_id
    assert body["anchors"][0]["exact_valid"] is True

    # DELETE is idempotent: the second delete is a 204, not a 404.
    first = client.delete(f"/books/doc-anchor/anchors/{anchor_id}")
    second = client.delete(f"/books/doc-anchor/anchors/{anchor_id}")
    assert first.status_code == 204
    assert second.status_code == 204
    assert client.get("/books/doc-anchor/anchors").json()["count"] == 0


def test_ambiguous_quote_is_a_422(api_env) -> None:
    db = api_env["db"]
    _seed_book(
        db,
        chunks=[("c-1", BODY_TEXT, None), ("c-2", BODY_TEXT, None)],
    )
    client = _client()
    resp = client.post("/books/doc-anchor/anchors", json=_pin_payload())
    assert resp.status_code == 422
    assert "anchor_resolution_ambiguous" in resp.json()["detail"]


def test_unlocatable_quote_is_a_422(api_env) -> None:
    db = api_env["db"]
    _seed_default_chunks(db)
    client = _client()
    resp = client.post(
        "/books/doc-anchor/anchors",
        json=_pin_payload(quote="no such sentence exists here", prefix="", suffix=""),
    )
    assert resp.status_code == 422
    assert "anchor_resolution_not_found" in resp.json()["detail"]


def test_invalid_source_is_a_422(api_env) -> None:
    db = api_env["db"]
    _seed_default_chunks(db)
    client = _client()
    resp = client.post("/books/doc-anchor/anchors", json=_pin_payload(source="made_up"))
    assert resp.status_code == 422
    assert "anchor_source_invalid" in resp.json()["detail"]


def test_owner_boundary_is_enforced(api_env) -> None:
    """A pin written by one owner is invisible and undeletable to another."""
    db = api_env["db"]
    _seed_default_chunks(db)
    client = _client()
    created = client.post("/books/doc-anchor/anchors", json=_pin_payload())
    assert created.status_code == 201
    anchor_id = created.json()["anchor_id"]

    # Re-key the pin to a different owner at the store layer (the request
    # itself is always the single test operator; the row's owner is what
    # the API filters on).
    with connect_write(db, purpose="test/rekey-owner") as con:
        con.execute(
            "UPDATE anchored_highlights SET owner_user_id = 'someone-else' WHERE anchor_id = ?",
            [anchor_id],
        )
    listing = client.get("/books/doc-anchor/anchors")
    assert listing.status_code == 200
    assert listing.json()["count"] == 0
    # Cross-owner delete is an idempotent 204 that deletes NOTHING.
    assert client.delete(f"/books/doc-anchor/anchors/{anchor_id}").status_code == 204
    con = connect_read(db)
    try:
        assert (
            con.execute(
                "SELECT COUNT(*) FROM anchored_highlights WHERE anchor_id = ?",
                [anchor_id],
            ).fetchone()[0]
            == 1
        )
    finally:
        con.close()


def test_get_anchors_escalates_to_reanchor_when_exact_fails(api_env) -> None:
    """The live exact check fails → the read escalates to the re-resolution
    pass under the write lock (the books.py:247 write-on-read precedent) and
    the stored status converges — drifted with quote kept."""
    db = api_env["db"]
    _seed_default_chunks(db)
    client = _client()
    created = client.post("/books/doc-anchor/anchors", json=_pin_payload())
    assert created.status_code == 201

    with connect_write(db, purpose="test/drift-the-passage") as con:
        con.execute(
            "UPDATE chunks SET text = ? WHERE chunk_id = ?",
            [
                "The first passage holds a NEW-LEAD-IN sentence worth remembering. "
                "A middle stretch of ordinary prose follows here. "
                "The last passage closes the book quietly.",
                "c-1",
            ],
        )
    listing = client.get("/books/doc-anchor/anchors")
    assert listing.status_code == 200
    anchor = listing.json()["anchors"][0]
    assert anchor["status"] == "drifted"
    assert anchor["anchor"]["quote"] == "sentence worth remembering"
    assert anchor["exact_valid"] is True  # the re-resolved location is exact


# ── Metadata-only: a non-servable document never stores a quote ────────────


def test_metadata_only_pin_on_non_servable_document(api_env) -> None:
    db = api_env["db"]
    _seed_book(
        db,
        document_id="doc-private",
        content_class="personal_reading",
        body=PRIVATE_BODY,
        chunks=[("p-1", PRIVATE_BODY, None)],
    )
    client = _client()
    created = client.post(
        "/books/doc-private/anchors",
        json={
            "quote": "private reading habits",
            "prefix": "their ",
            "suffix": ".",
            "source": "pin",
        },
    )
    assert created.status_code == 201
    anchor = created.json()
    assert anchor["servable_at_pin"] is False
    assert anchor["anchor"]["quote"] is None
    assert anchor["anchor"]["prefix"] is None
    assert anchor["anchor"]["suffix"] is None
    assert anchor["selection_text_sha256"]
    # And the ROW never stored the text — asserted at the DB layer.
    con = connect_read(db)
    try:
        raw = con.execute(
            "SELECT anchor_quote, anchor_prefix, anchor_suffix "
            "FROM anchored_highlights WHERE anchor_id = ?",
            [anchor["anchor_id"]],
        ).fetchone()
    finally:
        con.close()
    assert raw == (None, None, None)


# ── The anchor-map: ids/offsets/hashes only, gated like the body serve ─────


def test_anchor_map_carries_no_body_text(api_env) -> None:
    db = api_env["db"]
    _seed_default_chunks(db)
    client = _client()
    resp = client.get("/books/doc-anchor/anchor-map")
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == "doc-anchor"
    assert body["complete"] is True
    assert len(body["chunks"]) == 1
    chunk = body["chunks"][0]
    assert chunk["chunk_id"] == "c-1"
    assert chunk["section_path"] == "Page 1"
    assert chunk["body_start"] == 0
    assert chunk["body_end"] == len(BODY_TEXT)
    assert len(chunk["node_text_sha256"]) == 64
    # The manifest greps clean of every body sentence.
    text = json.dumps(body)
    for sentence in [
        "sentence worth remembering",
        "ordinary prose follows",
        "closes the book quietly",
    ]:
        assert sentence not in text


def test_anchor_map_403s_on_the_public_path_for_a_gated_book(api_env) -> None:
    db = api_env["db"]
    _seed_book(
        db,
        document_id="doc-gated",
        content_class="restricted_pending_opt_in",
        body="Gated body the public may not read.",
        chunks=[("g-1", "Gated body the public may not read.", None)],
    )
    client = _client()
    resp = client.get("/books/doc-gated/anchor-map")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "anchor_map_gated"
    # And the owner route refuses without the hardened owner signal.
    owner = client.get("/books/doc-gated/anchor-map/owner")
    assert owner.status_code == 403
    assert owner.json()["detail"] == "owner_read_required"


def test_anchor_map_owner_path_serves_owner_readable_book(api_env, monkeypatch) -> None:
    db = api_env["db"]
    _seed_book(
        db,
        document_id="doc-private",
        content_class="personal_reading",
        body=PRIVATE_BODY,
        chunks=[("p-1", PRIVATE_BODY, None)],
    )
    client = _client()
    # Without the owner signal: refused.
    assert client.get("/books/doc-private/anchor-map/owner").status_code == 403
    # The same authenticated-owner resolver books.py's own tests use, patched
    # on the ROUTER module's binding (the route resolves it there).
    import interfaces.research.api.book_anchor_routes as anchor_api

    monkeypatch.setattr(
        anchor_api,
        "_owner_read_policy_tag",
        lambda _request: books_api._OWNER_READ_POLICY_TAG,
    )
    resp = client.get("/books/doc-private/anchor-map/owner")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["chunks"]) == 1
    assert "private reading habits" not in json.dumps(body)


def test_anchor_map_404s_for_an_unknown_book(api_env) -> None:
    client = _client()
    assert client.get("/books/doc-missing/anchor-map").status_code == 404
    assert client.get("/books/doc-missing/anchors").status_code == 404


# ── The SPR-04 write-back + the explicit (metadata-only) pin form ──────────


def test_link_investigation_first_link_wins(api_env) -> None:
    db = api_env["db"]
    _seed_default_chunks(db)
    client = _client()
    created = client.post("/books/doc-anchor/anchors", json=_pin_payload())
    assert created.status_code == 201
    anchor_id = created.json()["anchor_id"]
    assert created.json()["investigation_id"] is None

    linked = client.patch(
        f"/books/doc-anchor/anchors/{anchor_id}",
        json={"investigation_id": "inv-spawned"},
    )
    assert linked.status_code == 200
    assert linked.json()["investigation_id"] == "inv-spawned"

    # Re-linking the SAME thread is the idempotent 200…
    again = client.patch(
        f"/books/doc-anchor/anchors/{anchor_id}",
        json={"investigation_id": "inv-spawned"},
    )
    assert again.status_code == 200
    # …but a DIFFERENT thread never overwrites (first link wins).
    conflict = client.patch(
        f"/books/doc-anchor/anchors/{anchor_id}",
        json={"investigation_id": "inv-other"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "anchor_already_linked"

    missing = client.patch(
        "/books/doc-anchor/anchors/ahl-missing",
        json={"investigation_id": "inv-x"},
    )
    assert missing.status_code == 404


def test_explicit_metadata_only_pin_form(api_env) -> None:
    """The client-resolved location (ids/numbers only — the withheld text
    never leaves the client): the server validates and, for a non-servable
    document, persists no quote."""
    db = api_env["db"]
    _seed_book(
        db,
        document_id="doc-private",
        content_class="personal_reading",
        body=PRIVATE_BODY,
        chunks=[("p-1", PRIVATE_BODY, None)],
    )
    client = _client()
    start = PRIVATE_BODY.index("private reading habits")
    end = start + len("private reading habits")
    created = client.post(
        "/books/doc-private/anchors",
        json={
            "node_id": "p-1",
            "start_scalar": start,
            "end_scalar": end,
            "source": "floatmenu_note",
        },
    )
    assert created.status_code == 201
    anchor = created.json()
    assert anchor["servable_at_pin"] is False
    assert anchor["anchor"]["quote"] is None
    assert anchor["anchor"]["node_id"] == "p-1"
    assert anchor["anchor"]["start_scalar"] == start

    # The same explicit form on a SERVABLE book derives + persists the
    # context from the server's own text.
    _seed_default_chunks(db)
    qstart = BODY_TEXT.index("sentence worth remembering")
    qend = qstart + len("sentence worth remembering")
    servable = client.post(
        "/books/doc-anchor/anchors",
        json={"node_id": "c-1", "start_scalar": qstart, "end_scalar": qend, "source": "pin"},
    )
    assert servable.status_code == 201
    assert servable.json()["anchor"]["quote"] == "sentence worth remembering"

    # Validation: offsets outside the chunk and a missing chunk refuse honestly.
    outside = client.post(
        "/books/doc-anchor/anchors",
        json={"node_id": "c-1", "start_scalar": 0, "end_scalar": len(BODY_TEXT) + 50, "source": "pin"},
    )
    assert outside.status_code == 422
    missing_chunk = client.post(
        "/books/doc-anchor/anchors",
        json={"node_id": "c-missing", "start_scalar": 0, "end_scalar": 2, "source": "pin"},
    )
    assert missing_chunk.status_code == 422
    conflict = client.post(
        "/books/doc-anchor/anchors",
        json=_pin_payload(node_id="c-1", start_scalar=0, end_scalar=2),
    )
    assert conflict.status_code == 422
    assert "anchor_location_conflicting" in conflict.json()["detail"]
