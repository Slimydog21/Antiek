"""Tests for acquisition/books/ (Sprint 10 day 3-4).

Strategy:

Synthetic PDF generation is awkward without reportlab. We test the
reader's pure functions (cleanup + heading promotion +
metadata-field coercion + page-joining) directly, and exercise
``read_pdf`` / ``ingest_pdf`` by monkeypatching the ``PdfReader``
import inside ``acquisition.books.reader`` with a stub that emits
the page text we want. This verifies the read pipeline + the
adapter's graph writes without requiring synthetic PDF bytes.

Coverage:

A. Pure helpers:
   1. _clean_page_text joins soft-wrapped hyphens
   2. _clean_page_text collapses multi-space runs
   3. _clean_page_text strips trailing/leading blank lines
   4. _promote_headings lifts all-caps blocks bounded by blanks
   5. _promote_headings does NOT lift mid-paragraph shouts
   6. _metadata_field handles missing keys gracefully
   7. _join_pages_to_markdown drops empty pages, adds anchors

B. read_pdf via stub reader:
   8. metadata title + author surface
   9. multi-page concatenation
   10. empty pages dropped
   11. ReadResult.word_count = sum of page counts

C. book_doc_id:
   12. stable for same bytes
   13. differs for different bytes
   14. path source uses absolute path
   15. empty input raises

D. End-to-end ingest with stub reader:
   16. emits document.loaded (pdf media_type, page_count populated)
   17. writes documents + chunks + nodes
   18. low_word_count gate skips graph writes
   19. idempotent on re-ingest
   20. nodes carry source=book metadata
"""

from __future__ import annotations

import os
import sys
import tempfile
from types import SimpleNamespace
from typing import List

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.books import (
    book_doc_id,
    ingest_pdf,
    read_pdf,
)
from acquisition.books.reader import (
    _clean_page_text,
    _join_pages_to_markdown,
    _metadata_field,
    _promote_headings,
    PdfPage,
)


# ---------------------------------------------------------------------------
# Stub reader: a fake PdfReader the production import path can swap in
# ---------------------------------------------------------------------------


class _StubPage:
    def __init__(self, text: str):
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _StubReader:
    """Drop-in for pypdf.PdfReader. Constructed with a list of page
    texts + a metadata dict; production accepts BytesIO or a path,
    so the stub accepts anything and ignores it."""

    def __init__(self, _source=None, page_texts: List[str] = None, meta: dict = None):
        self._pages = [_StubPage(t) for t in (page_texts or [])]
        self._meta = SimpleNamespace(
            get=lambda key: (meta or {}).get(key),
        )

    @property
    def pages(self):
        return list(self._pages)

    @property
    def metadata(self):
        return self._meta


@pytest.fixture
def stub_reader_factory(monkeypatch):
    """Returns a function ``install(pages=..., meta=...)`` that
    monkeypatches the PdfReader symbol inside the reader module so
    the next read_pdf call uses the stub."""
    def install(pages: List[str], meta: dict = None):
        def factory(source):
            return _StubReader(source, page_texts=pages, meta=meta or {})
        monkeypatch.setattr(
            "acquisition.books.reader.PdfReader", factory,
        )
    return install


# ---------------------------------------------------------------------------
# A. Pure helpers
# ---------------------------------------------------------------------------


def test_clean_page_text_joins_soft_wrapped_hyphens():
    text = "ana-\nlysis"
    assert _clean_page_text(text) == "analysis"


def test_clean_page_text_collapses_multi_space():
    text = "alpha    beta   gamma"
    assert _clean_page_text(text) == "alpha beta gamma"


def test_clean_page_text_strips_top_bottom_blanks():
    text = "\n\n\nbody line\n\n\n"
    assert _clean_page_text(text) == "body line"


def test_promote_headings_lifts_blank_bounded_caps():
    text = "intro paragraph.\n\nCHAPTER ONE\n\nbody paragraph."
    out = _promote_headings(text)
    assert "# Chapter One" in out


def test_promote_headings_skips_mid_paragraph_shouts():
    text = "in the middle of a SHOUTY sentence here.\n"
    out = _promote_headings(text)
    assert "# " not in out


def test_metadata_field_missing_key():
    meta = SimpleNamespace(get=lambda k: None)
    assert _metadata_field(meta, "/Title") is None


def test_metadata_field_string_coerce():
    meta = SimpleNamespace(get=lambda k: "Some Title")
    assert _metadata_field(meta, "/Title") == "Some Title"


def test_join_pages_drops_empty():
    pages = [
        PdfPage(0, "first body", 2),
        PdfPage(1, "", 0),
        PdfPage(2, "third body", 2),
    ]
    out = _join_pages_to_markdown(pages, promote_headings=False)
    assert "## Page 1" in out
    assert "## Page 3" in out
    assert "## Page 2" not in out  # empty page dropped


# ---------------------------------------------------------------------------
# B. read_pdf via stub reader
# ---------------------------------------------------------------------------


def test_read_pdf_metadata_surfaces(stub_reader_factory):
    stub_reader_factory(
        pages=["body of page one"],
        meta={"/Title": "Stub Title", "/Author": "Stub Author"},
    )
    r = read_pdf(b"any-bytes")
    assert r.title == "Stub Title"
    assert r.author == "Stub Author"
    assert r.page_count == 1
    assert r.word_count >= 4


def test_read_pdf_multipage_concatenation(stub_reader_factory):
    stub_reader_factory(
        pages=[
            "first page content here.",
            "second page content here.",
            "third page content here.",
        ],
        meta={"/Title": "Three Pages"},
    )
    r = read_pdf(b"any")
    assert r.page_count == 3
    for marker in ("## Page 1", "## Page 2", "## Page 3"):
        assert marker in r.markdown


def test_read_pdf_drops_empty_pages(stub_reader_factory):
    stub_reader_factory(
        pages=["only content here.", "", "more content."],
        meta={},
    )
    r = read_pdf(b"any")
    assert r.page_count == 3  # raw page count includes blanks
    assert "## Page 1" in r.markdown
    assert "## Page 3" in r.markdown
    assert "## Page 2" not in r.markdown


def test_read_pdf_word_count_sums_pages(stub_reader_factory):
    stub_reader_factory(
        pages=["one two three", "four five"],
        meta={},
    )
    r = read_pdf(b"any")
    assert r.word_count == 5


# ---------------------------------------------------------------------------
# C. book_doc_id
# ---------------------------------------------------------------------------


def test_book_doc_id_bytes_stable():
    a = book_doc_id(b"hello pdf bytes here")
    b = book_doc_id(b"hello pdf bytes here")
    assert a == b


def test_book_doc_id_bytes_differ():
    a = book_doc_id(b"first")
    b = book_doc_id(b"second")
    assert a != b


def test_book_doc_id_path_uses_abspath():
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(b"x")
        f.flush()
        did = book_doc_id(f.name)
    assert did.startswith("doc-book-")


def test_book_doc_id_empty_raises():
    with pytest.raises(ValueError):
        book_doc_id(b"")
    with pytest.raises(ValueError):
        book_doc_id("")


# ---------------------------------------------------------------------------
# D. End-to-end ingest
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_substrate(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-books-test-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmpdir}


class _StubEmbedder:
    def encode(self, text: str) -> list[float]:
        h = abs(hash(text)) % 64
        v = [0.0] * 16
        v[h % 16] = 1.0
        return v


_LONG_PAGE = (
    "Long enough body to clear the MIN_INGEST_WORD_COUNT gate. "
    "Repeated text repeated text repeated text repeated text. "
    * 20
)


def test_ingest_emits_document_loaded(temp_substrate, stub_reader_factory):
    stub_reader_factory(
        pages=[_LONG_PAGE, _LONG_PAGE],
        meta={"/Title": "Ingest Title", "/Author": "Ingest Author"},
    )
    res = ingest_pdf(
        b"any-pdf-bytes",
        investigation_id="inv-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
    )
    assert res.document_loaded_event_id is not None
    assert res.title == "Ingest Title"
    assert res.author == "Ingest Author"
    assert res.page_count == 2


def test_ingest_writes_documents_chunks_nodes(temp_substrate, stub_reader_factory):
    import duckdb

    stub_reader_factory(pages=[_LONG_PAGE, _LONG_PAGE], meta={})
    res = ingest_pdf(
        b"some-pdf-bytes",
        investigation_id="inv-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
    )
    assert res.skipped_reason is None
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (doc_count,) = con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
        (chunk_count,) = con.execute(
            "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
    finally:
        con.close()
    assert doc_count == 1
    assert chunk_count == res.chunks_written
    assert chunk_count >= 1


def test_ingest_low_word_count_skips_writes(temp_substrate, stub_reader_factory):
    stub_reader_factory(pages=["tiny"], meta={})
    res = ingest_pdf(
        b"abc",
        investigation_id="inv-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
    )
    assert res.skipped_reason == "low_word_count"
    assert res.chunks_written == 0
    assert res.document_loaded_event_id is not None


def test_ingest_idempotent_on_rows(temp_substrate, stub_reader_factory):
    import duckdb

    stub_reader_factory(pages=[_LONG_PAGE], meta={})
    r1 = ingest_pdf(
        b"same-bytes",
        investigation_id="inv-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
    )
    r2 = ingest_pdf(
        b"same-bytes",
        investigation_id="inv-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
    )
    assert r1.document_id == r2.document_id
    assert r1.chunk_ids == r2.chunk_ids
    assert r1.document_loaded_event_id != r2.document_loaded_event_id
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        (doc_count,) = con.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = ?",
            [r1.document_id],
        ).fetchone()
    finally:
        con.close()
    assert doc_count == 1


def test_ingest_nodes_carry_source_book(temp_substrate, stub_reader_factory):
    import duckdb
    import json

    stub_reader_factory(pages=[_LONG_PAGE], meta={})
    res = ingest_pdf(
        b"bytes",
        investigation_id="inv-test",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
    )
    con = duckdb.connect(temp_substrate["db_path"])
    try:
        rows = con.execute(
            "SELECT metadata FROM nodes WHERE node_id = ANY(?)",
            [res.node_ids],
        ).fetchall()
    finally:
        con.close()
    metas = [json.loads(r[0]) if isinstance(r[0], str) else r[0] for r in rows]
    assert all(m.get("source") == "book" for m in metas)
    assert all(m.get("document_id") == res.document_id for m in metas)
