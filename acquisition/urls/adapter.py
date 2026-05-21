"""URL → Antiek substrate adapter.

Fetch HTML, extract main content as markdown, emit ``document.loaded``,
write to ``substrate.graph``. Mirrors the ``acquisition.arxiv.adapter``
contract — same return shape, same idempotency guarantees.

Stable doc id: ``doc-url-<sha256-of-final-url[:16]>`` so the same URL
resurfacing in a new session dedups against prior ingestion. Using a
hash (not the URL itself) keeps the id length bounded and
DuckDB-string-safe regardless of how nasty the URL is.

Default source tier: 4 (general web — operator can override for
known-good outlets via ``ingest_url(..., source_tier=2)``).

What this does NOT do (the parameter_extractor's job): mint typed
nodes + edges from the article body. Loop 1 will pick that up when
it walks the trajectory.
"""

from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime, timezone

# Repo root on path for direct invocation.
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
from substrate.schemas.events import (  # noqa: E402
    FetchFallbackEscalatedPayload,
)

from .client import FetchedHtml, fetch
from .extract import MarkdownDoc, html_to_markdown

DEFAULT_URL_SOURCE_TIER = 4
_NODE_LABEL_MAX = 160

# Minimum markdown word count below which we skip graph writes.
# Pages where the extractor returns near-empty body usually mean it
# missed the article (paywall, JS-rendered). Emitting events but
# skipping graph writes lets the operator see the failure in the
# trajectory without polluting the graph.
MIN_INGEST_WORD_COUNT = 50


# ---------------------------------------------------------------------------
# Stable document id
# ---------------------------------------------------------------------------


def url_doc_id(url: str) -> str:
    """Stable Antiek doc id for a URL. Hashes the URL so the id length
    is bounded and DuckDB-string-safe regardless of URL shape."""
    if not url:
        raise ValueError("empty url")
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"doc-url-{h}"


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IngestUrlResult:
    """What ``ingest_url`` returns. ``skipped_reason`` is non-None when
    extraction succeeded but graph writes were skipped (e.g.
    ``"low_word_count"``)."""

    document_id: str
    final_url: str
    chunk_ids: List[str] = field(default_factory=list)
    node_ids: List[str] = field(default_factory=list)
    document_loaded_event_id: Optional[str] = None
    chunks_written: int = 0
    skipped_reason: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


def _try_browserbase_escalation(
    *,
    url: str,
    primary_word_count: int,
    investigation_id: str,
    wait_for: Optional[str],
) -> Optional[FetchedHtml]:
    """Drive a Browserbase session and emit
    ``FetchFallbackEscalatedPayload`` regardless of outcome. Returns
    the new ``FetchedHtml`` on success, ``None`` on any failure so
    the caller can fall back to the original skip path."""
    from .budget_browserbase import BrowserbaseBudgetExceeded
    from .client_browserbase import (
        BrowserbaseFetchError,
        BrowserbaseRobotsDisallowed,
        BrowserbaseUnavailable,
        DEFAULT_SESSION_COST_USD,
        fetch_via_browserbase,
    )

    fallback_word_count = 0
    fetched: Optional[FetchedHtml] = None
    estimated_cost = DEFAULT_SESSION_COST_USD
    try:
        fetched = fetch_via_browserbase(url, wait_for=wait_for)
        md = html_to_markdown(fetched.body, base_url=fetched.final_url)
        fallback_word_count = md.word_count
    except (
        BrowserbaseUnavailable,
        BrowserbaseRobotsDisallowed,
        BrowserbaseBudgetExceeded,
        BrowserbaseFetchError,
        Exception,
    ):
        fetched = None
        fallback_word_count = 0

    emit_typed(
        investigation_id,
        FetchFallbackEscalatedPayload(
            url=url,
            primary_word_count=primary_word_count,
            fallback_fetcher="browserbase",
            fallback_word_count=fallback_word_count,
            escalation_reason="low_word_count",
            estimated_cost_usd=estimated_cost,
        ),
        role="acquisition",
        policy_id="acquisition/urls/browserbase",
    )
    return fetched


def ingest_url(
    url: str,
    *,
    investigation_id: str,
    source_tier: int = DEFAULT_URL_SOURCE_TIER,
    db_path: Optional[str] = None,
    embedder: Optional[EmbeddingProvider] = None,
    http_client: Optional[object] = None,
    fetched: Optional[FetchedHtml] = None,
    min_word_count: int = MIN_INGEST_WORD_COUNT,
    # Wedge 2 (Browserbase escalation) — opt-in per call (default off).
    fallback_to_browserbase: bool = False,
    browserbase_wait_for: Optional[str] = None,
) -> IngestUrlResult:
    """Fetch ``url``, extract markdown, ingest into substrate.

    ``fetched`` lets callers reuse an already-fetched body (e.g. a
    crawler that batches requests) — when set, no HTTP is performed
    and ``http_client`` is ignored.

    ``fallback_to_browserbase`` opts in to Wedge 2 escalation when
    the httpx primary fetch returns low_word_count. Per spec §7.4
    Browserbase is 1000-5000× more expensive than httpx; default off.
    """
    page: FetchedHtml = fetched or fetch(url, client=http_client)  # type: ignore[arg-type]
    md_doc: MarkdownDoc = html_to_markdown(page.body, base_url=page.final_url)

    document_id = url_doc_id(page.final_url)
    text = md_doc.markdown
    chash = "sha256:" + content_hash(text)

    payload = DocumentLoadedPayload(
        media_type="url_extracted",
        content_hash=chash,
        size_bytes=len(text.encode("utf-8")),
        title=md_doc.title,
        page_count=None,
        source_uri=page.final_url,
    )
    event_id = emit_typed(
        investigation_id,
        payload,
        document_id=document_id,
        role="acquisition",
        policy_id="acquisition/urls",
    )

    # Word-count gate. Emit the event so the operator can see the
    # fetch happened, but skip graph writes for plausibly-misextracted
    # pages — keeps the graph cleaner during dev.
    if md_doc.word_count < min_word_count:
        escalation_ran = False
        if fallback_to_browserbase and fetched is None:
            escalation_ran = True
            escalated = _try_browserbase_escalation(
                url=url,
                primary_word_count=md_doc.word_count,
                investigation_id=investigation_id,
                wait_for=browserbase_wait_for,
            )
            if escalated is not None:
                page = escalated
                md_doc = html_to_markdown(page.body, base_url=page.final_url)
                text = md_doc.markdown
                chash = "sha256:" + content_hash(text)

        if md_doc.word_count < min_word_count:
            return IngestUrlResult(
                document_id=document_id,
                final_url=page.final_url,
                document_loaded_event_id=event_id,
                skipped_reason=(
                    "low_word_count_after_fallback"
                    if escalation_ran
                    else "low_word_count"
                ),
                title=md_doc.title,
                author=md_doc.author,
            )

    resolved_db_path = db_path or default_db_path()
    ensure_initialized(resolved_db_path)

    chunks: List[Chunk] = chunk_markdown(text)
    chunk_ids: List[str] = []
    node_ids: List[str] = []
    chunks_written = 0
    emb = embedder or default_embedding_provider()

    from runtime.db_lock import connect_write

    with connect_write(resolved_db_path, purpose="acquisition/urls") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=int(source_tier),
            document_type="web_article",
            source_uri=page.final_url,
            title=md_doc.title,
            author=md_doc.author,
            published_at=None,
            investigation_id=investigation_id,
            raw_text=text,
            metadata={
                "requested_url": page.requested_url,
                "final_url": page.final_url,
                "content_type": page.content_type,
                "status_code": page.status_code,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="ignore",
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
                label = f"{document_id}#{i}"
            node_id = insert_node(
                con,
                canonical_label=label,
                node_type="entity",
                graph_scope="cross_domain",
                investigation_id=investigation_id,
                embedding=emb.encode(label),
                metadata={
                    "source": "url",
                    "final_url": page.final_url,
                    "chunk_id": chunk_id,
                    "section": chunk.section,
                },
                parent_event_id=event_id,
                on_conflict="ignore",
            )
            node_ids.append(node_id)

    return IngestUrlResult(
        document_id=document_id,
        final_url=page.final_url,
        chunk_ids=chunk_ids,
        node_ids=node_ids,
        document_loaded_event_id=event_id,
        chunks_written=chunks_written,
        title=md_doc.title,
        author=md_doc.author,
    )
