"""Deterministic, page-aware PDF to born-Antiek HTML conversion."""

from __future__ import annotations

import hashlib
import html
import io
import re
from dataclasses import dataclass
from typing import Literal

from acquisition.openaccess.pdf_detect import assert_pdf
from services.html_projection.gate import ScriptViolation, assert_script_free
from substrate.contracts.html_projection import (
    AnchorMapping,
    HtmlProjectionContract,
    PdfPageLocator,
    TextLocator,
    derive_anchor_id,
)

AdapterOutcome = Literal["ready", "ocr_required", "failed"]
AdapterReason = Literal[
    "invalid_pdf", "page_extraction_failed", "no_meaningful_text", "script_gate_rejected",
    "resource_limit_exceeded",
]

MAX_SOURCE_BYTES = 100 * 1024 * 1024
MAX_PAGES = 2_000
MAX_PAGE_CHARACTERS = 1_000_000
MAX_TOTAL_CHARACTERS = 20_000_000


@dataclass(frozen=True)
class PdfAdapterResult:
    outcome: AdapterOutcome
    html_bytes: bytes | None = None
    anchor_mappings: tuple[AnchorMapping, ...] = ()
    reason: AdapterReason | None = None
    page_count: int = 0
    failed_page_count: int = 0


def convert_pdf(source_bytes: bytes, contract: HtmlProjectionContract) -> PdfAdapterResult:
    """Convert PDF bytes without persistence, I/O callbacks, or partial success."""
    if len(source_bytes) > MAX_SOURCE_BYTES:
        return PdfAdapterResult(outcome="failed", reason="resource_limit_exceeded")
    try:
        assert_pdf(source_bytes)
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(source_bytes))
    except Exception:
        # Deliberately closed: parser/provider exception strings and source bytes
        # must never become lifecycle evidence.
        return PdfAdapterResult(outcome="failed", reason="invalid_pdf")

    try:
        page_count = len(reader.pages)
    except Exception:
        return PdfAdapterResult(outcome="failed", reason="invalid_pdf")
    if page_count > MAX_PAGES:
        return PdfAdapterResult(
            outcome="failed", reason="resource_limit_exceeded", page_count=page_count,
        )

    pages: list[tuple[int, tuple[str, ...]]] = []
    failures = 0
    total_characters = 0
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            failures += 1
            continue
        if len(text) > MAX_PAGE_CHARACTERS or total_characters + len(text) > MAX_TOTAL_CHARACTERS:
            return PdfAdapterResult(
                outcome="failed", reason="resource_limit_exceeded", page_count=page_count,
            )
        total_characters += len(text)
        paragraphs = tuple(_paragraphs(text))
        pages.append((page_number, paragraphs))
    if failures:
        return PdfAdapterResult(
            outcome="failed", reason="page_extraction_failed",
            page_count=page_count, failed_page_count=failures,
        )
    if not any(paragraphs for _, paragraphs in pages):
        return PdfAdapterResult(
            outcome="ocr_required", reason="no_meaningful_text", page_count=page_count
        )

    mappings: list[AnchorMapping] = []
    body: list[str] = []
    text_offset = 0
    for page_number, paragraphs in pages:
        page_locator = PdfPageLocator(page=page_number, x0="0", y0="0", x1="1", y1="1")
        page_anchor = derive_anchor_id(contract.projection_id, page_locator)
        mappings.append(AnchorMapping(
            source_locator=page_locator, state="resolved", html_anchor_id=page_anchor
        ))
        body.append(f'<section id="{page_anchor}" data-source-page="{page_number}">')
        body.append(f"<h2>Page {page_number}</h2>")
        for paragraph_number, paragraph in enumerate(paragraphs, start=1):
            encoded = paragraph.encode("utf-8")
            locator = TextLocator(
                start=text_offset, end=text_offset + len(paragraph),
                text_sha256=hashlib.sha256(encoded).hexdigest(),
            )
            anchor = derive_anchor_id(contract.projection_id, locator)
            mappings.append(AnchorMapping(
                source_locator=locator, state="resolved", html_anchor_id=anchor
            ))
            body.append(
                f'<p id="{anchor}" data-source-page="{page_number}" '
                f'data-source-paragraph="{paragraph_number}">{html.escape(paragraph)}</p>'
            )
            text_offset += len(paragraph) + 1
        body.append("</section>")
    document = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="antiek-document-id" content="{html.escape(contract.source_document_id, quote=True)}">'
        f'<meta name="antiek-projection-id" content="{html.escape(contract.projection_id, quote=True)}">'
        "<title>Antiek PDF projection</title></head><body><main>"
        + "".join(body) + "</main></body></html>"
    )
    try:
        assert_script_free(document)
    except ScriptViolation:
        return PdfAdapterResult(
            outcome="failed", reason="script_gate_rejected", page_count=page_count
        )
    return PdfAdapterResult(
        outcome="ready", html_bytes=document.encode("utf-8"),
        anchor_mappings=tuple(mappings), page_count=page_count,
    )


def _paragraphs(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return [" ".join(block.split()) for block in re.split(r"\n\s*\n", normalized) if block.strip()]


__all__ = ["AdapterOutcome", "AdapterReason", "PdfAdapterResult", "convert_pdf"]
