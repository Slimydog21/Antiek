"""Substack RSS acquisition connector.

A thin connector that fetches a subscribed Substack publication's RSS feed
(``<publication>/feed``), parses posts, and ingests them into the substrate
as ``documents`` + ``chunks`` + graph ``nodes``. Modeled byte-for-byte on
``acquisition/podcasts``.

Lane: ``newsletter_post`` is a third-party ``document_type``; every post
lands ``content_class=personal_reading`` via the deny-by-default guard at
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

from .adapter import (
    IngestResult,
    PublicationIngestSummary,
    ingest_post,
    ingest_publication_feed,
)
from .client import (
    MIN_FULL_BODY_CHARS,
    TRUNCATION_MARKERS,
    Post,
    Publication,
    detect_truncation,
    fetch_feed,
    substack_doc_id,
)
from .subscriptions import (
    Subscription,
    SubscriptionManifestError,
    ingest_subscriptions,
    load_subscriptions,
    resolve_feed_url,
)

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
    "ingest_post",
    "ingest_publication_feed",
    "ingest_subscriptions",
    "load_subscriptions",
    "resolve_feed_url",
    "IngestResult",
    "PublicationIngestSummary",
]
