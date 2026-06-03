"""Twitter / X → Antiek substrate adapter.

Sprint 14: paired with the browser extension at ``apps/x-extension/``.

The extension captures a tweet thread from x.com and POSTs a
``TwitterThread`` payload to the substrate's ``/sources/ingest``
endpoint (kind="twitter"). This adapter writes it into the graph as
a single ``document_type='social_thread'`` row whose chunks are
individual tweets in the thread.

No direct API integration. The browser context is the canonical
authentication path for X (no developer-API tier is sufficient for
this use case at Sprint 14 pricing). The extension passes the page
DOM-extracted thread content.
"""

from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime

_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from processing.chunking.chunker import (  # noqa: E402
    Chunk,
    content_hash,
)
from processing.embedding.embed import (  # noqa: E402
    EmbeddingProvider,
    default_embedding_provider,
)
from substrate.constants import PERSONAL_READING_CONTENT_CLASS  # noqa: E402
from substrate.event_log import emit_typed  # noqa: E402
from substrate.graph import (  # noqa: E402
    default_db_path,
    ensure_initialized,
)
from substrate.graph.ops import (  # noqa: E402
    insert_chunk,
    insert_document,
    insert_node,
)
from substrate.schemas import DocumentLoadedPayload  # noqa: E402

DEFAULT_TWITTER_SOURCE_TIER = 4  # social_media tier in the master spec
_NODE_LABEL_MAX = 160
MIN_INGEST_WORD_COUNT = 5  # threads can be terse; lower threshold


@dataclass(frozen=True)
class Tweet:
    """One post within a thread."""

    tweet_id: str
    text: str
    author_handle: str  # without leading @
    author_verified: bool = False
    posted_at: datetime | None = None
    reply_to: str | None = None  # tweet_id this replies to
    quote_of: str | None = None  # tweet_id quoted-rt'd
    media_urls: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TwitterThread:
    """A captured thread — N tweets, ordered."""

    thread_url: str
    root_tweet_id: str
    author_handle: str  # without leading @
    tweets: list[Tweet]
    captured_at: datetime = field(
        default_factory=lambda: datetime.now(UTC),
    )


@dataclass(frozen=True)
class IngestTwitterResult:
    document_id: str
    chunk_ids: list[str] = field(default_factory=list)
    node_ids: list[str] = field(default_factory=list)
    document_loaded_event_id: str | None = None
    chunks_written: int = 0
    skipped_reason: str | None = None
    title: str | None = None


def twitter_doc_id(root_tweet_id: str) -> str:
    """Stable doc id keyed on the root tweet of the thread. Same root
    → same id, so re-ingesting an extended thread is idempotent at the
    document row (chunks will append new tweets)."""
    if not root_tweet_id:
        raise ValueError("empty root_tweet_id")
    h = hashlib.sha256(root_tweet_id.encode("utf-8")).hexdigest()[:16]
    return f"doc-x-{h}"


def _format_thread_markdown(thread: TwitterThread) -> str:
    """Render a TwitterThread as chunker-friendly markdown."""
    lines = [
        f"# Thread by @{thread.author_handle}",
        "",
        f"**URL:** {thread.thread_url}",
        f"**Captured:** {thread.captured_at.isoformat()}",
        f"**Root tweet:** {thread.root_tweet_id}",
        "",
    ]
    for i, tw in enumerate(thread.tweets):
        verified = " ✓" if tw.author_verified else ""
        when = (
            tw.posted_at.isoformat() if tw.posted_at else "?"
        )
        lines.append(f"## Tweet {i + 1} — @{tw.author_handle}{verified}")
        lines.append(f"_id: {tw.tweet_id} • posted: {when}_")
        if tw.reply_to:
            lines.append(f"_reply to: {tw.reply_to}_")
        if tw.quote_of:
            lines.append(f"_quoting: {tw.quote_of}_")
        lines.append("")
        lines.append(tw.text.strip())
        lines.append("")
    return "\n".join(lines)


def _chunk_per_tweet(
    thread: TwitterThread, full_text: str,
) -> list[Chunk]:
    """Each tweet → one chunk. This preserves tweet boundaries for
    later attribution rather than chunking by paragraph."""
    chunks: list[Chunk] = []
    for i, tw in enumerate(thread.tweets):
        section = f"Tweet {i + 1} (@{tw.author_handle})"
        body = f"@{tw.author_handle}: {tw.text.strip()}"
        chunks.append(Chunk(
            text=body,
            section=section,
            token_count=max(1, len(body.split())),
        ))
    return chunks


def ingest_twitter_thread(
    thread: TwitterThread,
    *,
    investigation_id: str,
    content_class: str = PERSONAL_READING_CONTENT_CLASS,
    source_tier: int = DEFAULT_TWITTER_SOURCE_TIER,
    db_path: str | None = None,
    embedder: EmbeddingProvider | None = None,
    min_word_count: int = MIN_INGEST_WORD_COUNT,
) -> IngestTwitterResult:
    """Ingest a captured Twitter thread. Each tweet becomes its own
    chunk + node so per-tweet attribution survives downstream.

    Personal-Reading Lane (SPR-08): ``content_class`` is threaded through to
    ``insert_document`` and DEFAULTS to the imported
    ``PERSONAL_READING_CONTENT_CLASS`` constant — a third-party X/Twitter thread
    the owner is reading lands ``personal_reading`` (owner-readable, NEVER served
    publicly / ad-attributed / trained on). The default is the IMPORTED CONSTANT,
    never the ``"personal_reading"`` string literal, so ``corpus_audit``'s
    bypass-scanner (which AST-scans ``acquisition/twitter/`` for content_class
    string literals) stays green. Both the browser-extension capture path and the
    BYOK API runner reach this one insert site, so both inherit the lane."""
    document_id = twitter_doc_id(thread.root_tweet_id)
    title = f"Thread by @{thread.author_handle}"

    if not thread.tweets:
        payload = DocumentLoadedPayload(
            media_type="markdown",
            content_hash="sha256:" + content_hash(thread.thread_url),
            size_bytes=0,
            title=title,
            page_count=None,
            source_uri=thread.thread_url,
        )
        event_id = emit_typed(
            investigation_id,
            payload,
            document_id=document_id,
            role="acquisition",
            policy_id="acquisition/twitter",
        )
        return IngestTwitterResult(
            document_id=document_id,
            document_loaded_event_id=event_id,
            skipped_reason="empty_thread",
            title=title,
        )

    full_text = _format_thread_markdown(thread)
    chash = "sha256:" + content_hash(full_text)
    word_count = sum(len(tw.text.split()) for tw in thread.tweets)

    payload = DocumentLoadedPayload(
        media_type="markdown",
        content_hash=chash,
        size_bytes=len(full_text.encode("utf-8")),
        title=title,
        page_count=None,
        source_uri=thread.thread_url,
    )
    event_id = emit_typed(
        investigation_id,
        payload,
        document_id=document_id,
        role="acquisition",
        policy_id="acquisition/twitter",
    )

    if word_count < min_word_count:
        return IngestTwitterResult(
            document_id=document_id,
            document_loaded_event_id=event_id,
            skipped_reason="low_word_count",
            title=title,
        )

    resolved_db_path = db_path or default_db_path()
    ensure_initialized(resolved_db_path)
    chunks: list[Chunk] = _chunk_per_tweet(thread, full_text)
    chunk_ids: list[str] = []
    node_ids: list[str] = []
    chunks_written = 0
    emb = embedder or default_embedding_provider()

    from runtime.db_lock import connect_write

    with connect_write(resolved_db_path, purpose="acquisition/twitter") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=int(source_tier),
            document_type="social_thread",
            # Personal-Reading Lane (SPR-02): a third-party X/Twitter thread
            # the owner captured for their own reading lands personal_reading —
            # full body readable by the owner, NEVER served publicly / ad-
            # attributed / trained on (§9.0). The IMPORTED CONSTANT is passed,
            # never the "personal_reading" literal (corpus_audit's scanner
            # flags content_class string literals to keep classify() the one
            # chokepoint). This is the SOLE insert_document site for the
            # social_thread document_type: ingest_thread_payload routes through
            # ingest_twitter_thread, so both entry points inherit this lane.
            # Belt-and-suspenders with the SPR-01 deny-by-default fallback.
            # SPR-08: the value comes from the ``content_class`` parameter, which
            # DEFAULTS to PERSONAL_READING_CONTENT_CLASS (the imported constant,
            # never a string literal) — the BYOK runner passes it explicitly.
            content_class=content_class,
            source_uri=thread.thread_url,
            title=title,
            author=thread.author_handle,
            published_at=thread.tweets[0].posted_at,
            investigation_id=investigation_id,
            raw_text=full_text,
            metadata={
                "platform": "twitter",
                "author_handle": thread.author_handle,
                "root_tweet_id": thread.root_tweet_id,
                "tweet_count": len(thread.tweets),
                "captured_at": thread.captured_at.isoformat(),
            },
            on_conflict="ignore",
        )
        for i, (chunk, tw) in enumerate(zip(chunks, thread.tweets)):
            chunk_id = insert_chunk(
                con,
                document_id=document_id,
                chunk_index=i,
                text=chunk.text,
                section_path=chunk.section,
                embedding=emb.encode(chunk.text),
                token_count=chunk.token_count,
            )
            chunk_ids.append(chunk_id)
            chunks_written += 1

            label = tw.text.strip().splitlines()[0] if tw.text.strip() else ""
            if len(label) > _NODE_LABEL_MAX:
                label = label[: _NODE_LABEL_MAX - 1] + "…"
            if not label:
                label = f"tweet-{tw.tweet_id}"
            node_id = insert_node(
                con,
                canonical_label=label,
                node_type="entity",
                graph_scope="cross_domain",
                investigation_id=investigation_id,
                embedding=emb.encode(label),
                metadata={
                    "source": "twitter",
                    "tweet_id": tw.tweet_id,
                    "author_handle": tw.author_handle,
                    "verified": tw.author_verified,
                    "chunk_id": chunk_id,
                },
                parent_event_id=event_id,
                on_conflict="ignore",
            )
            node_ids.append(node_id)

    return IngestTwitterResult(
        document_id=document_id,
        chunk_ids=chunk_ids,
        node_ids=node_ids,
        document_loaded_event_id=event_id,
        chunks_written=chunks_written,
        title=title,
    )


def ingest_thread_payload(
    payload: dict,
    *,
    investigation_id: str,
    content_class: str = PERSONAL_READING_CONTENT_CLASS,
    db_path: str | None = None,
    embedder: EmbeddingProvider | None = None,
) -> IngestTwitterResult:
    """Convenience: convert the browser extension's POST payload into
    a ``TwitterThread`` and run ``ingest_twitter_thread``.

    Personal-Reading Lane (SPR-08): ``content_class`` is forwarded to
    ``ingest_twitter_thread`` and defaults to the imported
    ``PERSONAL_READING_CONTENT_CLASS`` constant, so the browser-extension handler
    lands ``personal_reading`` (not the servable ``user_owned`` default).

    Expected payload shape (matches what the extension posts):

    ```json
    {
      "thread_url": "https://x.com/<handle>/status/<id>",
      "root_tweet_id": "<id>",
      "author_handle": "<handle>",
      "tweets": [
        {
          "tweet_id": "...",
          "text": "...",
          "author_handle": "...",
          "author_verified": false,
          "posted_at": "2026-05-18T14:30:00Z",
          "reply_to": null,
          "quote_of": null,
          "media_urls": []
        },
        ...
      ]
    }
    ```
    """
    tweets: list[Tweet] = []
    for raw in payload.get("tweets", []):
        posted_at = None
        if raw.get("posted_at"):
            try:
                posted_at = datetime.fromisoformat(
                    raw["posted_at"].replace("Z", "+00:00")
                )
            except (TypeError, ValueError):
                posted_at = None
        tweets.append(Tweet(
            tweet_id=str(raw.get("tweet_id", "")),
            text=str(raw.get("text", "")),
            author_handle=str(
                raw.get("author_handle", payload.get("author_handle", ""))
            ).lstrip("@"),
            author_verified=bool(raw.get("author_verified", False)),
            posted_at=posted_at,
            reply_to=raw.get("reply_to"),
            quote_of=raw.get("quote_of"),
            media_urls=list(raw.get("media_urls", [])),
        ))
    thread = TwitterThread(
        thread_url=str(payload.get("thread_url", "")),
        root_tweet_id=str(payload.get("root_tweet_id", "")),
        author_handle=str(payload.get("author_handle", "")).lstrip("@"),
        tweets=tweets,
    )
    return ingest_twitter_thread(
        thread,
        investigation_id=investigation_id,
        content_class=content_class,
        db_path=db_path,
        embedder=embedder,
    )
