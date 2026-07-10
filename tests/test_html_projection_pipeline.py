from __future__ import annotations

import hashlib
import io

import duckdb
import pytest
from pypdf import PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from services.html_projection.gate import assert_script_free
from substrate.contracts.html_projection import HtmlProjectionContract, derive_projection_id
from substrate.reading.projection import ProjectionStore
from substrate.reading.projection.pdf_adapter import (
    MAX_PAGE_CHARACTERS,
    MAX_PAGES,
    MAX_SOURCE_BYTES,
    convert_pdf,
)
from substrate.reading.projection.pipeline import (
    finalize_projection,
    persist_prepared_projection,
    prepare_projection,
)


def _pdf(*pages: str) -> bytes:
    buffer = io.BytesIO()
    output = canvas.Canvas(buffer, pagesize=letter, invariant=True)
    for text in pages:
        output.drawString(72, 720, text)
        output.showPage()
    output.save()
    return buffer.getvalue()


def _queued(data: bytes) -> HtmlProjectionContract:
    identity = {
        "source_asset_id": "asset-1", "source_document_id": "document-1",
        "source_sha256": hashlib.sha256(data).hexdigest(), "converter_id": "pypdf",
        "converter_version": "1", "sanitizer_policy": "born-antiek",
        "sanitizer_version": "1",
    }
    return HtmlProjectionContract(
        **identity, projection_id=derive_projection_id(**identity), status="queued"
    )


def test_two_page_pdf_is_deterministic_safe_and_page_aware() -> None:
    data = _pdf("Alpha <script>alert(1)</script>", "Beta & conclusion")
    first = prepare_projection(_queued(data), data)
    second = prepare_projection(_queued(data), data)
    assert first == second
    assert first.html_bytes is not None
    assert hashlib.sha256(first.html_bytes).hexdigest() == first.html_sha256
    rendered = first.html_bytes.decode()
    assert_script_free(rendered)
    assert 'data-source-page="1"' in rendered and 'data-source-page="2"' in rendered
    assert "&lt;script&gt;" in rendered and "<script" not in rendered
    assert [mapping.source_locator.kind for mapping in first.anchor_mappings] == [
        "pdf_page_bbox", "text", "pdf_page_bbox", "text"
    ]
    assert all(mapping.html_anchor_id in rendered for mapping in first.anchor_mappings)
    lowered = rendered.lower()
    for forbidden in (" onload=", "javascript:", "http://", "https://", "<object", "<embed", "<iframe", "data:"):
        assert forbidden not in lowered


def test_hash_mismatch_rejected_before_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    data = _pdf("original")
    monkeypatch.setattr(
        "substrate.reading.projection.pipeline.convert_pdf",
        lambda *_: pytest.fail("parser invoked"),
    )
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        prepare_projection(_queued(data), b"different")


@pytest.mark.parametrize("data", [b"not a pdf secret", b"%PDF-1.7 truncated secret"])
def test_bad_pdf_has_closed_failure_without_leak(data: bytes) -> None:
    result = prepare_projection(_queued(data), data)
    assert result.terminal_status == "failed"
    assert result.html_bytes is None
    assert result.machine_detail == "invalid_pdf"
    assert "secret" not in repr(result)


def test_textless_pdf_requires_ocr() -> None:
    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(buffer)
    data = buffer.getvalue()
    result = prepare_projection(_queued(data), data)
    assert [target.status for target in result.lifecycle_targets] == ["extracting", "ocr_required"]
    assert result.html_bytes is None and result.html_sha256 is None


def test_page_failure_never_publishes_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    import pypdf

    real_reader = pypdf.PdfReader

    class BrokenPage:
        def extract_text(self) -> str:
            raise RuntimeError("provider payload secret")

    class Reader:
        def __init__(self, stream: object) -> None:
            parsed = real_reader(stream)
            self.pages = [parsed.pages[0], BrokenPage()]

    data = _pdf("safe", "broken")
    monkeypatch.setattr(pypdf, "PdfReader", Reader)
    result = prepare_projection(_queued(data), data)
    assert result.terminal_status == "failed" and result.html_bytes is None
    assert result.machine_detail == "page_extraction_failed"
    assert result.evidence_count == 1 and "secret" not in repr(result)


def test_conversion_precedes_store_access_and_replay_is_idempotent() -> None:
    data = _pdf("Prepared outside transaction")
    queued = _queued(data)

    prepared = prepare_projection(queued, data)
    finalized = finalize_projection(prepared, "objects/document-1.html")
    assert [target.status for target in finalized.lifecycle_targets] == [
        "extracting", "sanitizing", "ready"
    ]
    con = duckdb.connect(":memory:")
    store = ProjectionStore(con)
    con.execute("BEGIN TRANSACTION")
    assert persist_prepared_projection(store, queued, finalized).status == "ready"
    assert persist_prepared_projection(store, queued, finalized).status == "ready"
    con.execute("COMMIT")
    assert store.load(queued.projection_id).hosted_html_sha256 == prepared.html_sha256

    assert finalize_projection(finalized, "objects/document-1.html") == finalized
    with pytest.raises(ValueError, match="different locator"):
        finalize_projection(finalized, "objects/other.html")


def test_persistence_resumes_from_an_exact_intermediate_state() -> None:
    data = _pdf("Resume after a process crash")
    queued = _queued(data)
    finalized = finalize_projection(prepare_projection(queued, data), "objects/resume.html")
    con = duckdb.connect(":memory:")
    store = ProjectionStore(con)
    store.claim(queued)
    store.transition(finalized.lifecycle_targets[0])

    assert persist_prepared_projection(store, queued, finalized).status == "ready"


def test_resource_limits_fail_closed_without_parser_or_source_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = b"%PDF-1.7 secret" + b"x" * MAX_SOURCE_BYTES
    contract = _queued(data)
    monkeypatch.setattr(
        "pypdf.PdfReader", lambda *_: pytest.fail("oversized source reached parser")
    )
    result = convert_pdf(data, contract)
    assert result.outcome == "failed" and result.reason == "resource_limit_exceeded"
    assert "secret" not in repr(result)


@pytest.mark.parametrize(
    ("pages", "text"),
    [([object()] * (MAX_PAGES + 1), ""), ([object()], "x" * (MAX_PAGE_CHARACTERS + 1))],
)
def test_page_and_extracted_text_limits_fail_closed(
    monkeypatch: pytest.MonkeyPatch, pages: list[object], text: str,
) -> None:
    class Page:
        def extract_text(self) -> str:
            return text

    class Reader:
        def __init__(self, _stream: object) -> None:
            self.pages = pages if len(pages) > 1 else [Page()]

    data = _pdf("bounded")
    monkeypatch.setattr("pypdf.PdfReader", Reader)
    result = convert_pdf(data, _queued(data))
    assert result.outcome == "failed" and result.reason == "resource_limit_exceeded"


def test_cumulative_text_limit_and_unicode_offsets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Page:
        def __init__(self, text: str) -> None:
            self.text = text

        def extract_text(self) -> str:
            return self.text

    class Reader:
        def __init__(self, _stream: object) -> None:
            self.pages = [Page("Über"), Page("À demain")]

    data = _pdf("bounded")
    monkeypatch.setattr("pypdf.PdfReader", Reader)
    result = convert_pdf(data, _queued(data))
    text_locators = [
        mapping.source_locator
        for mapping in result.anchor_mappings
        if mapping.source_locator.kind == "text"
    ]
    assert [(locator.start, locator.end) for locator in text_locators] == [(0, 4), (5, 13)]

    monkeypatch.setattr("substrate.reading.projection.pdf_adapter.MAX_TOTAL_CHARACTERS", 10)
    limited = convert_pdf(data, _queued(data))
    assert limited.outcome == "failed" and limited.reason == "resource_limit_exceeded"
