"""Read SPR-08 (backend) — spin-research seam: the gated-seed-no-leak
guard and the two-way passage↔research provenance link.

The mandatory gate (rigor #3): a research seeded from a gated book must
NEVER carry the book's full text — that would launder content past the
SPR-01 serve gate. The frontend (ResearchThis.tsx, return-to-reading,
e2e) layers on the unbuilt DRW reading surface and is out of scope here.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.books import ingest as bingest
from substrate.books.passage_research import (
    build_research_seed,
    link_passage_to_research,
    parse_passage_id,
    passage_for_research,
    passage_id,
    researches_for_passage,
)
from substrate.graph.ops import insert_document
from substrate.graph.schema import init_database

_GATED_BODY = "SECRET COPYRIGHTED PASSAGE THAT MUST NOT LEAK INTO A RESEARCH SEED " * 20
_PUBLIC_BODY = "Public domain passage text that may seed a research. " * 20


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-spin-")
    db_path = os.path.join(tmp, "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmp, "events"))
    con = connect_write(db_path, purpose="spin-test")
    init_database(con)
    con.close()
    return db_path


def _register(db, document_id, body, content_class=None):
    con = connect_write(db, purpose="setup")
    try:
        insert_document(con, document_id=document_id, source_tier=2,
                        document_type="book", title="A Book", author="Auth",
                        raw_text=body)
        bingest.register_book(con, document_id=document_id, content_class=content_class)
    finally:
        con.close()


# ── M1: the gated-seed-no-leak guard ────────────────────────────────


def test_gated_book_seed_carries_no_full_text(db):
    """THE mandatory gate: a research seeded from a gated book gets only
    metadata + bounded snippet, never the body — even when the caller
    hands us the full passage text."""
    _register(db, "doc-gated", _GATED_BODY)  # no license → gated
    con = connect_read(db)
    try:
        seed = build_research_seed(
            con, document_id="doc-gated", page_index=2,
            passage_text=_GATED_BODY,  # caller supplies full text...
        )
    finally:
        con.close()
    assert seed.gated is True
    # ...and the guard drops it: the full body never enters the seed.
    assert _GATED_BODY.strip() not in seed.seed_text
    assert len(seed.seed_text) < len(_GATED_BODY)
    # Metadata context is still present so the research has a topic.
    assert "A Book" in seed.seed_text


def test_servable_book_seed_carries_passage(db):
    _register(db, "doc-public", _PUBLIC_BODY, content_class="public_domain")
    con = connect_read(db)
    try:
        seed = build_research_seed(
            con, document_id="doc-public", page_index=0,
            passage_text="the selected sentence to research",
        )
    finally:
        con.close()
    assert seed.gated is False
    assert "the selected sentence to research" in seed.seed_text


def test_taken_down_book_seed_is_empty_of_body(db):
    """A taken-down book exposes nothing — its seed has no body at all."""
    from substrate.books import takedown
    _register(db, "doc-td", _PUBLIC_BODY, content_class="public_domain")
    con = connect_write(db, purpose="td")
    try:
        takedown.take_down(con, "doc-td", reason="dmca")
    finally:
        con.close()
    con = connect_read(db)
    try:
        seed = build_research_seed(con, document_id="doc-td", page_index=0,
                                   passage_text=_PUBLIC_BODY)
    finally:
        con.close()
    assert seed.gated is True
    assert _PUBLIC_BODY.strip() not in seed.seed_text


def test_seed_unknown_book_raises(db):
    con = connect_read(db)
    try:
        with pytest.raises(ValueError, match="not a registered book"):
            build_research_seed(con, document_id="doc-nope", page_index=0)
    finally:
        con.close()


# ── M4: two-way provenance link ─────────────────────────────────────


def test_passage_id_round_trips():
    pid = passage_id("doc-book-1", 7)
    assert pid == "passage:doc-book-1:p7"
    assert parse_passage_id(pid) == ("doc-book-1", 7)
    assert parse_passage_id("not-a-passage") is None


def test_spin_research_endpoint_gate_safe(db):
    """The /books/{id}/spin-research endpoint builds the seed server-side:
    a gated book's full text never enters the research seed, even when the
    client posts the passage body."""
    from fastapi.testclient import TestClient

    from interfaces.research.api.app import create_app

    _register(db, "doc-gated-api", _GATED_BODY)  # gated default
    client = TestClient(create_app(register_wrestling=False, register_providers=False, cors_origins=[]))
    resp = client.post(
        "/books/doc-gated-api/spin-research",
        json={"page_index": 1, "passage_text": _GATED_BODY},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["gated"] is True
    assert body["investigation_id"].startswith("inv-")
    assert _GATED_BODY.strip() not in body["seed_preview"]  # full body never seeded
    # The two-way link was recorded.
    assert researches_for_passage("doc-gated-api", 1) == [body["investigation_id"]]


def test_spin_research_endpoint_can_export_html_artifact_shell(db, monkeypatch):
    """Reading highlight → research should be able to open HTML asset + twin immediately.

    The export is still no-spend/no-provider and must preserve the gated seed
    guard: the artifact shell may include the safe seed preview/question, never
    the gated passage body supplied by the client.
    """
    from fastapi.testclient import TestClient

    from interfaces.research.api.app import create_app

    arts = os.path.join(os.path.dirname(db), "artifacts")
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", arts)
    _register(db, "doc-gated-export", _GATED_BODY)  # gated default
    client = TestClient(create_app(register_wrestling=False, register_providers=False, cors_origins=[]))
    resp = client.post(
        "/books/doc-gated-export/spin-research",
        json={
            "page_index": 2,
            "passage_text": _GATED_BODY,
            "export_artifact": True,
        },
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["artifact_path"]
    assert body["twin_notes_path"]
    assert os.path.isfile(body["artifact_path"])
    assert os.path.isfile(body["twin_notes_path"])
    artifact = Path(body["artifact_path"]).read_text(encoding="utf-8")
    twin = Path(body["twin_notes_path"]).read_text(encoding="utf-8")
    assert _GATED_BODY.strip() not in artifact
    assert _GATED_BODY.strip() not in twin
    assert "ResearchArtifact twin notes" in twin
    assert "A Book" in artifact


def test_spin_research_endpoint_unknown_book_404(db):
    from fastapi.testclient import TestClient

    from interfaces.research.api.app import create_app

    client = TestClient(create_app(register_wrestling=False, register_providers=False, cors_origins=[]))
    resp = client.post("/books/doc-nope/spin-research", json={"page_index": 0})
    assert resp.status_code == 404


def test_two_way_link_between_passage_and_research(db):
    link_passage_to_research(
        document_id="doc-book-1", page_index=3, investigation_id="inv-child-1",
    )
    link_passage_to_research(
        document_id="doc-book-1", page_index=3, investigation_id="inv-child-2",
    )
    # Forward: the passage shows its spawned researches.
    spawned = researches_for_passage("doc-book-1", 3)
    assert set(spawned) == {"inv-child-1", "inv-child-2"}
    # Backward: the research links back to its originating passage.
    assert passage_for_research("inv-child-1") == ("doc-book-1", 3)
    assert passage_for_research("inv-unrelated") is None
