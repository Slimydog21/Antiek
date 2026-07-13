"""Substack RSS acquisition connector.

A thin connector that fetches a subscribed Substack publication's RSS feed
(``<publication>/feed``), parses posts, and ingests them into the substrate as
``documents`` + ``chunks`` + graph ``nodes``. Modeled on ``acquisition/podcasts``
(and reusing ``acquisition/urls``' HTML→markdown extractor).

Lane: ``newsletter_post`` is a third-party ``document_type``; every post lands
``content_class=personal_reading`` via the deny-by-default guard at
``insert_document`` (option A — guard-reliant). It is NEVER servable,
attributed, or trained. See README for the full lane rationale.

Public surface (mirrors ``acquisition/podcasts/__init__.py``):

- ``fetch_feed(feed_url, *, max_posts=None, client=None) -> Publication``
- ``ingest_post(post, *, publication, investigation_id, ...) -> IngestResult``
- ``ingest_publication_feed(feed_url, *, investigation_id, ...) -> PublicationIngestSummary``
- ``ingest_subscriptions(path, *, investigation_id, ...) -> list[PublicationIngestSummary]``
- ``substack_doc_id(guid) -> str``
- ``resolve_feed_url(entry) -> str`` / ``load_subscriptions(path) -> list[Subscription]``
- ``detect_truncation(*, body_markdown, summary_html="") -> (bool, str)``
- dataclasses ``Publication``, ``Post``, ``Subscription``
"""
from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORT_MODULE = {
    "DEFAULT_SUBSTACK_SOURCE_TIER": "adapter",
    "IngestResult": "adapter",
    "PublicationIngestSummary": "adapter",
    "ingest_post": "adapter",
    "ingest_publication_feed": "adapter",
    "MIN_FULL_BODY_CHARS": "client",
    "TRUNCATION_MARKERS": "client",
    "Post": "client",
    "Publication": "client",
    "detect_truncation": "client",
    "fetch_feed": "client",
    "substack_doc_id": "client",
    "Subscription": "subscriptions",
    "SubscriptionManifestError": "subscriptions",
    "ingest_subscriptions": "subscriptions",
    "load_subscriptions": "subscriptions",
    "resolve_feed_url": "subscriptions",
}


def __getattr__(name: str) -> Any:
    """Load the legacy network connector only when its public symbol is requested."""
    module_name = _EXPORT_MODULE.get(name)
    if module_name is None:
        raise AttributeError(name)
    value = getattr(import_module(f"{__name__}.{module_name}"), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))

__all__ = [
    "Publication",
    "Post",
    "Subscription",
    "SubscriptionManifestError",
    "fetch_feed",
    "substack_doc_id",
    "detect_truncation",
    "TRUNCATION_MARKERS",
    "MIN_FULL_BODY_CHARS",
    "DEFAULT_SUBSTACK_SOURCE_TIER",
    "ingest_post",
    "ingest_publication_feed",
    "ingest_subscriptions",
    "load_subscriptions",
    "resolve_feed_url",
    "IngestResult",
    "PublicationIngestSummary",
]
