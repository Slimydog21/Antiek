"""Durable document.loaded emitter shared by hosted acquisition routes."""

from __future__ import annotations

from typing import Literal

from acquisition.documents import ExtractedDocument
from substrate.event_log import emit_typed, trajectory
from substrate.schemas import DocumentLoadedPayload


def emit_document_loaded(
    investigation_id: str,
    document_id: str,
    extracted: ExtractedDocument,
    size_bytes: int,
    source_uri: str | None,
) -> str:
    """Append once and recover the receipt after a host-store checkpoint crash."""
    for row in trajectory(investigation_id):
        payload = row.get("payload") if isinstance(row, dict) else None
        if (
            row.get("action_type") == "document.loaded"
            and row.get("document_id") == document_id
            and isinstance(payload, dict)
            and payload.get("content_hash") == extracted.canonical_content_hash
        ):
            prior_event_id = str(row.get("event_id") or "").strip()
            if prior_event_id:
                return prior_event_id
    media_type: Literal["pdf", "markdown"] = (
        "pdf" if extracted.source_format == "pdf" else "markdown"
    )
    event_id = emit_typed(
        investigation_id,
        DocumentLoadedPayload(
            media_type=media_type,
            content_hash=extracted.canonical_content_hash,
            size_bytes=size_bytes,
            title=extracted.title,
            page_count=extracted.page_count,
            source_uri=source_uri,
        ),
        document_id=document_id,
        role="acquisition",
        policy_id="services/hosted_documents",
    )
    if event_id is None:
        raise RuntimeError("event log is disabled; hosted document was not persisted")
    if not any(row.get("event_id") == event_id for row in trajectory(investigation_id)):
        raise RuntimeError("document.loaded append was not durably observable")
    return event_id


__all__ = ["emit_document_loaded"]
