"""Substack ingestion adapter — feed posts to documents + chunks + nodes.

Writes funnel through ``runtime.db_lock.connect_write`` (single-writer §16).
Each post becomes a ``documents`` row (``document_type="newsletter_post"``)
plus ``chunks`` and per-chunk graph ``nodes``. Idempotent: re-ingesting the
same feed is a graph no-op via ``on_conflict="ignore"`` keyed on the
deterministic doc id (the same ``_exists`` early-return ``acquisition/podcasts``
and ``acquisition/urls`` rely on at ``insert_document``). The IngestResult
"skipped" label is derived from a DOCUMENT-presence probe (the same
``documents.document_id`` predicate ``insert_document`` dedups on), not from a
downstream chunks probe — so an empty-bodied post (zero chunks) still dedups
correctly on re-ingest.

The write block mirrors ``acquisition/podcasts/adapter.py:185-245`` and
``acquisition/urls/adapter.py:445-570`` line-for-line: emit ``document.loaded``
→ ``connect_write`` → ``insert_document(on_conflict="ignore")`` →
``insert_chunk`` loop with embeddings → per-chunk ``insert_node``.

LANE NOTE (M2 decision — see README "Why personal_reading"):
``newsletter_post`` is a THIRD-PARTY document_type (it is a member of
``constants.THIRD_PARTY_DOCUMENT_TYPES``). We use OPTION A — GUARD-RELIANT:
we do NOT pass ``content_class``; the deny-by-default guard at
``insert_document`` (``substrate/graph/ops.py:200-207``) re-maps third-party
types to ``personal_reading``. This keeps the rights policy in ONE place — a
future maintainer of this connector cannot pass the wrong class because this
connector passes none. A leaked-servable post is the §9.0 catastrophe; a single
policy location is the most defensible guard against it.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

# Repo root on path for direct invocation (mirrors podcasts/urls adapters).
_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from processing.chunking.chunker import (  # noqa: E402
    Chunk,
    chunk_markdown,
    content_hash,
)
from processing.embedding.embed import (  # noqa: E402
    EmbeddingProvider,
    default_embedding_provider,
)
from runtime.db_lock import connect_write  # noqa: E402
from substrate.event_log import emit_typed  # noqa: E402
from substrate.graph import (  # noqa: E402
    default_db_path,
    ensure_initialized,
)
from substrate.graph.ops import (  # noqa: E402
    _exists,
    insert_chunk,
    insert_document,
    insert_node,
)
from substrate.schemas import DocumentLoadedPayload  # noqa: E402

from .client import Post, Publication, fetch_feed, substack_doc_id

# General-web tier (4), consistent with acquisition/urls' DEFAULT_URL_SOURCE_TIER
# for unranked web — a subscribed newsletter is general-web trust, not a curated
# corpus source. Overridable per ``ingest_publication_feed(..., source_tier=...)``
# like the podcast/url adapters. Defined as a MODULE constant (the sibling
# convention — acquisition/urls and acquisition/podcasts each define their own
# DEFAULT_*_SOURCE_TIER in their adapter, NOT in constants.py), and it is NOT a
# content_class, so the corpus_audit literal-bypass scan is unaffected.
DEFAULT_SUBSTACK_SOURCE_TIER = 4
_NODE_LABEL_MAX = 160


@dataclass(frozen=True)
class IngestResult:
    """Outcome of ingesting a single post."""

    document_id: str
    guid: str
    status: str  # "ingested" | "skipped"
    chunk_ids: list[str] = field(default_factory=list)
    document_loaded_event_id: str | None = None
    chunks_written: int = 0
    truncated: bool = False
    truncation_reason: str = "none"
    title: str | None = None


def ingest_post(
    post: Post,
    *,
    publication: Publication,
    investigation_id: str,
    db_path: str | None = None,
    source_tier: int = DEFAULT_SUBSTACK_SOURCE_TIER,
    embedder: EmbeddingProvider | None = None,
) -> IngestResult:
    """Ingest a single Substack post into documents + chunks + nodes.

    Lands ``content_class=personal_reading`` via the deny-by-default guard
    (newsletter_post is a third-party type) — see module docstring (option A).
    The stored ``raw_text`` is EXACTLY the markdown rendered from the feed body;
    truncated posts are stored as-is and flagged, never fabricated (rigor #1).
    """
    document_id = substack_doc_id(post.guid)
    resolved_db_path = db_path or default_db_path()
    # raw_text == exactly the feed body rendered to markdown. No padding, no
    # synthesized remainder for truncated posts (rigor #1).
    full_text = post.body_markdown
    chash = "sha256:" + content_hash(full_text)

    payload = DocumentLoadedPayload(
        media_type="markdown",
        content_hash=chash,
        size_bytes=len(full_text.encode("utf-8")),
        title=post.title,
        page_count=None,
        source_uri=post.post_url or publication.feed_url,
    )
    event_id = emit_typed(
        investigation_id,
        payload,
        document_id=document_id,
        role="acquisition",
        policy_id="acquisition/substack",
    )

    ensure_initialized(resolved_db_path)
    chunks: list[Chunk] = chunk_markdown(full_text)
    chunk_ids: list[str] = []
    chunks_written = 0
    emb = embedder or default_embedding_provider()

    with connect_write(resolved_db_path, purpose="acquisition/substack") as con:
        # Dedup probe — keyed on the DOCUMENT, the same authority
        # insert_document(on_conflict="ignore") keys on (its `_exists` check on
        # documents.document_id at substrate/graph/ops.py). insert_document
        # returns the document_id whether it inserted or short-circuited, so it
        # gives us no inserted-vs-skipped signal to read; we therefore probe the
        # documents table ourselves, BEFORE the insert, to decide the
        # IngestResult status. Probing `documents` (not `chunks`) is the correct
        # authority: a prior post with an empty/whitespace body produced a
        # document row but ZERO chunks (chunk_markdown("") -> []), so a
        # chunk-presence probe would wrongly re-process that row on every run.
        # Document presence is exactly the predicate insert_document dedups on,
        # so "only a fresh document reaches the chunk loop" holds for all bodies.
        already_present = _exists(con, "documents", "document_id", document_id)
        insert_document(
            con,
            document_id=document_id,
            source_tier=int(source_tier),
            document_type="newsletter_post",
            source_uri=post.post_url or publication.feed_url,
            title=post.title,
            author=post.author or None,
            published_at=post.published_at,
            investigation_id=investigation_id,
            raw_text=full_text,
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
            on_conflict="ignore",
            # content_class OMITTED on purpose (option A, guard-reliant):
            # newsletter_post ∈ THIRD_PARTY_DOCUMENT_TYPES → the insert_document
            # guard maps it to personal_reading. ip_holder_id left None
            # (personal_reading accrues zero attribution; author→holder
            # resolution is an explicit open question — see README/handoff).
        )
        if already_present:
            return IngestResult(
                document_id=document_id,
                guid=post.guid,
                status="skipped",
                document_loaded_event_id=event_id,
                truncated=post.truncated,
                truncation_reason=post.truncation_reason,
                title=post.title,
            )

        for i, chunk in enumerate(chunks):
            chunk_id = insert_chunk(
                con,
                document_id=document_id,
                chunk_index=i,
                text=chunk.text,
                section_path=chunk.section or None,
                embedding=emb.encode(chunk.text),
                token_count=chunk.token_count,
            )
            chunk_ids.append(chunk_id)
            chunks_written += 1

            label = chunk.text.strip().splitlines()[0] if chunk.text.strip() else ""
            if len(label) > _NODE_LABEL_MAX:
                label = label[: _NODE_LABEL_MAX - 1] + "…"
            if not label:
                label = f"{post.guid}#{i}"
            insert_node(
                con,
                canonical_label=label,
                node_type="entity",
                graph_scope="cross_domain",
                investigation_id=investigation_id,
                embedding=emb.encode(label),
                metadata={
                    "source": "substack",
                    "publication_title": publication.title,
                    "guid": post.guid,
                    "chunk_id": chunk_id,
                    "section": chunk.section,
                },
                parent_event_id=event_id,
                on_conflict="ignore",
            )

    return IngestResult(
        document_id=document_id,
        guid=post.guid,
        status="ingested",
        chunk_ids=chunk_ids,
        document_loaded_event_id=event_id,
        chunks_written=chunks_written,
        truncated=post.truncated,
        truncation_reason=post.truncation_reason,
        title=post.title,
    )


@dataclass
class PublicationIngestSummary:
    """Aggregated outcome of ingesting one publication's feed.

    Mirrors the per-feed aggregation in ``podcasts.ingest_feed`` (per-episode
    results) and additionally rolls up counts so a multi-publication
    ``ingest_subscriptions`` run can report per-publication totals.
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
    db_path: str | None = None,
    max_posts: int | None = None,
    source_tier: int = DEFAULT_SUBSTACK_SOURCE_TIER,
    embedder: EmbeddingProvider | None = None,
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
                embedder=embedder,
            )
        )
    return PublicationIngestSummary(
        feed_url=feed_url,
        publication_title=publication.title,
        results=results,
    )
