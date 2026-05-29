"""Read SPR-09 — library catalog endpoint (GET /library).

Mechanical gates: pagination, the servable|gated|all filter, title/author
substring search, and the §9.0 invariant — a gated work appears as METADATA
only (flagged), its body text NEVER in the list payload.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app

# A sentinel that must never appear in any /library payload (it is the body of
# a gated book). If it leaks, the §9.0 gate is broken.
_GATED_BODY = "THE_ENTIRE_COPYRIGHTED_BODY_OF_A_GATED_BOOK_xyzzy"


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-library-api-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    try:
        from substrate.graph import ensure_initialized

        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _client():
    return TestClient(create_app(register_wrestling=False, register_providers=False))


def _seed_book(
    db_path: str,
    *,
    document_id: str,
    title: str,
    author: str,
    content_class: str,
    raw_text: str,
):
    from runtime.db_lock import connect_write
    from substrate.books import ingest as bingest
    from substrate.graph.ops import insert_document

    with connect_write(db_path, purpose="test:seed_book") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="book",
            title=title,
            author=author,
            raw_text=raw_text,
        )
        bingest.register_book(con, document_id=document_id, content_class=content_class)


def _seed_corpus(db_path: str, n_servable: int = 3):
    # Servable public-domain books.
    for i in range(n_servable):
        _seed_book(
            db_path,
            document_id=f"pd-{i}",
            title=f"Meditations Volume {i}",
            author="Marcus Aurelius",
            content_class="public_domain",
            raw_text=f"stoic body text {i}",
        )
    # One gated book — its body must never appear in /library.
    _seed_book(
        db_path,
        document_id="gated-1",
        title="A Gated Modern Treatise",
        author="Living Author",
        content_class="restricted_pending_opt_in",
        raw_text=_GATED_BODY,
    )


# ── Empty state ──────────────────────────────────────────────────────


def test_library_empty(isolated_db):
    resp = _client().get("/library")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"works": [], "total": 0, "page": 1, "page_size": 20}


# ── Default (all) lists servable + gated, each flagged ───────────────


def test_library_all_flags_each_work(isolated_db):
    _seed_corpus(isolated_db, n_servable=3)
    resp = _client().get("/library?filter=all")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 4
    by_id = {w["document_id"]: w for w in body["works"]}
    assert by_id["pd-0"]["servable_full_text"] is True
    assert by_id["gated-1"]["servable_full_text"] is False
    assert by_id["gated-1"]["servability"] == "gated_metadata_only"


# ── Filter: servable-only / gated-only ───────────────────────────────


def test_library_filter_servable_excludes_gated(isolated_db):
    _seed_corpus(isolated_db, n_servable=3)
    body = _client().get("/library?filter=servable").json()
    ids = {w["document_id"] for w in body["works"]}
    assert "gated-1" not in ids
    assert all(w["servable_full_text"] for w in body["works"])
    assert body["total"] == 3


def test_library_filter_gated_only(isolated_db):
    _seed_corpus(isolated_db, n_servable=3)
    body = _client().get("/library?filter=gated").json()
    ids = {w["document_id"] for w in body["works"]}
    assert ids == {"gated-1"}
    assert body["works"][0]["servable_full_text"] is False


# ── Search: case-insensitive substring over title + author ───────────


def test_library_search_matches_title(isolated_db):
    _seed_corpus(isolated_db, n_servable=3)
    body = _client().get("/library?search=gated").json()
    assert {w["document_id"] for w in body["works"]} == {"gated-1"}
    assert body["total"] == 1


def test_library_search_matches_author_case_insensitive(isolated_db):
    _seed_corpus(isolated_db, n_servable=3)
    body = _client().get("/library?search=AURELIUS").json()
    assert {w["document_id"] for w in body["works"]} == {"pd-0", "pd-1", "pd-2"}


# ── Pagination ───────────────────────────────────────────────────────


def test_library_pagination(isolated_db):
    _seed_corpus(isolated_db, n_servable=5)  # 5 servable + 1 gated = 6
    p1 = _client().get("/library?page=1&page_size=4").json()
    assert p1["total"] == 6
    assert len(p1["works"]) == 4
    assert p1["page"] == 1 and p1["page_size"] == 4
    p2 = _client().get("/library?page=2&page_size=4").json()
    assert p2["total"] == 6
    assert len(p2["works"]) == 2
    # Disjoint pages — no overlap, full coverage.
    ids1 = {w["document_id"] for w in p1["works"]}
    ids2 = {w["document_id"] for w in p2["works"]}
    assert ids1.isdisjoint(ids2)
    assert len(ids1 | ids2) == 6


def test_library_page_beyond_end_is_empty(isolated_db):
    _seed_corpus(isolated_db, n_servable=2)
    body = _client().get("/library?page=99&page_size=10").json()
    assert body["works"] == []
    assert body["total"] == 3


# ── §9.0 — gated body NEVER in any payload ───────────────────────────


def test_gated_body_absent_from_every_payload(isolated_db):
    _seed_corpus(isolated_db, n_servable=3)
    for url in ("/library?filter=all", "/library?filter=gated", "/library?search=gated"):
        resp = _client().get(url)
        assert resp.status_code == 200
        assert _GATED_BODY not in resp.text, f"gated body leaked in {url}"
    # And no payload carries a raw_text / full_text field at all.
    body = _client().get("/library?filter=all").json()
    for w in body["works"]:
        assert "raw_text" not in w
        assert "full_text" not in w
