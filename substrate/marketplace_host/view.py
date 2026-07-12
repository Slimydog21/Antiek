"""HTML-first human view of a hosted book (PDF never required as view)."""

from __future__ import annotations

from typing import Any

from substrate.engagement_spine.project import project_to_html

from .library import HostStore


def _paragraphs_from_body(body: str) -> list[dict[str, Any]]:
    chunks = [p.strip() for p in body.replace("\r\n", "\n").split("\n\n") if p.strip()]
    if not chunks:
        chunks = [body.strip() or "(empty)"]
    nodes: list[dict[str, Any]] = []
    for chunk in chunks:
        # Bound individual projection nodes without discarding canonical text.
        # Split at whitespace where possible; a single enormous token falls
        # back to the hard boundary and remains lossless across nodes.
        remaining = chunk
        while remaining:
            split_at = min(len(remaining), 4000)
            if split_at < len(remaining):
                boundary = remaining.rfind(" ", 0, split_at + 1)
                if boundary > 0:
                    split_at = boundary
            text = remaining[:split_at]
            nodes.append(
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": text}],
                }
            )
            remaining = remaining[split_at:].lstrip(" ")
    return nodes


def project_hosted_book_html(
    document_id: str,
    *,
    store: HostStore,
) -> str:
    """Project a hosted document to self-contained HTML via engagement projection."""
    doc = store.get_document(document_id)
    if doc is None:
        raise KeyError(f"unknown document_id: {document_id}")
    title = str(doc.get("title") or document_id)
    body = str(doc.get("body_text") or "")
    license_class = str(doc.get("license_class") or "unknown")
    view_format = str(doc.get("view_format") or "html")
    if view_format.lower() == "pdf":
        raise RuntimeError("hosted book view_format must not be PDF")

    content: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": title}],
        },
        {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": f"License: {license_class} · view: HTML",
                }
            ],
        },
    ]
    content.extend(_paragraphs_from_body(body))
    doc_model: dict[str, Any] = {"type": "doc", "content": content}
    html = project_to_html(
        doc_model,
        document_id=document_id,
        creator="marketplace_host",
    )
    if not html or not html.strip():
        raise RuntimeError("HTML projection empty for hosted book")
    # Primary surface must not be a PDF document
    lowered = html.lstrip().lower()
    if lowered.startswith("%pdf"):
        raise RuntimeError("projection produced PDF bytes; HTML required")
    return html
