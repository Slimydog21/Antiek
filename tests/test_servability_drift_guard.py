"""Gated-body-never-served drift guard (SPR-02 M4).

The §9.0 invariant is worthless as a comment; it must be PROVEN, and the proof
must go RED if a future edit lets a gated body leak. These tests:

  - construct a REAL gated work (body = a unique sentinel) and assert that
    sentinel appears in NONE of the public payloads — ``/library``, the
    ``/books`` list, the ``/books/{id}`` detail, and ``serve.py``'s output;
  - confirm ``servable_full_text`` is DERIVED from ``content_class`` (membership
    in SERVABLE_CONTENT_CLASSES), never read from a stored boolean — a case
    where a stale stored flag, if one existed, would disagree with the class,
    and the class wins;
  - DEMONSTRATE the guard actually guards: when the SAME body is registered
    under a servable class, the gated-body-absence assertion FAILS — so a
    future edit that marked a gated work servable, or let its body into a
    payload, turns this suite red.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.books import ingest as bingest
from substrate.books.model import BookAsset, get_book_asset
from substrate.books.serve import serve_full_text
from substrate.books.servability import (
    ServabilityStatus,
    is_servable_full_text,
    servability_of,
)
from substrate.constants import SERVABLE_CONTENT_CLASSES
from substrate.graph.ops import insert_document

# The full body of a gated book. If this string appears in ANY public payload
# the §9.0 gate has leaked. Unique so a substring search is unambiguous.
_GATED_BODY = "THE_WHOLE_COPYRIGHTED_BODY_OF_A_GATED_WORK_qpzm_" + ("lorem ipsum " * 200)


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-drift-guard-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    try:
        from substrate.graph import ensure_initialized

        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _seed_book(db_path, *, document_id, content_class, raw_text, title="A Work", author="Auth"):
    with connect_write(db_path, purpose="test:drift-guard-seed") as con:
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


def _client():
    from fastapi.testclient import TestClient

    from interfaces.research.api.app import create_app

    return TestClient(create_app(register_wrestling=False, register_providers=False))


def _body_appears_in_public_payloads(db_path, document_id, body) -> bool:
    """The guard predicate: does the gated body reach ANY public payload?

    Enumerates every leak surface by name — the /library catalog, the /books
    list, the /books/{id} detail, and serve.py's full-text output — and reports
    whether ``body`` appears in any of them. Used both to assert absence for a
    gated work and to DEMONSTRATE the guard goes red for a servable one."""
    client = _client()

    library = client.get("/library?filter=all").text
    books_list = client.get("/books?status=all").text
    detail = client.get(f"/books/{document_id}").text

    with connect_read(db_path) as con:
        served = serve_full_text(con, document_id)
    serve_text = served.full_text or ""

    return any(body in surface for surface in (library, books_list, detail, serve_text))


# ---------------------------------------------------------------------------
# The invariant: a gated body reaches NO public payload
# ---------------------------------------------------------------------------


def test_gated_body_absent_from_every_public_payload(isolated_db):
    _seed_book(
        isolated_db,
        document_id="gated-doc",
        content_class="restricted_pending_opt_in",
        raw_text=_GATED_BODY,
    )
    assert not _body_appears_in_public_payloads(isolated_db, "gated-doc", _GATED_BODY), (
        "gated body leaked into a public payload — §9.0 gate broken"
    )


def test_gated_body_absent_surface_by_surface(isolated_db):
    """The same invariant, asserted surface-by-surface so a regression names
    WHICH payload leaked."""
    _seed_book(
        isolated_db,
        document_id="gated-doc-2",
        content_class="restricted_pending_opt_in",
        raw_text=_GATED_BODY,
    )
    client = _client()
    assert _GATED_BODY not in client.get("/library?filter=all").text, "/library leaked"
    assert _GATED_BODY not in client.get("/books?status=all").text, "/books list leaked"
    assert _GATED_BODY not in client.get("/books/gated-doc-2").text, "/books detail leaked"
    with connect_read(isolated_db) as con:
        served = serve_full_text(con, "gated-doc-2")
    assert served.full_text is None, "serve.py served gated full text"
    # A bounded snippet is permitted (Authors Guild v. Google) but NOT the body.
    assert served.snippet is not None and len(served.snippet) < len(_GATED_BODY)


def test_gated_book_appears_flagged_as_metadata(isolated_db):
    """The gated work is NOT skipped from the catalog — it appears, flagged as
    gated metadata (body withheld). That is gated mass-ingest: present in the
    graph, body withheld."""
    _seed_book(
        isolated_db,
        document_id="gated-doc-3",
        content_class="restricted_pending_opt_in",
        raw_text=_GATED_BODY,
        title="A Findable Gated Title",
    )
    body = _client().get("/library?filter=gated").json()
    ids = {w["document_id"] for w in body["works"]}
    assert "gated-doc-3" in ids
    work = next(w for w in body["works"] if w["document_id"] == "gated-doc-3")
    assert work["servable_full_text"] is False
    assert work["servability"] == "gated_metadata_only"
    assert "full_text" not in work  # metadata only — no body field at all


# ---------------------------------------------------------------------------
# The guard actually guards — flipping to servable goes RED
# ---------------------------------------------------------------------------


def test_guard_goes_red_when_same_body_is_servable(isolated_db):
    """DEMONSTRATION (rigor #3): register the SAME body under a SERVABLE class.
    Now the body DOES reach the public serve path, so the gated-body-absence
    predicate returns True — i.e. the assertion in
    ``test_gated_body_absent_from_every_public_payload`` would FAIL. This proves
    the guard is not vacuous: if a future edit marked a gated work servable, the
    suite turns red here."""
    _seed_book(
        isolated_db,
        document_id="servable-doc",
        content_class="public_domain",  # the would-be drift: gated -> servable
        raw_text=_GATED_BODY,
    )
    assert _body_appears_in_public_payloads(isolated_db, "servable-doc", _GATED_BODY), (
        "a servable book's body must reach serve.py — if this is False the "
        "guard predicate is broken and the absence test above is vacuous"
    )


# ---------------------------------------------------------------------------
# servable_full_text is DERIVED, never stored (the -k derived gate)
# ---------------------------------------------------------------------------


def test_servable_full_text_is_derived_from_content_class():
    """``servable_full_text`` is computed from content_class membership in
    SERVABLE_CONTENT_CLASSES — not a stored column. A gated class derives False;
    each servable class derives True."""
    assert is_servable_full_text(servability_of("restricted_pending_opt_in")) is False
    assert is_servable_full_text(servability_of(None)) is False
    for cc in SERVABLE_CONTENT_CLASSES:
        assert is_servable_full_text(servability_of(cc)) is True


def test_servable_full_text_derived_not_a_stored_boolean(isolated_db):
    """There is no persisted ``servable_full_text`` / ``is_servable`` column the
    model reads. The flag is recomputed from (content_class, taken_down) on the
    BookAsset; we assert the columns the projection reads from are content_class
    + the takedown flag, and that no servability boolean column exists to read."""
    _seed_book(
        isolated_db,
        document_id="derived-doc",
        content_class="restricted_pending_opt_in",
        raw_text="gated body",
    )
    with connect_read(isolated_db) as con:
        cols = {
            row[1]
            for row in con.execute("PRAGMA table_info('documents')").fetchall()
        }
        cols |= {
            row[1]
            for row in con.execute("PRAGMA table_info('book_assets')").fetchall()
        }
        asset = get_book_asset(con, "derived-doc")
    # No stored servability boolean to drift from the class.
    assert "servable_full_text" not in cols
    assert "is_servable" not in cols
    # content_class is the column the derivation keys off.
    assert "content_class" in cols
    assert asset is not None
    assert asset.servable_full_text is False


def test_class_wins_over_a_stale_stored_flag():
    """If a stale stored boolean existed and DISAGREED with the class, the class
    must win. We model that disagreement directly: build a BookAsset whose
    content_class is gated, then prove its derived servable_full_text is False
    regardless of any external claim — the dataclass recomputes it in
    __post_init__ from the class, so there is no field a caller could set to
    override the derivation."""
    asset = BookAsset(
        document_id="stale-doc",
        title="t",
        author="a",
        content_class="restricted_pending_opt_in",
        ip_holder_id=None,
        page_count=1,
        pagination_scheme="pdf_page",
        cover_uri=None,
        toc=[],
        provenance=None,
        license_basis=None,
        taken_down=False,
        taken_down_at=None,
        takedown_reason=None,
        pre_takedown_content_class=None,
    )
    # init=False derived fields: cannot be supplied by the caller, so a "stored
    # True" can't be injected; the class governs.
    assert asset.servability is ServabilityStatus.GATED_METADATA_ONLY
    assert asset.servable_full_text is False
