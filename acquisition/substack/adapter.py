"""Substack ingestion adapter — feed posts to documents + chunks + nodes.

Writes funnel through ``runtime.db_lock.connect_write`` (single-writer §16).
Each post becomes a ``documents`` row (``document_type="newsletter_post"``)
plus ``chunks`` and a graph ``node``. Idempotent: re-ingesting the same feed
is a no-op via ``on_conflict="ignore"`` keyed on the deterministic doc id.

This module mirrors ``acquisition/podcasts/adapter.py`` line-for-line in the
write sequence (the ``with connect_write(...) as conn`` block at
podcasts/adapter.py:79-117: document_exists short-circuit → insert_document
with on_conflict="ignore" → insert_chunk loop → insert_node).

LANE NOTE (M2 decision — see README "Why personal_reading"):
``newsletter_post`` is a THIRD-PARTY document_type (it is a member of
``constants.THIRD_PARTY_DOCUMENT_TYPES``). We use OPTION A — GUARD-RELIANT:
we do NOT pass ``content_class``; the deny-by-default guard at
``insert_document`` (``_resolve_content_class``) re-maps third-party types to
``personal_reading``. This matches the actual shipped SPR-02 sibling
convention in ``acquisition/urls/adapter.py`` and ``acquisition/podcasts`` —
the policy lives in ONE place (the guard), so a future maintainer cannot pass
the wrong class here. A leaked-servable post is the §9.0 catastrophe; keeping
a single policy location is the most defensible guard against it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from runtime import db_lock
from substrate import constants
from substrate.event_log import emit_typed
from substrate.events_typed import DocumentLoadedPayload
from substrate.graph import ops as graph_ops
from substrate.text import chunk_markdown

from .client import Post, Publication, fetch_feed, substack_doc_id


@dataclass
class IngestResult:
    """Outcome of ingesting a single post."""

    doc_id: str
    status: str  # "ingested" | "skipped"
    chunk_count: int = 0
    truncated: bool = False


def _resolve_db_path(db_path: Optional[str]) -> str:
    if db_path is not None:
        return db_path
    return constants.resolve_db_path()


def ingest_post(
    post: Post,
    *,
    publication: Publication,
    investigation_id: str,
    db_path: Optional[str] = None,
    source_tier: int = constants.DEFAULT_SUBSTACK_SOURCE_TIER,
) -> IngestResult:
    """Ingest a single Substack post into documents + chunks + node.

    Lands ``content_class=personal_reading`` via the deny-by-default guard
    (newsletter_post is a third-party type) — see module docstring (option A).
    The stored ``raw_text`` is EXACTLY the markdown rendered from the feed
    body; truncated posts are stored as-is and flagged, never fabricated.
    """
    doc_id = substack_doc_id(post.guid)
    resolved_db_path = _resolve_db_path(db_path)
    # raw_text == exactly the feed body rendered to markdown. No padding, no
    # synthesized remainder for truncated posts (rigor #1).
    markdown = post.body_markdown
    chunks = chunk_markdown(markdown)

    payload = DocumentLoadedPayload(
        document_id=doc_id,
        document_type="newsletter_post",
        source_url=post.post_url or publication.feed_url,
        title=post.title,
        byte_count=len(markdown.encode("utf-8")),
    )
    emit_typed(
        payload,
        role="acquisition",
        policy_id="acquisition/substack",
        investigation_id=investigation_id,
    )

    with db_lock.connect_write(
        resolved_db_path, purpose="acquisition/substack"
    ) as conn:
        if graph_ops.document_exists(conn, doc_id):
            return IngestResult(
                doc_id=doc_id, status="skipped", truncated=post.truncated
            )
        graph_ops.insert_document(
            conn,
            document_id=doc_id,
            document_type="newsletter_post",
            title=post.title,
            raw_text=markdown,
            source_url=post.post_url or publication.feed_url,
            metadata={
                "feed_url": publication.feed_url,
                "publication_title": publication.title,
                "guid": post.guid,
                "author": post.author,
                "post_url": post.post_url,
                "published_at": post.published_at.isoformat()
                if post.published_at
                else None,
                "truncated": post.truncated,
                "truncation_reason": post.truncation_reason,
            },
            source_tier=source_tier,
            on_conflict="ignore",
            # content_class OMITTED on purpose (option A, guard-reliant):
            # newsletter_post ∈ THIRD_PARTY_DOCUMENT_TYPES → the guard at
            # insert_document maps it to personal_reading. ip_holder_id left
            # None (personal_reading accrues zero attribution; author→holder
            # resolution is an explicit open question — see README/handoff).
        )
        for idx, chunk_text in enumerate(chunks):
            graph_ops.insert_chunk(
                conn,
                document_id=doc_id,
                chunk_index=idx,
                text=chunk_text,
            )
        graph_ops.insert_node(
            conn,
            node_id=doc_id,
            node_type="document",
            label=post.title,
            metadata={"document_type": "newsletter_post"},
        )
    return IngestResult(
        doc_id=doc_id,
        status="ingested",
        chunk_count=len(chunks),
        truncated=post.truncated,
    )


@dataclass
class PublicationIngestSummary:
    """Aggregated outcome of ingesting one publication's feed.

    Mirrors the per-feed aggregation in ``podcasts.ingest_feed`` (which returns
    per-episode results); here we additionally roll up counts so a
    multi-publication ``ingest_subscriptions`` run can report per-publication
    totals.
    """

    feed_url: str
    publication_title: str
    results: list[IngestResult]

    @property
    def ingested(self) -> int:
        return sum(1 for r in self.results if r.status == "ingested")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == "skipped")

    @property
    def truncated(self) -> int:
        return sum(1 for r in self.results if r.truncated)


def ingest_publication_feed(
    feed_url: str,
    *,
    investigation_id: str,
    db_path: Optional[str] = None,
    max_posts: Optional[int] = None,
    source_tier: int = constants.DEFAULT_SUBSTACK_SOURCE_TIER,
    client=None,
) -> PublicationIngestSummary:
    """Fetch one publication feed and ingest every post.

    Returns a ``PublicationIngestSummary`` with per-post results + roll-ups.
    """
    publication = fetch_feed(feed_url, max_posts=max_posts, client=client)
    results: list[IngestResult] = []
    for post in publication.posts:
        results.append(
            ingest_post(
                post,
                publication=publication,
                investigation_id=investigation_id,
                db_path=db_path,
                source_tier=source_tier,
            )
        )
    return PublicationIngestSummary(
        feed_url=feed_url,
        publication_title=publication.title,
        results=results,
    )
