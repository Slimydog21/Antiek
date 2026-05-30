"""Shared fixtures + fakes for the SPR-06 PD-connector tests.

NO live network: a ``FakeFetcher`` records canned JSON/text/bytes by URL,
exposing the same ``get_json`` / ``get_text`` / ``get_bytes`` surface as the
real ``ThrottledFetcher``. Real PDF bytes are minted with reportlab so the FULL
ingest path runs offline (read → chunk → embed → graph write → §9.0 servability
registration) and tests assert on actual DuckDB rows + the resolved verdict.
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
from typing import Optional

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.books.pd_connector_base import FetchError


class FakeFetcher:
    """Records canned JSON-by-URL, text-by-URL, and bytes-by-URL. Same surface
    as the real ``ThrottledFetcher`` (``get_json`` / ``get_text`` /
    ``get_bytes``). A missing URL raises ``FetchError`` so a connector's
    per-item isolation is exercised honestly."""

    def __init__(self, *, json_by_url=None, text_by_url=None, bytes_by_url=None):
        self._json = json_by_url or {}
        self._text = text_by_url or {}
        self._bytes = bytes_by_url or {}
        self.json_calls: list[str] = []
        self.text_calls: list[str] = []
        self.bytes_calls: list[str] = []

    def get_json(self, url: str, *, params: Optional[dict] = None) -> dict:
        self.json_calls.append(url)
        if url not in self._json:
            raise FetchError(f"no canned json for {url}")
        return self._json[url]

    def get_text(self, url: str, *, params: Optional[dict] = None) -> str:
        self.text_calls.append(url)
        if url not in self._text:
            raise FetchError(f"no canned text for {url}")
        return self._text[url]

    def get_bytes(self, url: str, *, params: Optional[dict] = None) -> bytes:
        self.bytes_calls.append(url)
        if url not in self._bytes:
            raise FetchError(f"download failed (no canned bytes) for {url}")
        return self._bytes[url]


def make_pdf(title: str, body: str, *, pages: int = 3) -> bytes:
    """Mint a small but real multi-page PDF with extractable text + title, so
    read_pdf/pypdf produces non-empty markdown above the word gate."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setTitle(title)
    for page in range(pages):
        text = c.beginText(72, 720)
        text.textLine(title)
        for i in range(40):
            text.textLine(f"Page {page + 1} line {i}: {body}")
        c.drawText(text)
        c.showPage()
    c.save()
    return buf.getvalue()


class StubEmbedder:
    def encode(self, text: str) -> list[float]:
        h = abs(hash(text)) % 64
        v = [0.0] * 16
        v[h % 16] = 1.0
        return v


@pytest.fixture
def stub_embedder():
    return StubEmbedder()


@pytest.fixture
def temp_substrate(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-pd6-test-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmpdir}


def book_asset_row(db_path: str, document_id: str):
    """(content_class, license_basis, raw_text) for a document, or None."""
    import duckdb

    con = duckdb.connect(db_path)
    try:
        row = con.execute(
            "SELECT d.content_class, b.license_basis, d.raw_text "
            "FROM documents d JOIN book_assets b ON d.document_id = b.document_id "
            "WHERE d.document_id = ?",
            [document_id],
        ).fetchone()
    finally:
        con.close()
    return row


def count_servable_book_assets(db_path: str) -> int:
    """How many book_assets resolve to a servable full-text content_class."""
    import duckdb

    from substrate.constants import SERVABLE_CONTENT_CLASSES

    con = duckdb.connect(db_path)
    try:
        rows = con.execute(
            "SELECT d.content_class FROM documents d "
            "JOIN book_assets b ON d.document_id = b.document_id"
        ).fetchall()
    finally:
        con.close()
    return sum(1 for (cc,) in rows if cc in SERVABLE_CONTENT_CLASSES)
