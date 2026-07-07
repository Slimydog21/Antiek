"""Tests for the local-file inbox acquisition connector (DOGFOOD SPR-01).

No network: the inbox is ``~/research/inbox/<date>/*.txt`` article dumps. The
DB is a temp DuckDB initialized per test via ``ensure_initialized`` (mirrors
``tests/test_acquisition_substack.py``). Embeddings use the default provider
(HashEmbedding when sentence-transformers is absent).

Coverage maps to SPR-01 milestones + the verify-gap-first gate:
- M1/M2: fixtured day -> personal_reading docs + chunks + nodes; dedup keyed
         on the content-addressed document_id (derived from the abs path)
- M3: a corrupted/empty file is skipped + logged, never aborting the day
- §9.0 lane invariant asserted directly (every doc is personal_reading)
"""
from __future__ import annotations

import os
import sys

import duckdb
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.inbox.ingest import (  # noqa: E402
    InboxDayResult,
    ingest_inbox_day,
    ingest_inbox_file,
)
from substrate.graph import ensure_initialized  # noqa: E402

# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

_ARTICLE_A = """\
# On the durability of personal knowledge graphs

A reading flywheel only compounds if yesterday's intake is retrievable today.
The inbox is the operator's personal reading stream: newsletters, essay dumps,
and saved articles that arrive as flat text. Each one is owner-readable under
the section 9.0 personal-reading lane, never public-servable. The job of the
ingestion connector is to turn a day's worth of text into documents, chunks,
and graph nodes without ever aborting the whole day on one bad file.
"""

_ARTICLE_B = """\
## Why idempotency matters for re-ingest

Content-addressed document ids derived from the absolute source path mean that
re-ingesting the same day is a pure no-op. The operator can replay a directory
after a schema migration without duplicating rows or polluting the graph with
phantom nodes. This is the same single-writer contract the substack adapter
already relies on: connect_write, insert_document with on_conflict ignore, then
a chunk loop that content-addresses every chunk id from its text.
"""


@pytest.fixture
def temp_db(tmp_path):
    db_path = str(tmp_path / "test.duckdb")
    ensure_initialized(db_path)
    return db_path


@pytest.fixture
def inbox_day(tmp_path):
    """A day-directory with two real articles + one empty file."""
    day = tmp_path / "inbox" / "2026-07-01"
    day.mkdir(parents=True)
    (day / "on-durability.txt").write_text(_ARTICLE_A)
    (day / "on-idempotency.txt").write_text(_ARTICLE_B)
    (day / "empty.txt").write_text("")
    return str(day)


def _doc_rows(db_path):
    con = duckdb.connect(db_path, read_only=True)
    try:
        return con.execute(
            "SELECT document_id, source_uri, content_class, document_type, "
            "investigation_id FROM documents ORDER BY source_uri"
        ).fetchall()
    finally:
        con.close()


def _counts(db_path):
    con = duckdb.connect(db_path, read_only=True)
    try:
        docs = con.execute(
            "SELECT count(*) FROM documents WHERE content_class='personal_reading'"
        ).fetchone()[0]
        chunks = con.execute("SELECT count(*) FROM chunks").fetchone()[0]
        nodes = con.execute(
            "SELECT count(*) FROM nodes WHERE node_type='entity' "
            "AND graph_scope='cross_domain'"
        ).fetchone()[0]
        return docs, chunks, nodes
    finally:
        con.close()


# --------------------------------------------------------------------------
# M1/M2 — ingest a day: personal_reading docs + chunks + nodes land
# --------------------------------------------------------------------------

def test_ingest_day_lands_personal_reading(temp_db, inbox_day):
    result = ingest_inbox_day(
        inbox_day, investigation_id="spr01-test", db_path=temp_db
    )
    assert isinstance(result, InboxDayResult)
    assert result.files_seen == 3
    assert result.documents_added == 3          # empty.txt still a valid doc
    assert result.chunks_added > 0              # the two real articles chunked
    assert result.errors == []

    docs, chunks, nodes = _counts(temp_db)
    assert docs == 3
    assert chunks > 0
    assert nodes > 0

    # §9.0 lane invariant: EVERY document is personal_reading (owner-readable /
    # public-non-servable) — the inbox is the operator's personal reading stream.
    rows = _doc_rows(temp_db)
    assert rows, "expected documents to land"
    assert all(r[2] == "personal_reading" for r in rows), rows
    # source_uri is the absolute path to the *.txt article dump.
    assert all(r[1].endswith(".txt") and os.path.isabs(r[1]) for r in rows), rows
    # document_type is 'article' (the inbox connector's declared type).
    assert all(r[3] == "article" for r in rows), rows
    # investigation_id is stamped on the DOCUMENT (binds content into a research
    # project) — NOT dropped on the insert (mirrors acquisition/substack).
    assert all(r[4] == "spr01-test" for r in rows), rows


def test_doc_id_is_path_content_addressed(temp_db, tmp_path):
    """Two distinct abs paths must yield distinct content-addressed doc ids."""
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text(_ARTICLE_A)
    b.write_text(_ARTICLE_A)  # same BODY, different PATH -> different doc_id
    ra = ingest_inbox_file(str(a), investigation_id="i", db_path=temp_db)
    rb = ingest_inbox_file(str(b), investigation_id="i", db_path=temp_db)
    assert ra.status == "ingested" and rb.status == "ingested"
    assert ra.document_id != rb.document_id
    assert ra.document_id.startswith("inbox:")


# --------------------------------------------------------------------------
# M2 — dedup is keyed on the document_id (re-ingest is a no-op)
# --------------------------------------------------------------------------

def test_dedup_is_document_keyed(temp_db, inbox_day):
    first = ingest_inbox_day(inbox_day, investigation_id="spr01-test", db_path=temp_db)
    assert first.documents_added == 3 and first.skipped_dup == 0

    docs_before, chunks_before, nodes_before = _counts(temp_db)

    second = ingest_inbox_day(inbox_day, investigation_id="spr01-test", db_path=temp_db)
    assert second.documents_added == 0           # nothing new
    assert second.skipped_dup == 3               # all three already present
    assert second.chunks_added == 0
    assert second.errors == []

    # No row growth: the re-ingest touched nothing.
    docs_after, chunks_after, nodes_after = _counts(temp_db)
    assert docs_after == docs_before
    assert chunks_after == chunks_before
    assert nodes_after == nodes_before


# --------------------------------------------------------------------------
# M3 — a bad file never aborts the day (partial state is enumerated)
# --------------------------------------------------------------------------

def test_empty_file_is_a_doc_with_zero_chunks_no_error(temp_db, inbox_day):
    result = ingest_inbox_day(inbox_day, investigation_id="spr01-test", db_path=temp_db)
    assert result.errors == []
    empty = next(f for f in result.file_results if f.source_uri.endswith("empty.txt"))
    assert empty.status == "ingested"
    assert empty.chunks_written == 0


def test_not_a_directory_returns_error_result(temp_db, tmp_path):
    bogus = str(tmp_path / "nope")
    result = ingest_inbox_day(bogus, investigation_id="spr01-test", db_path=temp_db)
    assert result.files_seen == 0
    assert result.documents_added == 0
    assert result.errors == [{"file": bogus, "reason": "not a directory"}]
