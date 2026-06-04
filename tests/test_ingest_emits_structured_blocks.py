"""SPR-02 D2 — the M2/M3 mappers are WIRED into the running ingest paths.

Round 1 built ``arxiv_to_document`` / ``fetch_arxiv_document`` (M3) and
``pdf_bytes_to_document`` (M2) but never wired them into the adapters that
actually run on ingest, so no real arXiv or PDF ingest emitted the model. These
tests prove the wiring:

  * ``acquisition.arxiv.adapter.ingest_paper`` now passes ``structured_blocks``
    into ``insert_document`` (the arXiv ingest emits the typed-block Document);
  * ``acquisition.urls.adapter.ingest_url`` detects a PDF body and routes it to
    ``pdf_bytes_to_document``, emitting ``structured_blocks`` (the PDF-URL path
    emits the model, NOT a flat flatten of garbled binary);
  * both are BEST-EFFORT — a fetch/parse failure stores NULL blocks + logs and
    NEVER breaks ingest (the abstract / raw_text still lands; backfill upgrades
    it later).

NO LIVE NETWORK (rigor #1 / #4). The arXiv 429-ban history forbids hitting
arXiv/ar5iv in the suite. The arXiv test INJECTS the structured fetcher
(``fetch_structured=``) so the governed live egress is never opened here; the
PDF-URL test passes an already-fetched ``FetchedHtml`` whose body is a locally-
built PDF (no fetch). The live egress path IS wired + governed (through
``acquisition.arxiv.source_document.fetch_arxiv_document`` →
``arxiv_governed_client`` / ``governed_request``) — it is validated by injection,
not by hitting the banned endpoint.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime

import duckdb
import pytest

from acquisition.arxiv.adapter import ingest_paper
from acquisition.arxiv.client import ArxivPaper
from acquisition.books.public_domain import text_to_pdf
from acquisition.urls.adapter import ingest_url
from acquisition.urls.client import FetchedHtml
from substrate.contracts.document_model import (
    Document,
    DocumentAttribution,
    ParagraphBlock,
    TextSpan,
)
from processing.extraction.to_document_model import text_to_document


class _StubEmbedder:
    def encode(self, text: str) -> list[float]:
        v = [0.0] * 16
        v[abs(hash(text)) % 16] = 1.0
        return v


@pytest.fixture
def temp_substrate(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-spr02-d2-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    yield {"db_path": db_path}


def _read_structured_blocks(db_path: str, document_id: str) -> str | None:
    con = duckdb.connect(db_path, read_only=True)
    try:
        (sb,) = con.execute(
            "SELECT structured_blocks FROM documents WHERE document_id = ?",
            [document_id],
        ).fetchone()
    finally:
        con.close()
    return sb


def _paper(arxiv_id: str = "2310.12345") -> ArxivPaper:
    now = datetime(2024, 2, 15, 12, 0, 0, tzinfo=UTC)
    return ArxivPaper(
        arxiv_id=arxiv_id,
        version="v1",
        title="A Test Paper on Bounds",
        authors=["Jane Doe"],
        abstract="We bound the error and converge. " * 6,
        categories=["cs.AI"],
        primary_category="cs.AI",
        published_at=now,
        updated_at=now,
        abs_url=f"https://arxiv.org/abs/{arxiv_id}",
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
    )


# ───────────────────────────────────────────────────────────────────────────
# arXiv adapter (D2): ingest_paper passes structured_blocks at ingest, using an
# INJECTED governed-fetch seam (no live arXiv/ar5iv).
# ───────────────────────────────────────────────────────────────────────────


def test_arxiv_ingest_emits_structured_blocks_via_injected_fetch(temp_substrate):
    """``ingest_paper`` writes structured_blocks (the wired M3 model) into the
    documents row — proven with an INJECTED structured fetcher so NO network is
    touched (the 429-ban makes live arXiv/ar5iv unsafe in CI)."""
    fetch_calls: list[tuple[str, str, str | None]] = []

    def fake_fetch_structured(arxiv_id: str, document_id: str, title: str | None) -> str:
        fetch_calls.append((arxiv_id, document_id, title))
        # Mimic what fetch_arxiv_document returns: a serialized SPR-01 Document.
        doc = Document(
            id=document_id,
            title=title or "A Test Paper on Bounds",
            attribution=DocumentAttribution(source_url="https://arxiv.org/abs/2310.12345"),
            blocks=[ParagraphBlock(spans=[TextSpan(text="Structured arXiv body.")])],
        )
        return doc.model_dump_json()

    res = ingest_paper(
        _paper(),
        investigation_id="inv-d2-arxiv",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        fetch_structured=fake_fetch_structured,
    )

    # The wired fetch fired with the row's own document_id (model id == row id).
    assert fetch_calls == [("2310.12345", res.document_id, "A Test Paper on Bounds")]
    sb = _read_structured_blocks(temp_substrate["db_path"], res.document_id)
    assert sb is not None, "ingest_paper must persist structured_blocks (D2 wiring)"
    doc = Document.model_validate_json(sb)
    assert doc.id == res.document_id
    assert any(b.type == "paragraph" for b in doc.blocks)


def test_arxiv_ingest_uses_governed_default_fetcher_signature():
    """The DEFAULT structured fetcher is the governed source_document path (no
    second fetcher; rigor #4). We assert the wiring imports + calls
    ``fetch_arxiv_document`` (the governed-egress seam) rather than opening its
    own socket — by patching it and confirming the default fetcher delegates to
    it. (We never invoke the real governed fetch — that would hit arXiv.)"""
    from acquisition.arxiv import adapter as arxiv_adapter

    captured: dict = {}

    class _FakeExtraction:
        def __init__(self) -> None:
            self.document = Document(
                id="doc-arxiv-x",
                title="t",
                attribution=DocumentAttribution(),
                blocks=[ParagraphBlock(spans=[TextSpan(text="body")])],
            )

    def fake_fetch_arxiv_document(arxiv_id, *, document_id, title=None):
        captured["args"] = (arxiv_id, document_id, title)
        return _FakeExtraction()

    # The default fetcher imports fetch_arxiv_document lazily from
    # acquisition.arxiv.source_document; patch it there.
    import acquisition.arxiv.source_document as sd

    orig = sd.fetch_arxiv_document
    sd.fetch_arxiv_document = fake_fetch_arxiv_document
    try:
        out = arxiv_adapter._default_fetch_structured_blocks(
            "2310.55555", "doc-arxiv-x", "t",
        )
    finally:
        sd.fetch_arxiv_document = orig

    assert captured["args"] == ("2310.55555", "doc-arxiv-x", "t")
    assert Document.model_validate_json(out).id == "doc-arxiv-x"


def test_arxiv_ingest_structured_fetch_failure_is_best_effort(temp_substrate):
    """A structured-fetch failure (e.g. an ArxivBanned) must NOT break ingest:
    the abstract still lands, structured_blocks is NULL, a backfill can upgrade
    later. Mirrors the URL adapter's best-effort pattern."""

    def boom(arxiv_id: str, document_id: str, title: str | None) -> str:
        raise RuntimeError("ar5iv unreachable / banned")

    res = ingest_paper(
        _paper("2401.00001"),
        investigation_id="inv-d2-arxiv-fail",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        fetch_structured=boom,
    )

    # Ingest succeeded (the abstract row exists) but blocks are NULL (not broken).
    con = duckdb.connect(temp_substrate["db_path"], read_only=True)
    try:
        (raw_text, sb) = con.execute(
            "SELECT raw_text, structured_blocks FROM documents WHERE document_id = ?",
            [res.document_id],
        ).fetchone()
    finally:
        con.close()
    assert raw_text is not None and "Bounds" in raw_text  # abstract landed
    assert sb is None  # best-effort degrade to NULL, never a broken ingest


def test_arxiv_emit_structured_blocks_false_keeps_legacy_path(temp_substrate):
    """``emit_structured_blocks=False`` keeps the abstract-only behavior (a pure
    metadata sweep that must NOT touch ar5iv/arxiv.org) — structured_blocks NULL,
    and the structured fetcher is never consulted."""

    def must_not_call(*a, **k):  # pragma: no cover — asserted not called
        raise AssertionError("structured fetch must not run when disabled")

    res = ingest_paper(
        _paper("2402.00002"),
        investigation_id="inv-d2-arxiv-off",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        emit_structured_blocks=False,
        fetch_structured=must_not_call,
    )
    assert _read_structured_blocks(temp_substrate["db_path"], res.document_id) is None


# ───────────────────────────────────────────────────────────────────────────
# PDF-URL path (D2): a fetched PDF body routes to pdf_bytes_to_document and emits
# structured_blocks (NOT a flat flatten of garbled binary).
# ───────────────────────────────────────────────────────────────────────────


def _pdf_fetched(url: str, pdf_bytes: bytes, *, content_type: str) -> FetchedHtml:
    return FetchedHtml(
        requested_url=url,
        final_url=url,
        status_code=200,
        content_type=content_type,
        charset="utf-8",
        body=pdf_bytes,
    )


def _make_pdf() -> bytes:
    # A real PDF with enough words to clear MIN_INGEST_WORD_COUNT.
    body = "This is a synthetic PDF article body for the URL ingest path. " * 20
    return text_to_pdf(body, title="A Fetched PDF Article")


def test_pdf_url_ingest_emits_structured_blocks(temp_substrate):
    """A URL whose body is a PDF (declared content-type) emits structured_blocks
    via the M2 PDF extractor — the model, not a flat flatten of binary bytes."""
    url = "https://example.com/paper.pdf"
    res = ingest_url(
        url,
        investigation_id="inv-d2-pdf",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        fetched=_pdf_fetched(url, _make_pdf(), content_type="application/pdf"),
    )
    assert res.skipped_reason is None, "the PDF should clear the word-count gate"
    sb = _read_structured_blocks(temp_substrate["db_path"], res.document_id)
    assert sb is not None, "the PDF-URL path must persist structured_blocks (D2)"
    doc = Document.model_validate_json(sb)
    # The PDF extractor produces real blocks (headings/paragraphs), not a single
    # garbled string — at least one paragraph/heading must be present.
    assert any(b.type in ("heading", "paragraph") for b in doc.blocks)


def test_pdf_detected_by_magic_bytes_when_mislabeled(temp_substrate):
    """A PDF mislabeled as octet-stream is still routed to the PDF extractor via
    the %PDF- magic-byte floor (a server that omits application/pdf)."""
    url = "https://example.com/mislabeled"
    pdf = _make_pdf()
    assert pdf[:5] == b"%PDF-"
    res = ingest_url(
        url,
        investigation_id="inv-d2-pdf-magic",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        fetched=_pdf_fetched(url, pdf, content_type="application/octet-stream"),
    )
    sb = _read_structured_blocks(temp_substrate["db_path"], res.document_id)
    assert sb is not None
    assert Document.model_validate_json(sb).blocks  # real structure recovered


def test_html_body_unaffected_still_uses_text_path(temp_substrate):
    """A normal HTML body is NOT misrouted to the PDF path — it still flows
    through html_to_markdown → text_to_document (regression guard for the
    content-type/magic-byte gate)."""
    html = (
        b"<!DOCTYPE html><html><head><title>HTML Doc</title></head><body>"
        b"<article><h1>An HTML Heading</h1>"
        b"<p>" + (b"Plenty of real words in this article body. " * 8) + b"</p>"
        b"</article></body></html>"
    )
    url = "https://example.com/post"
    res = ingest_url(
        url,
        investigation_id="inv-d2-html",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        fetched=_pdf_fetched(url, html, content_type="text/html; charset=utf-8"),
    )
    sb = _read_structured_blocks(temp_substrate["db_path"], res.document_id)
    assert sb is not None
    doc = Document.model_validate_json(sb)
    kinds = {b.type for b in doc.blocks}
    assert "heading" in kinds and "paragraph" in kinds


def test_corrupt_pdf_is_best_effort_skipped_not_broken(temp_substrate):
    """A body that claims to be a PDF but is corrupt degrades to an empty model
    (the word-count gate then skips the row) — ingest never raises."""
    url = "https://example.com/corrupt.pdf"
    res = ingest_url(
        url,
        investigation_id="inv-d2-pdf-corrupt",
        db_path=temp_substrate["db_path"],
        embedder=_StubEmbedder(),
        fetched=_pdf_fetched(url, b"%PDF-1.4 not really a pdf", content_type="application/pdf"),
    )
    # Empty extraction → word-count gate skip; the run did not raise.
    assert res.skipped_reason is not None
