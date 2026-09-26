"""Reading-state bus route proofs (reading-global SPR-01).

FastAPI TestClient against a REAL DuckDB fixture (the api_env shape from
tests/test_book_anchor_routes.py): PUT → GET round-trip per owner, the
owner boundary, stale-revision 409 (never a silent clobber), and the empty
v1 prefs allowlist enforced at BOTH layers (API 422 + the DB CHECK). The
auth middleware's enforcement-disabled default stamps the single-operator
identity, so the requesting owner is the substrate's "__operator__" unless
a test re-keys a row at the store layer.
"""

from __future__ import annotations

import os
import tempfile

import duckdb
import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write
from substrate.graph import ensure_initialized
from substrate.graph.ops import insert_document


@pytest.fixture
def api_env(monkeypatch):
    # This is a substrate-free route fixture: ambient operator credentials on
    # a development workstation must not turn the hermetic TestClient into a
    # 401-only suite.
    for variable in (
        "ANTIEK_AUTH_SECRET",
        "ANTIEK_DEV_LOGIN_TOKEN",
        "ANTIEK_OPERATOR_EMAIL",
        "ANTIEK_OPERATOR_TOKEN",
        "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET",
    ):
        monkeypatch.delenv(variable, raising=False)
    tmpdir = tempfile.mkdtemp(prefix="reading-state-api-")
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


def _seed_book(db: str, document_id: str = "doc-bus") -> None:
    with connect_write(db, purpose="test/seed-bus-book") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="book",
            title="Bus Book",
            raw_text="A short book for the bus.",
            content_class="public_domain",
            on_conflict="ignore",
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, "
            "section_path, text, token_count) VALUES (?, ?, 0, 'Page 1', ?, 7)",
            [f"chunk-{document_id}", document_id, "A short book for the bus."],
        )


def _pin(client: TestClient, document_id: str = "doc-bus") -> str:
    response = client.post(
        f"/books/{document_id}/anchors",
        json={
            "quote": "short book",
            "prefix": "A ",
            "suffix": " for the bus.",
            "source": "pin",
        },
    )
    assert response.status_code == 201
    return str(response.json()["anchor_id"])


# ── Proof 1: the round-trip, the owner boundary, the concurrency rules ─────


def test_put_get_round_trip_per_owner(api_env) -> None:
    db = api_env["db"]
    _seed_book(db)
    client = _client()
    anchor_id = _pin(client)

    # No position recorded yet — an honest 404, never a fabricated page 0.
    missing = client.get("/books/doc-bus/reading-state")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "reading_state_not_found"

    # First write (revision 0 = the row does not exist yet) creates it.
    created = client.put(
        "/books/doc-bus/reading-state",
        json={"page_index": 3, "anchor_ref": anchor_id, "prefs": {}, "revision": 0},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["page_index"] == 3
    assert body["anchor_ref"] == anchor_id
    assert body["prefs"] == {}
    assert body["revision"] == 1

    # The round-trip reads it back; the next write carries the seen revision.
    got = client.get("/books/doc-bus/reading-state")
    assert got.status_code == 200
    assert got.json()["page_index"] == 3
    assert got.json()["revision"] == 1
    moved = client.put(
        "/books/doc-bus/reading-state",
        json={"page_index": 4, "revision": 1},
    )
    assert moved.status_code == 200
    assert moved.json()["page_index"] == 4
    assert moved.json()["revision"] == 2
    # anchor_ref defaults to null when omitted (refs, never content).
    assert moved.json()["anchor_ref"] is None


def test_anchor_ref_must_be_an_owned_anchor_on_this_document(api_env) -> None:
    db = api_env["db"]
    _seed_book(db)
    _seed_book(db, "doc-bus-2")
    client = _client()
    owned_anchor = _pin(client)
    other_document_anchor = _pin(client, "doc-bus-2")

    with connect_write(db, purpose="test/rekey-anchor-owner") as con:
        con.execute(
            "UPDATE anchored_highlights SET owner_user_id = 'someone-else' "
            "WHERE anchor_id = ?",
            [owned_anchor],
        )

    for invalid in (
        "A short book for the bus.",
        "short book",
        "ahl-0000000000000000",
        other_document_anchor,
        owned_anchor,
        "x" * 21,
    ):
        response = client.put(
            "/books/doc-bus/reading-state",
            json={"page_index": 3, "anchor_ref": invalid, "revision": 0},
        )
        assert response.status_code == 422
        if invalid == "short book":
            assert response.json()["detail"] == "anchor_ref_invalid"
        assert client.get("/books/doc-bus/reading-state").status_code == 404

    accepted = client.put(
        "/books/doc-bus/reading-state",
        json={"page_index": 3, "anchor_ref": None, "revision": 0},
    )
    assert accepted.status_code == 200
    assert accepted.json()["anchor_ref"] is None


def test_deleted_anchor_echo_keeps_next_page_turn_and_drops_ref(api_env) -> None:
    db = api_env["db"]
    _seed_book(db)
    client = _client()
    anchor_id = _pin(client)
    first = client.put(
        "/books/doc-bus/reading-state",
        json={"page_index": 3, "anchor_ref": anchor_id, "revision": 0},
    )
    assert first.status_code == 200
    assert client.delete(f"/books/doc-bus/anchors/{anchor_id}").status_code == 204

    changed_ref = client.put(
        "/books/doc-bus/reading-state",
        json={
            "page_index": 4,
            "anchor_ref": "ahl-0000000000000000",
            "revision": 1,
        },
    )
    assert changed_ref.status_code == 422
    assert client.get("/books/doc-bus/reading-state").json()["page_index"] == 3

    stale = client.put(
        "/books/doc-bus/reading-state",
        json={"page_index": 4, "anchor_ref": anchor_id, "revision": 0},
    )
    assert stale.status_code == 409

    moved = client.put(
        "/books/doc-bus/reading-state",
        json={"page_index": 4, "anchor_ref": anchor_id, "revision": 1},
    )
    assert moved.status_code == 200
    assert moved.json()["page_index"] == 4
    assert moved.json()["anchor_ref"] is None
    assert moved.json()["revision"] == 2
    got = client.get("/books/doc-bus/reading-state").json()
    assert got["page_index"] == 4
    assert got["anchor_ref"] is None


def test_second_owner_gets_no_row(api_env) -> None:
    """A position written by one owner is invisible to another."""
    db = api_env["db"]
    _seed_book(db)
    client = _client()
    created = client.put(
        "/books/doc-bus/reading-state",
        json={"page_index": 3, "revision": 0},
    )
    assert created.status_code == 200

    # Re-key the row to a different owner at the store layer (the request
    # itself is always the single test operator; the row's owner is what
    # the API filters on).
    with connect_write(db, purpose="test/rekey-owner") as con:
        con.execute(
            "UPDATE reading_state SET owner_user_id = 'someone-else' "
            "WHERE document_id = 'doc-bus'",
        )

    # The operator's GET now finds no row of THEIR OWN — the other owner's
    # position is not leaked, not even its existence beyond the 404 shape.
    assert client.get("/books/doc-bus/reading-state").status_code == 404


def test_stale_revision_is_a_409_and_the_row_is_unchanged(api_env) -> None:
    db = api_env["db"]
    _seed_book(db)
    client = _client()
    assert client.put(
        "/books/doc-bus/reading-state", json={"page_index": 3, "revision": 0}
    ).status_code == 200

    # A writer holding the stale revision 0 is refused — never a clobber.
    stale = client.put(
        "/books/doc-bus/reading-state", json={"page_index": 7, "revision": 0}
    )
    assert stale.status_code == 409
    assert "reading_state_stale_revision" in stale.json()["detail"]
    got = client.get("/books/doc-bus/reading-state").json()
    assert got["page_index"] == 3
    assert got["revision"] == 1

    # And a future revision on a non-existent row is equally stale.
    _seed_book(db, document_id="doc-bus-2")
    premature = client.put(
        "/books/doc-bus-2/reading-state", json={"page_index": 1, "revision": 3}
    )
    assert premature.status_code == 409


def test_non_empty_prefs_is_a_422_at_the_api_and_a_check_at_the_db(api_env) -> None:
    """The anti-smuggling rule, both layers: the v1 allowlist is EMPTY."""
    db = api_env["db"]
    _seed_book(db)
    client = _client()

    # Layer 1 — the API boundary refuses before the store runs.
    resp = client.put(
        "/books/doc-bus/reading-state",
        json={"page_index": 1, "prefs": {"font": "large"}, "revision": 0},
    )
    assert resp.status_code == 422
    assert "prefs_not_allowlisted" in resp.json()["detail"]
    assert client.get("/books/doc-bus/reading-state").status_code == 404

    # Layer 2 — a writer that skips the API hits the CHECK (the backstop).
    # The schema is initialized through the store's own write path first
    # (the table is additive and lazy, exactly like production).
    from substrate.books.reading_state import init_reading_state_schema

    with connect_write(db, purpose="test/prefs-check-init") as con:
        init_reading_state_schema(con)
    with pytest.raises(duckdb.ConstraintException), connect_write(
        db, purpose="test/prefs-check"
    ) as con:
        con.execute(
            "INSERT INTO reading_state (owner_user_id, document_id, "
            "page_index, prefs_json, revision) "
            "VALUES ('__operator__', 'doc-bus', 1, '{\"font\": \"large\"}', 1)",
        )

    # The lawful empty map stores the canonical '{}' the CHECK constrains.
    ok = client.put(
        "/books/doc-bus/reading-state", json={"page_index": 1, "prefs": {}, "revision": 0}
    )
    assert ok.status_code == 200
    assert ok.json()["prefs"] == {}


def test_negative_page_index_is_a_422(api_env) -> None:
    db = api_env["db"]
    _seed_book(db)
    client = _client()
    resp = client.put(
        "/books/doc-bus/reading-state", json={"page_index": -1, "revision": 0}
    )
    assert resp.status_code == 422


def test_unknown_book_is_a_404(api_env) -> None:
    api_env["db"]
    client = _client()
    assert client.get("/books/no-such-book/reading-state").status_code == 404
    assert (
        client.put(
            "/books/no-such-book/reading-state", json={"page_index": 0, "revision": 0}
        ).status_code
        == 404
    )
