"""Governed arXiv body hydration into the owner-bound canonical HTML store.

Network authority is deliberately outside this module: callers must install a
body fetcher, and boot wiring installs it only when the live env gate is also
enabled.  The fetcher is expected to be the existing ``fetch_pdf`` path, which
requires an ``ArxivThrottle`` and uses the host-global governor.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

from acquisition.arxiv.pdf_fetch import FetchedPdf
from services.hosted_documents.service import (
    EmitDocumentLoaded,
    HostAuthorization,
    HostedDocumentResult,
    ingest_hosted_document,
)
from substrate.marketplace_host.library import HostStore

ArxivBodyStatus = Literal["body_complete", "body_unavailable"]
FetchArxivBody = Callable[[str], FetchedPdf]


@dataclass(frozen=True)
class ArxivHydrationOutcome:
    status: ArxivBodyStatus
    arxiv_id: str
    canonical_url: str
    document: HostedDocumentResult | None
    receipt: dict[str, Any]

    @property
    def hydrated(self) -> bool:
        return self.status == "body_complete" and self.document is not None


def hydrate_arxiv_body(
    *,
    arxiv_id: str,
    owner_id: str,
    investigation_id: str,
    title: str | None,
    store: HostStore,
    fetch_body: FetchArxivBody | None,
    emit_document_loaded: EmitDocumentLoaded,
    minimum_viewable_words: int = 50,
) -> ArxivHydrationOutcome:
    """Fetch one governed PDF, extract it, and host its canonical HTML view.

    ``None`` is a typed unavailable result and performs zero requests.  Fetch
    failures are recorded without retrying, so 429/ban and malformed/oversized
    bodies retain the canonical fetcher's fail-closed policy.
    """
    clean_id = arxiv_id.strip()
    if not clean_id:
        raise ValueError("arxiv_id is required")
    canonical_url = f"https://arxiv.org/abs/{clean_id}"
    if fetch_body is None:
        return ArxivHydrationOutcome(
            status="body_unavailable",
            arxiv_id=clean_id,
            canonical_url=canonical_url,
            document=None,
            receipt={
                "kind": "arxiv_body_unavailable",
                "reason": "body_fetcher_not_installed",
                "arxiv_id": clean_id,
                "canonical_url": canonical_url,
                "request_attempted": False,
            },
        )
    try:
        fetched = fetch_body(clean_id)
    except Exception as exc:
        return ArxivHydrationOutcome(
            status="body_unavailable",
            arxiv_id=clean_id,
            canonical_url=canonical_url,
            document=None,
            receipt={
                "kind": "arxiv_body_unavailable",
                "reason": type(exc).__name__,
                "arxiv_id": clean_id,
                "canonical_url": canonical_url,
                "request_attempted": True,
            },
        )
    if not isinstance(fetched, FetchedPdf):
        raise TypeError("arXiv body fetcher must return FetchedPdf")
    if fetched.arxiv_id != clean_id:
        raise ValueError("arXiv body fetch returned a different arxiv_id")
    actual_sha256 = hashlib.sha256(fetched.content).hexdigest()
    if fetched.sha256 != actual_sha256 or fetched.byte_size != len(fetched.content):
        raise ValueError("arXiv body fetch returned inconsistent digest or byte size")
    source = urlsplit(fetched.source_url)
    expected_path = f"/pdf/{clean_id}"
    if source.scheme != "https" or source.hostname != "arxiv.org" or source.path != expected_path:
        raise ValueError("arXiv body fetch returned invalid source provenance")
    network_policy = dict(fetched.policy_receipt or {})
    if (
        network_policy.get("governor") != "host_global_arxiv_rate_governor"
        or network_policy.get("redirect_policy") != "every_arxiv_hop_governed"
        or network_policy.get("rate_limit_policy") != "persist_429_ban_and_do_not_retry"
        or not isinstance(network_policy.get("min_spacing_s"), (int, float))
        or float(network_policy["min_spacing_s"]) < 0
        or not isinstance(network_policy.get("default_ban_backoff_s"), (int, float))
        or float(network_policy["default_ban_backoff_s"]) <= 0
    ):
        raise ValueError("arXiv body fetch lacks host-global governor receipt")
    provenance = {
        "kind": "arxiv_pdf_acquisition",
        "arxiv_id": clean_id,
        "canonical_url": canonical_url,
        "source_url": fetched.source_url,
        "source_sha256": fetched.sha256,
        "source_byte_size": fetched.byte_size,
        "network_policy": network_policy,
        "rights": {
            "content_class": "personal_reading",
            "basis": "private_owner_research_copy_not_redistributable",
            "redistributable": False,
        },
    }
    document = ingest_hosted_document(
        owner_id=owner_id,
        raw=fetched.content,
        source_format="pdf",
        store=store,
        authorization=HostAuthorization("personal_reading"),
        emit_document_loaded=emit_document_loaded,
        investigation_id=investigation_id,
        title=title,
        source_uri=fetched.source_url,
        minimum_viewable_words=minimum_viewable_words,
        provenance=provenance,
    )
    if document.state != "ready" or not document.body_text.strip():
        return ArxivHydrationOutcome(
            status="body_unavailable",
            arxiv_id=clean_id,
            canonical_url=canonical_url,
            document=document,
            receipt={
                **provenance,
                "kind": "arxiv_body_unavailable",
                "reason": document.non_viewable_reason or "extracted_body_empty",
                "request_attempted": True,
                "document_id": document.document_id,
            },
        )
    stored = store.get_document(document.document_id)
    if stored is None:
        raise RuntimeError("canonical hosted document disappeared after ingest")
    return ArxivHydrationOutcome(
        status="body_complete",
        arxiv_id=clean_id,
        canonical_url=canonical_url,
        document=document,
        receipt={
            **provenance,
            "kind": "arxiv_body_complete",
            "verified_body": True,
            "request_attempted": True,
            "document_id": document.document_id,
            "canonical_hosted_document_id": document.document_id,
            "canonical_content_hash": document.canonical_content_hash,
            "source_byte_hash": document.source_byte_hash,
            "source_format": document.source_format,
            "document_loaded_event_id": document.document_loaded_event_id,
            "extractor_version": stored.get("extractor_version"),
            "extracted_content_hash": stored.get("extracted_content_hash"),
            "word_count": stored.get("word_count"),
            "network_policy": network_policy,
            "rights": provenance["rights"],
            "owner_bound": True,
            "view_format": "html",
        },
    )


__all__ = ["ArxivHydrationOutcome", "FetchArxivBody", "hydrate_arxiv_body"]
