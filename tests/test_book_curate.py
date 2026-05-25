"""Read SPR-04 — prompt-to-curate over the servable corpus.

The load-bearing gate: curation ranks ONLY servable books. A gated book,
no matter how relevant, never appears in a reading list (it isn't
readable). Embedding similarity is a stub here (no sentence-transformers).
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.books import ingest as bingest
from substrate.books.curate import curate_reading_list
from substrate.graph.ops import insert_chunk, insert_document
from substrate.graph.schema import init_database


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) * (i + 1) for i, c in enumerate(text)) or 1
        return [
            float(h % 7) / 7.0, float((h >> 3) % 11) / 11.0,
            float((h >> 5) % 13) / 13.0, float((h >> 7) % 17) / 17.0,
        ]


@pytest.fixture
def db(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-curate-")
    db_path = os.path.join(tmp, "graph.duckdb")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmp, "events"))
    con = connect_write(db_path, purpose="curate-test")
    init_database(con)
    con.close()
    return db_path


def _book(db, document_id, *, content_class, chunk_text):
    con = connect_write(db, purpose="setup")
    try:
        insert_document(con, document_id=document_id, source_tier=2,
                        document_type="book", title=document_id.upper(), raw_text=chunk_text)
        insert_chunk(con, document_id=document_id, chunk_index=0, text=chunk_text,
                     token_count=5, embedding=StubEmbedding().encode(chunk_text))
        bingest.register_book(con, document_id=document_id, content_class=content_class)
    finally:
        con.close()


def test_curate_ranks_only_servable_books(db):
    _book(db, "doc-pd", content_class="public_domain", chunk_text="stoic philosophy on resilience")
    _book(db, "doc-licensed", content_class="opt_in_licensed", chunk_text="modern psychology of burnout")
    _book(db, "doc-gated", content_class="restricted_pending_opt_in", chunk_text="stoic philosophy on resilience")

    con = connect_read(db)
    try:
        results = curate_reading_list(con, "stoicism for burnout", model=StubEmbedding(), limit=10)
    finally:
        con.close()
    ids = {r.document_id for r in results}
    assert "doc-gated" not in ids, "a gated book was curated into a readable reading list"
    assert ids == {"doc-pd", "doc-licensed"}
    # Ranked by score descending.
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_curate_empty_prompt_returns_nothing(db):
    con = connect_read(db)
    try:
        assert curate_reading_list(con, "   ", model=StubEmbedding()) == []
    finally:
        con.close()


def test_curate_excludes_taken_down(db):
    from substrate.books import takedown

    _book(db, "doc-x", content_class="public_domain", chunk_text="quantum computing primer")
    con = connect_write(db, purpose="td")
    try:
        takedown.take_down(con, "doc-x", reason="dmca")
    finally:
        con.close()
    con = connect_read(db)
    try:
        results = curate_reading_list(con, "quantum", model=StubEmbedding())
    finally:
        con.close()
    assert all(r.document_id != "doc-x" for r in results)
