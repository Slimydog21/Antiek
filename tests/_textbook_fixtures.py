"""Shared offline fixtures for the open-textbook connector tests (SPR-05).

NO live HTTP. ``FakeClient`` records canned JSON-by-URL and bytes-by-URL with
the SAME surface the real ``acquisition.textbooks.ThrottledClient`` exposes
(``get_json`` / ``get_bytes``), so the full ingest path runs offline:
discover -> classify() -> fetch + extraction gate -> read/chunk/embed/graph ->
§9.0 register. ``make_pdf`` mints a real multi-page PDF (reportlab) so the
reader produces non-empty markdown above the word gate. ``HTML_LANDING_PAGE``
is the bytes a publisher landing page serves where a PDF was expected (starts
``b'<!DO'``).
"""

from __future__ import annotations

import io
import os
import sys
import tempfile
from typing import Optional

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.textbooks import SourceError


def make_pdf(title: str, body: str, *, pages: int = 3) -> bytes:
    """A small but real multi-page PDF with extractable text + a title."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setTitle(title)
    for page in range(pages):
        text = c.beginText(72, 720)
        text.textLine(title)
        for i in range(40):  # enough words to clear MIN_INGEST_WORD_COUNT
            text.textLine(f"Page {page + 1} line {i}: {body}")
        c.drawText(text)
        c.showPage()
    c.save()
    return buf.getvalue()


# A publisher/landing-page HTML body served 200-OK where a PDF was expected —
# the exact 6/15-OA-landing-pages failure. Bytes start b'<!DO'.
HTML_LANDING_PAGE = (
    b"<!DOCTYPE html>\n<html><head><title>Download</title></head>"
    b"<body><h1>Click here to download the book</h1></body></html>"
)

assert HTML_LANDING_PAGE.startswith(b"<!DO")


class FakeClient:
    """Records canned JSON-by-URL and bytes-by-URL. Same surface the real
    ``ThrottledClient`` exposes. Never touches the network."""

    def __init__(self, *, json_by_url=None, bytes_by_url=None):
        self._json = json_by_url or {}
        self._bytes = bytes_by_url or {}
        self.json_calls: list[str] = []
        self.bytes_calls: list[str] = []

    def get_json(self, url: str, *, params: Optional[dict] = None) -> dict:
        self.json_calls.append(url)
        if url not in self._json:
            raise SourceError(f"no canned json for {url}")
        return self._json[url]

    def get_bytes(self, url: str) -> bytes:
        self.bytes_calls.append(url)
        if url not in self._bytes:
            raise SourceError(f"download failed (no canned bytes) for {url}")
        return self._bytes[url]


class StubEmbedder:
    """Deterministic tiny embedding so the graph-write path runs fast offline."""

    def encode(self, text: str) -> list[float]:
        h = abs(hash(text)) % 64
        v = [0.0] * 16
        v[h % 16] = 1.0
        return v


@pytest.fixture
def temp_substrate(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-textbook-test-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    yield {"db_path": db_path, "events_dir": events_dir, "tmpdir": tmpdir}
