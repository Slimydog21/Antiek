"""Persistence tests for the store-both structured model (SPR-02 M4).

The M4 gate: the structured Document is persisted via the ONE sanctioned writer
(``insert_document``) ALONGSIDE raw_text (store-both), content_class is stamped
NOT NULL (deny-by-default preserved), the original (raw_text) is retrievable for
"view original", and ingestion uses the single write lock. No second writer, no
rights-gate self-check raised.
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from acquisition.urls.adapter import ingest_url
from acquisition.urls.client import FetchedHtml
from substrate.contracts.document_model import Document


_HTML = b"""<!DOCTYPE html>
<html lang="en"><head>
  <meta charset="utf-8"><title>Plain Title</title>
  <meta property="og:title" content="Structured Title">
</head><body>
  <article>
    <h1>Article Heading</h1>
    <p>First substantive paragraph with enough words to clear the ingest gate
    threshold so the adapter writes the document to the graph and chunks it.</p>
    <h2>A Subsection</h2>
    <p>Second paragraph adding more detail so the structured model has multiple
    blocks of real content to persist alongside the raw text body.</p>
    <p>Third paragraph so the word count comfortably clears the minimum.</p>
  </article>
</body></html>"""


class _StubEmbedder:
    def encode(self, text: str) -> list[float]:
        v = [0.0] * 16
        v[abs(hash(text)) % 16] = 1.0
        return v


@pytest.fixture
def temp_substrate(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-spr02-test-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir}


def _fetched():
    return FetchedHtml(
        requested_url="https://example.com/post",
        final_url="https://example.com/post",
        status_code=200,
        content_type="text/html; charset=utf-8",
        charset="utf-8",
        body=_HTML,
    )


def _ingest(db_path):
    return ingest_url(
        "https://example.com/post",
        investigation_id="inv-spr02",
        db_path=db_path,
        embedder=_StubEmbedder(),
        fetched=_fetched(),
    )


def test_store_both_structured_blocks_and_raw_text(temp_substrate):
    """Both the structured model AND raw_text are persisted on the same row."""
    import duckdb

    res = _ingest(temp_substrate["db_path"])
    assert res.skipped_reason is None
    con = duckdb.connect(temp_substrate["db_path"], read_only=True)
    try:
        row = con.execute(
            "SELECT raw_text, structured_blocks, content_class "
            "FROM documents WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
    finally:
        con.close()
    raw_text, structured_blocks, content_class = row
    # view-original source preserved.
    assert raw_text is not None and "Article Heading" in raw_text
    # structured model persisted.
    assert structured_blocks is not None


def test_persisted_structured_blocks_is_a_valid_document(temp_substrate):
    """The persisted structured_blocks deserializes to a valid SPR-01 Document
    with real heading + paragraph blocks (reads as a document)."""
    import duckdb

    res = _ingest(temp_substrate["db_path"])
    con = duckdb.connect(temp_substrate["db_path"], read_only=True)
    try:
        (sb,) = con.execute(
            "SELECT structured_blocks FROM documents WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
    finally:
        con.close()
    doc = Document.model_validate_json(sb)
    kinds = {b.type for b in doc.blocks}
    assert "heading" in kinds
    assert "paragraph" in kinds
    assert doc.id == res.document_id


def test_content_class_stamped_not_null_deny_by_default(temp_substrate):
    """content_class is NOT NULL — the deny-by-default stamping is preserved
    unchanged by the store-both change (a web_article lands personal_reading)."""
    import duckdb

    res = _ingest(temp_substrate["db_path"])
    con = duckdb.connect(temp_substrate["db_path"], read_only=True)
    try:
        (cc,) = con.execute(
            "SELECT content_class FROM documents WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
    finally:
        con.close()
    assert cc is not None
    assert cc == "personal_reading"  # the §9.0 owner-read lane for third-party


def test_get_structured_blocks_helper_round_trips(temp_substrate):
    """The read helper returns the stored JSON, which round-trips to a Document."""
    import duckdb

    from substrate.graph.ops import get_structured_blocks

    res = _ingest(temp_substrate["db_path"])
    con = duckdb.connect(temp_substrate["db_path"], read_only=True)
    try:
        sb = get_structured_blocks(con, res.document_id)
    finally:
        con.close()
    assert sb is not None
    doc = Document.model_validate_json(sb)
    assert doc.id == res.document_id


def test_set_structured_blocks_uses_write_lock(temp_substrate):
    """set_structured_blocks requires a LockedConnection (single-writer) — a raw
    duckdb connection is rejected (the only-writer invariant is enforced)."""
    import duckdb

    from substrate.graph.ops import set_structured_blocks

    res = _ingest(temp_substrate["db_path"])
    raw = duckdb.connect(temp_substrate["db_path"])
    try:
        with pytest.raises(TypeError):
            set_structured_blocks(raw, res.document_id, "{}")
    finally:
        raw.close()


def test_no_structured_blocks_is_additive_not_required(temp_substrate):
    """insert_document without structured_blocks still works (existing callers
    unchanged); the column is NULL and the row is otherwise identical."""
    import duckdb

    from runtime.db_lock import connect_write
    from substrate.graph import ensure_initialized
    from substrate.graph.ops import insert_document

    db_path = temp_substrate["db_path"]
    ensure_initialized(db_path)
    with connect_write(db_path, purpose="test") as con:
        insert_document(
            con,
            document_id="doc-no-sb",
            source_tier=4,
            document_type="paper",  # NOT third-party → content_class stays NULL
            raw_text="plain body",
        )
    con = duckdb.connect(db_path, read_only=True)
    try:
        (sb,) = con.execute(
            "SELECT structured_blocks FROM documents WHERE document_id = 'doc-no-sb'"
        ).fetchone()
    finally:
        con.close()
    assert sb is None  # additive — absent when not provided
