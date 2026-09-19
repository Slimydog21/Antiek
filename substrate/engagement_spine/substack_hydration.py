"""Policy-injected Substack acquisition into owner-bound canonical HTML.

This module contains no network client.  The operator-owned factory is the
only I/O authority; its typed response is independently validated before any
asset or hosted-document write occurs.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from acquisition.snapshot.reader_html import sanitize_html_fragment
from services.hosted_documents.service import (
    EmitDocumentLoaded,
    HostAuthorization,
    HostedDocumentResult,
    ingest_hosted_document,
)
from substrate.marketplace_host.library import HostStore

MAX_SUBSTACK_BODY_BYTES = 2 * 1024 * 1024
MAX_SUBSTACK_BODY_CHARS = 500_000
SubstackHydrationStatus = Literal["body_complete", "body_unavailable"]


@dataclass(frozen=True)
class FetchedSubstackPost:
    requested_url: str
    final_url: str
    redirect_chain: tuple[str, ...]
    title: str
    author: str
    published_at: datetime | None
    body_html: str
    body_sha256: str
    body_size_bytes: int
    content_type: str
    truncated: bool
    paywalled: bool
    auth_challenge: bool
    factory_id: str
    policy_id: str
    policy_approved_by: str
    rollback_switch: str


FetchSubstackPost = Callable[[str], FetchedSubstackPost]


@dataclass(frozen=True)
class SubstackHydrationOutcome:
    status: SubstackHydrationStatus
    requested_url: str
    canonical_url: str
    document: HostedDocumentResult | None
    receipt: dict[str, Any]

    @property
    def hydrated(self) -> bool:
        return self.status == "body_complete" and self.document is not None


def _post_origin(url: str) -> tuple[str, str]:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host.endswith(".substack.com"):
        raise ValueError("Substack acquisition requires an https *.substack.com URL")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2 or parts[0] != "p" or not parts[1]:
        raise ValueError("Substack acquisition requires an explicit /p/<slug> post URL")
    return host, f"https://{host}/p/{parts[1]}"


def _unavailable(
    *,
    requested_url: str,
    canonical_url: str,
    reason: str,
    attempted: bool,
    evidence: dict[str, Any] | None = None,
) -> SubstackHydrationOutcome:
    return SubstackHydrationOutcome(
        status="body_unavailable",
        requested_url=requested_url,
        canonical_url=canonical_url,
        document=None,
        receipt={
            "kind": "substack_body_unavailable",
            "reason": reason,
            "requested_url": requested_url,
            "canonical_url": canonical_url,
            "request_attempted": attempted,
            **(evidence or {}),
        },
    )


def hydrate_substack_body(
    *,
    requested_url: str,
    owner_id: str,
    investigation_id: str,
    store: HostStore,
    fetch_post: FetchSubstackPost | None,
    emit_document_loaded: EmitDocumentLoaded,
    minimum_viewable_words: int = 50,
) -> SubstackHydrationOutcome:
    """Acquire one explicit post and host its sanitized canonical HTML body."""
    requested_host, canonical_requested = _post_origin(requested_url)
    if fetch_post is None:
        return _unavailable(
            requested_url=requested_url,
            canonical_url=canonical_requested,
            reason="operator_factory_not_installed",
            attempted=False,
        )
    try:
        fetched = fetch_post(canonical_requested)
    except Exception as exc:
        return _unavailable(
            requested_url=requested_url,
            canonical_url=canonical_requested,
            reason=type(exc).__name__,
            attempted=True,
        )
    if not isinstance(fetched, FetchedSubstackPost):
        raise TypeError("Substack factory must return FetchedSubstackPost")
    _, normalized_response_request = _post_origin(fetched.requested_url)
    final_host, canonical_final = _post_origin(fetched.final_url)
    if normalized_response_request != canonical_requested:
        raise ValueError("Substack factory response does not match the requested post")
    if final_host != requested_host:
        raise ValueError("Substack redirect escaped the approved publication host")
    if not fetched.redirect_chain or len(fetched.redirect_chain) > 6:
        raise ValueError("Substack redirect chain receipt is missing or oversized")
    normalized_hops: list[str] = []
    for hop in fetched.redirect_chain:
        try:
            hop_host, normalized_hop = _post_origin(hop)
        except ValueError as exc:
            raise ValueError(
                "Substack redirect chain escaped the approved publication host"
            ) from exc
        if hop_host != requested_host:
            raise ValueError("Substack redirect chain escaped the approved publication host")
        normalized_hops.append(normalized_hop)
    if normalized_hops[0] != canonical_requested or normalized_hops[-1] != canonical_final:
        raise ValueError("Substack redirect chain does not bind request to final URL")
    policy_values = (
        fetched.factory_id.strip(),
        fetched.policy_id.strip(),
        fetched.policy_approved_by.strip(),
        fetched.rollback_switch.strip(),
    )
    if not all(policy_values):
        raise ValueError("Substack factory response lacks operator policy authority")
    if fetched.paywalled or fetched.auth_challenge or fetched.truncated:
        reason = (
            "paywall_detected"
            if fetched.paywalled
            else "auth_challenge_detected"
            if fetched.auth_challenge
            else "truncated_teaser"
        )
        return _unavailable(
            requested_url=requested_url,
            canonical_url=canonical_final,
            reason=reason,
            attempted=True,
            evidence={
                "redirect_chain": list(fetched.redirect_chain),
                "factory": {
                    "factory_id": fetched.factory_id,
                    "policy_id": fetched.policy_id,
                    "policy_approved_by": fetched.policy_approved_by,
                    "rollback_switch": fetched.rollback_switch,
                },
            },
        )
    raw = fetched.body_html.encode("utf-8")
    if not raw or not fetched.body_html.strip():
        raise ValueError("Substack factory returned an empty body")
    if len(raw) > MAX_SUBSTACK_BODY_BYTES or len(fetched.body_html) > MAX_SUBSTACK_BODY_CHARS:
        raise ValueError("Substack body exceeds the acquisition limit")
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if fetched.body_sha256 != actual_sha256 or fetched.body_size_bytes != len(raw):
        raise ValueError("Substack body receipt does not match the acquired bytes")
    if fetched.content_type.split(";", 1)[0].strip().lower() not in {
        "text/html",
        "application/xhtml+xml",
    }:
        raise ValueError("Substack factory returned a non-HTML content type")
    sanitized = sanitize_html_fragment(fetched.body_html, max_chars=MAX_SUBSTACK_BODY_CHARS)
    if not sanitized.strip():
        raise ValueError("Substack body is empty after sanitization")
    sanitized_raw = sanitized.encode("utf-8")
    provenance = {
        "kind": "substack_post_acquisition",
        "requested_url": canonical_requested,
        "canonical_url": canonical_final,
        "redirect_chain": list(fetched.redirect_chain),
        "source_sha256": actual_sha256,
        "source_byte_size": len(raw),
        "sanitized_sha256": hashlib.sha256(sanitized_raw).hexdigest(),
        "publication": {
            "title": fetched.title,
            "author": fetched.author,
            "published_at": fetched.published_at.isoformat() if fetched.published_at else None,
        },
        "factory": {
            "factory_id": fetched.factory_id,
            "policy_id": fetched.policy_id,
            "policy_approved_by": fetched.policy_approved_by,
            "rollback_switch": fetched.rollback_switch,
        },
        "rights": {
            "content_class": "personal_reading",
            "basis": "operator_approved_private_subscriber_copy_not_redistributable",
            "redistributable": False,
        },
    }
    document = ingest_hosted_document(
        owner_id=owner_id,
        raw=sanitized_raw,
        source_format="html",
        store=store,
        authorization=HostAuthorization("personal_reading"),
        emit_document_loaded=emit_document_loaded,
        investigation_id=investigation_id,
        title=fetched.title,
        source_uri=canonical_final,
        minimum_viewable_words=minimum_viewable_words,
        provenance=provenance,
    )
    if document.state != "ready" or not document.body_text.strip():
        return SubstackHydrationOutcome(
            status="body_unavailable",
            requested_url=requested_url,
            canonical_url=canonical_final,
            document=document,
            receipt={
                **provenance,
                "kind": "substack_body_unavailable",
                "reason": document.non_viewable_reason or "extracted_body_empty",
                "request_attempted": True,
                "document_id": document.document_id,
            },
        )
    stored = store.get_document(document.document_id)
    if stored is None:
        raise RuntimeError("canonical Substack document disappeared after ingest")
    return SubstackHydrationOutcome(
        status="body_complete",
        requested_url=requested_url,
        canonical_url=canonical_final,
        document=document,
        receipt={
            **provenance,
            "kind": "substack_body_complete",
            "verified_body": True,
            "request_attempted": True,
            "canonical_hosted_document_id": document.document_id,
            "canonical_content_hash": document.canonical_content_hash,
            "source_byte_hash": document.source_byte_hash,
            "source_format": document.source_format,
            "document_loaded_event_id": document.document_loaded_event_id,
            "extractor_version": stored.get("extractor_version"),
            "extracted_content_hash": stored.get("extracted_content_hash"),
            "word_count": stored.get("word_count"),
            "author": fetched.author,
            "title": fetched.title,
            "published_at": fetched.published_at.isoformat() if fetched.published_at else None,
            "owner_bound": True,
            "view_format": "html",
        },
    )


__all__ = [
    "FetchedSubstackPost",
    "FetchSubstackPost",
    "MAX_SUBSTACK_BODY_BYTES",
    "SubstackHydrationOutcome",
    "hydrate_substack_body",
]
