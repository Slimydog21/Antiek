"""Owner-bound canonical document ingest shared by Wrestle and Marketplace."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from acquisition.documents import ExtractedDocument, extract_document_bytes
from substrate.marketplace_host.library import HostStore

LicenseClass = Literal["private_upload", "public_domain", "purchased"]
EmitDocumentLoaded = Callable[[str, str, ExtractedDocument, int, str | None], str]

_INGEST_LOCK = threading.RLock()


@dataclass(frozen=True)
class HostAuthorization:
    license_class: LicenseClass
    entitlement_id: str | None = None

    def validate(self) -> None:
        if self.license_class == "purchased" and not (self.entitlement_id or "").strip():
            raise ValueError("purchased content requires entitlement_id")
        if self.license_class != "purchased" and self.entitlement_id is not None:
            raise ValueError("entitlement_id is only valid for purchased content")


@dataclass(frozen=True)
class HostedDocumentResult:
    document_id: str
    owner_id: str
    state: Literal["ready", "non_viewable"]
    source_byte_hash: str
    canonical_content_hash: str
    source_format: str
    title: str
    body_text: str
    document_loaded_event_id: str | None
    already_hosted: bool
    non_viewable_reason: str | None


def _document_id(owner_id: str, source_byte_hash: str) -> str:
    digest = hashlib.sha256(
        f"hosted-document:v1:{owner_id}:{source_byte_hash}".encode()
    ).hexdigest()[:24]
    return f"hdoc_{digest}"


def _result(doc: dict[str, Any], *, already_hosted: bool) -> HostedDocumentResult:
    return HostedDocumentResult(
        document_id=str(doc["document_id"]),
        owner_id=str(doc["owner_id"]),
        state=str(doc["state"]),  # type: ignore[arg-type]
        source_byte_hash=str(doc["source_byte_hash"]),
        canonical_content_hash=str(doc["canonical_content_hash"]),
        source_format=str(doc["source_format"]),
        title=str(doc["title"]),
        body_text=str(doc.get("body_text") or ""),
        document_loaded_event_id=(
            str(doc["document_loaded_event_id"])
            if doc.get("document_loaded_event_id")
            else None
        ),
        already_hosted=already_hosted,
        non_viewable_reason=(
            str(doc["non_viewable_reason"]) if doc.get("non_viewable_reason") else None
        ),
    )


def ingest_hosted_document(
    *,
    owner_id: str,
    raw: bytes,
    source_format: str,
    store: HostStore,
    authorization: HostAuthorization,
    emit_document_loaded: EmitDocumentLoaded,
    investigation_id: str,
    title: str | None = None,
    source_uri: str | None = None,
) -> HostedDocumentResult:
    """Extract, identify, store, and emit once for one owner/source pair.

    The emitter is injected so this application service stays independent of
    event-log paths in tests. A process lock makes the store lookup, emission,
    and persistence one critical section for the process-local production
    store. Durable stores must provide their own single-writer deployment.
    """
    owner = owner_id.strip()
    if not owner:
        raise ValueError("owner_id is required")
    if not investigation_id.strip():
        raise ValueError("investigation_id is required")
    authorization.validate()
    extracted = extract_document_bytes(raw, source_format=source_format)
    document_id = _document_id(owner, extracted.source_byte_hash)

    with _INGEST_LOCK:
        existing = store.get_document(document_id)
        if existing is not None:
            if str(existing.get("owner_id") or "") != owner:
                raise RuntimeError("hosted document identity owner mismatch")
            store.put_membership(owner, document_id)
            return _result(existing, already_hosted=True)

        resolved_title = (title or extracted.title or "Hosted document").strip()
        state: Literal["ready", "non_viewable"] = (
            "ready" if extracted.viewable else "non_viewable"
        )
        event_id = None
        if extracted.viewable:
            event_id = emit_document_loaded(
                investigation_id,
                document_id,
                extracted,
                len(raw),
                source_uri,
            )
            if not event_id.strip():
                raise RuntimeError("document.loaded emitter returned an empty event_id")

        doc: dict[str, Any] = {
            "document_id": document_id,
            "owner_id": owner,
            "state": state,
            "source_byte_hash": extracted.source_byte_hash,
            "content_hash": extracted.canonical_content_hash,
            "canonical_content_hash": extracted.canonical_content_hash,
            "extracted_content_hash": extracted.extracted_content_hash,
            "extractor_version": extracted.extractor_version,
            "source_format": extracted.source_format,
            "title": resolved_title,
            "author": extracted.author,
            "body_text": extracted.text,
            "page_count": extracted.page_count,
            "page_word_counts": list(extracted.page_word_counts),
            "toc": [entry.__dict__ for entry in extracted.toc],
            "word_count": extracted.word_count,
            "truncated": extracted.truncated,
            "non_viewable_reason": extracted.non_viewable_reason,
            "document_loaded_event_id": event_id,
            "license_class": authorization.license_class,
            "entitlement_id": authorization.entitlement_id,
            "source_uri": source_uri,
            "view_format": "html",
        }
        store.put_document(document_id, doc)
        store.put_membership(owner, document_id)
        return _result(doc, already_hosted=False)
