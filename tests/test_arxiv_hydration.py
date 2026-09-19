from __future__ import annotations

import hashlib
import io

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from acquisition.arxiv.pdf_fetch import FetchedPdf
from substrate.engagement_spine.arxiv_hydration import hydrate_arxiv_body
from substrate.marketplace_host import InMemoryHostStore, project_hosted_book_html


def _paper_pdf() -> bytes:
    buf = io.BytesIO()
    page = canvas.Canvas(buf, pagesize=letter)
    text = page.beginText(48, 740)
    for line in range(8):
        text.textLine(
            "Governed research paper body with enough canonical words for extraction "
            f"and provenance verification line {line}."
        )
    page.drawText(text)
    page.save()
    return buf.getvalue()


def _policy() -> dict[str, object]:
    return {
        "governor": "host_global_arxiv_rate_governor",
        "min_spacing_s": 3.0,
        "default_ban_backoff_s": 1800.0,
        "redirect_policy": "every_arxiv_hop_governed",
        "rate_limit_policy": "persist_429_ban_and_do_not_retry",
    }


def test_missing_fetcher_is_typed_unavailable_and_zero_request() -> None:
    outcome = hydrate_arxiv_body(
        arxiv_id="2402.03300",
        owner_id="alice",
        investigation_id="inv",
        title="Paper",
        store=InMemoryHostStore(),
        fetch_body=None,
        emit_document_loaded=lambda *args: "forbidden",
    )
    assert outcome.hydrated is False
    assert outcome.status == "body_unavailable"
    assert outcome.receipt["request_attempted"] is False
    assert outcome.receipt["reason"] == "body_fetcher_not_installed"


def test_fetch_failure_is_typed_unavailable_without_retry() -> None:
    calls = 0

    def fail_once(_arxiv_id: str) -> FetchedPdf:
        nonlocal calls
        calls += 1
        raise RuntimeError("429")

    outcome = hydrate_arxiv_body(
        arxiv_id="2402.03300",
        owner_id="alice",
        investigation_id="inv",
        title="Paper",
        store=InMemoryHostStore(),
        fetch_body=fail_once,
        emit_document_loaded=lambda *args: "forbidden",
    )
    assert calls == 1
    assert outcome.status == "body_unavailable"
    assert outcome.receipt["reason"] == "RuntimeError"


def test_real_body_hosts_owner_bound_canonical_html_with_exact_receipt() -> None:
    raw = _paper_pdf()
    digest = hashlib.sha256(raw).hexdigest()
    store = InMemoryHostStore()
    events: list[str] = []

    def fetch(arxiv_id: str) -> FetchedPdf:
        return FetchedPdf(
            arxiv_id=arxiv_id,
            source_url=f"https://arxiv.org/pdf/{arxiv_id}",
            content=raw,
            sha256=digest,
            byte_size=len(raw),
            policy_receipt=_policy(),
        )

    def emit(_investigation_id, document_id, *_args):
        events.append(document_id)
        return "evt-arxiv-body"

    outcome = hydrate_arxiv_body(
        arxiv_id="2402.03300",
        owner_id="alice",
        investigation_id="inv",
        title="Governed Paper",
        store=store,
        fetch_body=fetch,
        emit_document_loaded=emit,
    )
    assert outcome.hydrated is True
    assert outcome.document is not None
    assert events == [outcome.document.document_id]
    assert outcome.receipt["source_sha256"] == digest
    assert outcome.receipt["canonical_content_hash"]
    assert outcome.receipt["owner_bound"] is True
    stored = store.get_document(outcome.document.document_id)
    assert stored is not None
    assert stored["owner_id"] == "alice"
    assert stored["license_class"] == "personal_reading"
    assert stored["provenance"]["arxiv_id"] == "2402.03300"
    html = project_hosted_book_html(outcome.document.document_id, store=store)
    assert "Governed research paper body" in html
    assert "%PDF" not in html


def test_forged_fetch_receipt_is_rejected_before_storage() -> None:
    raw = _paper_pdf()
    store = InMemoryHostStore()

    def forged(arxiv_id: str) -> FetchedPdf:
        return FetchedPdf(
            arxiv_id=arxiv_id,
            source_url="https://evil.example/paper.pdf",
            content=raw,
            sha256="0" * 64,
            byte_size=len(raw) + 1,
            policy_receipt=_policy(),
        )

    with pytest.raises(ValueError, match="digest or byte size"):
        hydrate_arxiv_body(
            arxiv_id="2402.03300",
            owner_id="alice",
            investigation_id="inv",
            title="Paper",
            store=store,
            fetch_body=forged,
            emit_document_loaded=lambda *args: "forbidden",
        )
    assert store.list_membership("alice") == []


def test_persistence_failure_propagates_instead_of_claiming_unavailable() -> None:
    raw = _paper_pdf()

    def fetched(arxiv_id: str) -> FetchedPdf:
        return FetchedPdf(
            arxiv_id=arxiv_id,
            source_url=f"https://arxiv.org/pdf/{arxiv_id}",
            content=raw,
            sha256=hashlib.sha256(raw).hexdigest(),
            byte_size=len(raw),
            policy_receipt=_policy(),
        )

    with pytest.raises(RuntimeError, match="event persistence failed"):
        hydrate_arxiv_body(
            arxiv_id="2402.03300",
            owner_id="alice",
            investigation_id="inv",
            title="Paper",
            store=InMemoryHostStore(),
            fetch_body=fetched,
            emit_document_loaded=lambda *args: (_ for _ in ()).throw(
                RuntimeError("event persistence failed")
            ),
        )
