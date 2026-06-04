"""arXiv structured-source path tests (SPR-02 M3) — math as tex, PDF fallback.

HONESTY NOTE (rigor #1 / #4): no network. The arXiv 429-ban history forbids
hitting ``export.arxiv.org`` during a test run, and there is no local arXiv
paper. So these tests INJECT the fetchers (``fetch_html`` / ``fetch_pdf``) — the
default-suite path never opens a socket — and validate the mapping against a
local ar5iv-SHAPED HTML fixture (real LaTeXML structure: ``<math alttext=...>``
carrying the TeX) plus a locally-built PDF for the fallback. This proves the
mapping + path selection; it does NOT prove a live ar5iv fetch (that needs a real
paper and an open rate window — explicitly out of reach here, stated not faked).
"""

from __future__ import annotations

import io

import pytest

from acquisition.arxiv.source_document import fetch_arxiv_document
from processing.extraction.to_document_model import (
    ArxivSourceFetch,
    ar5iv_html_to_blocks,
    arxiv_to_document,
)
from substrate.contracts.document_model import Document


# An ar5iv-shaped (LaTeXML) HTML fragment. Equations carry the original TeX in
# ``alttext`` exactly as ar5iv emits them; headings are real <hN> tags.
_AR5IV_HTML = """\
<html><body>
<h1 class="ltx_title ltx_title_document">Bounding the Error</h1>
<section class="ltx_section">
  <h2 class="ltx_title ltx_title_section">Introduction</h2>
  <p class="ltx_p">The bound depends on
     <math alttext="\\epsilon" display="inline" class="ltx_Math"><mi>ε</mi></math>
     and converges.</p>
  <math alttext="\\mathcal{L} = \\sum_i \\|f(x_i) - y_i\\|^2" display="block" class="ltx_Math"><mrow></mrow></math>
  <h2 class="ltx_title ltx_title_section">Method</h2>
  <p class="ltx_p">We proceed in steps.</p>
  <ul class="ltx_itemize">
    <li class="ltx_item"><p class="ltx_p">Extract blocks.</p></li>
    <li class="ltx_item"><p class="ltx_p">Validate them.</p></li>
  </ul>
</section>
</body></html>
"""


def test_ar5iv_inline_math_is_tex_not_flattened():
    blocks = ar5iv_html_to_blocks(_AR5IV_HTML)
    paras = [b for b in blocks if b.type == "paragraph"]
    math_spans = [
        s for p in paras for s in p.spans if s.type == "math"
    ]
    assert any(s.tex == "\\epsilon" for s in math_spans), (
        "inline equation must carry its TeX, not be flattened to text"
    )


def test_ar5iv_display_math_becomes_math_block_with_tex():
    blocks = ar5iv_html_to_blocks(_AR5IV_HTML)
    math_blocks = [b for b in blocks if b.type == "math"]
    assert math_blocks, "display equation should become a MathBlock"
    assert math_blocks[0].tex == "\\mathcal{L} = \\sum_i \\|f(x_i) - y_i\\|^2"
    assert math_blocks[0].display is True


def test_ar5iv_headings_and_list_mapped():
    blocks = ar5iv_html_to_blocks(_AR5IV_HTML)
    kinds = [b.type for b in blocks]
    assert "heading" in kinds
    assert "list" in kinds
    h1 = next(b for b in blocks if b.type == "heading" and b.level == 1)
    assert "Bounding" in "".join(s.text for s in h1.spans if s.type == "text")


def test_structured_path_preferred_and_recorded():
    """When HTML is available, the structured path is chosen and recorded."""
    result = arxiv_to_document(
        ArxivSourceFetch(html=_AR5IV_HTML),
        document_id="doc-arxiv-1",
    )
    assert result.path == "structured_source"
    assert isinstance(result.document, Document)
    # Round-trips through JSON (the wire format).
    as_json = result.document.model_dump_json()
    assert Document.model_validate_json(as_json).model_dump_json() == as_json


def test_falls_back_to_pdf_when_no_structured_source():
    """No HTML → the M2 PDF path fires and is recorded as pdf_fallback."""
    pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, h - 72, "A PDF Only Paper")
    c.setFont("Helvetica", 11)
    c.drawString(72, h - 110, "Body text of the fallback paper.")
    c.save()

    result = arxiv_to_document(
        ArxivSourceFetch(pdf_bytes=buf.getvalue()),
        document_id="doc-arxiv-2",
    )
    assert result.path == "pdf_fallback"
    assert result.pdf_report is not None  # M2 confidence report present
    assert any(b.type == "heading" for b in result.document.blocks)


def test_fetch_arxiv_document_uses_injected_fetchers_no_network():
    """The wiring picks structured source when fetch_html returns HTML, and
    never calls fetch_pdf — proven with injected fetchers (NO network)."""
    pdf_called = {"v": False}

    def fake_html(arxiv_id: str) -> str:
        assert arxiv_id == "2310.00001"
        return _AR5IV_HTML

    def fake_pdf(arxiv_id: str) -> bytes:
        pdf_called["v"] = True
        return b"%PDF-should-not-be-used"

    result = fetch_arxiv_document(
        "2310.00001",
        document_id="doc-arxiv-3",
        fetch_html=fake_html,
        fetch_pdf=fake_pdf,
    )
    assert result.path == "structured_source"
    assert pdf_called["v"] is False, "structured source available — must not fetch PDF"


def test_fetch_arxiv_document_falls_back_when_html_absent():
    """fetch_html returns None (ar5iv 404) → wiring fetches PDF via injected
    fetcher and records pdf_fallback. Still no real network."""
    pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, h - 72, "Fallback Title")
    c.setFont("Helvetica", 11)
    c.drawString(72, h - 108, "Fallback body paragraph text here.")
    c.save()
    pdf = buf.getvalue()

    result = fetch_arxiv_document(
        "2310.99999",
        document_id="doc-arxiv-4",
        fetch_html=lambda _id: None,
        fetch_pdf=lambda _id: pdf,
    )
    assert result.path == "pdf_fallback"


def test_ar5iv_fetch_exception_degrades_to_pdf_not_abort():
    """An ar5iv fetch raising (e.g. ArxivBanned/network) must DEGRADE to the PDF
    path, not abort ingestion (rigor #4 — a ban pauses ar5iv, PDF is the floor)."""
    pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, h - 72, "Resilient Title")
    c.setFont("Helvetica", 11)
    c.drawString(72, h - 108, "Body after an ar5iv failure.")
    c.save()
    pdf = buf.getvalue()

    def boom(_id: str):
        raise RuntimeError("ar5iv unreachable")

    result = fetch_arxiv_document(
        "2310.00002",
        document_id="doc-arxiv-5",
        fetch_html=boom,
        fetch_pdf=lambda _id: pdf,
    )
    assert result.path == "pdf_fallback"
