"""Ingest ``~/research/inbox/<date>/*.txt`` article dumps into the substrate.

This is the local-.txt mirror of ``acquisition.substack.adapter``: the operator's
daily reading stream is personal reading (§9.0), so every document lands with
``content_class="personal_reading"`` + ``source_kind="user"``. Writes funnel
through the single writer (``runtime.db_lock.connect_write``, §16):

    connect_write → insert_document(on_conflict="ignore", content_class=personal_reading)
                  → chunk_markdown → insert_chunk (embeddings) → insert_node (per chunk)

Idempotent: a document is content-addressed from its absolute source path, so
re-ingesting a day is a no-op (``insert_document`` dedups on ``document_id`` and
``insert_chunk`` is content-addressed). A corrupted/empty ``.txt`` is skipped and
logged in ``errors`` — it never aborts the whole day (rigor: partial-state
enumerated, not discovered in review).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

# sys.path bootstrap — mirrors acquisition/substack/adapter.py so the package
# imports resolve when run as a script / from tools/run_corpus_ingest.py.
_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from processing.chunking.chunker import (  # noqa: E402
    chunk_markdown,
    content_hash,
)
from processing.embedding.embed import (  # noqa: E402
    EmbeddingProvider,
    default_embedding_provider,
)
from runtime.db_lock import connect_write  # noqa: E402
from substrate.constants import PERSONAL_READING_CONTENT_CLASS  # noqa: E402
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

# General-web tier (4), consistent with acquisition/substack + acquisition/urls
# for unranked/personal web sources. Module constant (the sibling convention) —
# NOT a content_class, so the corpus_audit literal-bypass scan is unaffected.
DEFAULT_INBOX_SOURCE_TIER = 4
_NODE_LABEL_MAX = 160


@dataclass(frozen=True)
class InboxFileResult:
    """Outcome of ingesting one ``.txt`` article."""

    document_id: str
    source_uri: str
    status: str  # "ingested" | "skipped"
    chunks_written: int = 0


@dataclass(frozen=True)
class InboxDayResult:
    """Aggregated outcome of ingesting one inbox day-directory."""

    day_path: str
    files_seen: int = 0
    documents_added: int = 0
    chunks_added: int = 0
    skipped_dup: int = 0
    file_results: list[InboxFileResult] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)


def _inbox_doc_id(source_uri: str) -> str:
    """Content-addressed document id from the absolute source path (dedup key)."""
    return "inbox:" + content_hash(source_uri)


def ingest_inbox_file(
    path: str,
    *,
    investigation_id: str,
    db_path: str | None = None,
    source_tier: int = DEFAULT_INBOX_SOURCE_TIER,
    embedder: EmbeddingProvider | None = None,
) -> InboxFileResult:
    """Ingest one ``.txt`` article into documents + chunks + nodes.

    §9.0: ``content_class="personal_reading"`` (owner-readable / public-non-
    servable lane) — the inbox is the operator's personal reading stream.
    Idempotent on ``document_id`` (content-addressed from the abs path).
    """
    resolved_db = db_path or default_db_path()
    ensure_initialized(resolved_db)
    source_uri = os.path.abspath(path)
    document_id = _inbox_doc_id(source_uri)

    with open(path, encoding="utf-8", errors="replace") as fh:
        full_text = fh.read()

    provider = embedder if embedder is not None else default_embedding_provider()
    title = os.path.splitext(os.path.basename(path))[0]

    with connect_write(resolved_db) as con:
        if _exists(con, "documents", "document_id", document_id):
            return InboxFileResult(
                document_id=document_id, source_uri=source_uri, status="skipped"
            )
        insert_document(
            con,
            document_id=document_id,
            source_tier=source_tier,
            document_type="article",
            source_uri=source_uri,
            title=title,
            raw_text=full_text,
            content_class=PERSONAL_READING_CONTENT_CLASS,
            investigation_id=investigation_id,
            on_conflict="ignore",
        )
        chunks_written = 0
        for index, chunk in enumerate(chunk_markdown(full_text)):
            cid = insert_chunk(
                con,
                document_id=document_id,
                chunk_index=index,
                text=chunk.text,
                embedding=provider.encode(chunk.text),
                token_count=getattr(chunk, "token_count", 0) or 0,
            )
            # Node label = first non-empty line (mirrors acquisition/substack).
            label = chunk.text.strip().splitlines()[0] if chunk.text.strip() else ""
            if len(label) > _NODE_LABEL_MAX:
                label = label[: _NODE_LABEL_MAX - 1] + "…"
            if not label:
                label = f"{document_id}#{index}"
            insert_node(
                con,
                canonical_label=label,
                node_type="entity",
                graph_scope="cross_domain",
                investigation_id=investigation_id,
                embedding=provider.encode(label),
                # on_conflict="ignore": a node is content-addressed on
                # label|entity|cross_domain, so two documents that share a
                # chunk's first line (e.g. a duplicate article saved under a
                # new filename) map to the SAME node_id. "ignore" makes that a
                # clean no-op instead of a primary-key crash — full idempotency
                # at every layer (document, chunk, node are all content-addressed).
                on_conflict="ignore",
                metadata={
                    "source": "inbox",
                    "chunk_id": cid,
                    "document_id": document_id,
                },
            )
            chunks_written += 1
    return InboxFileResult(
        document_id=document_id,
        source_uri=source_uri,
        status="ingested",
        chunks_written=chunks_written,
    )


def ingest_inbox_day(
    day_path: str,
    *,
    investigation_id: str,
    db_path: str | None = None,
    source_tier: int = DEFAULT_INBOX_SOURCE_TIER,
    embedder: EmbeddingProvider | None = None,
) -> InboxDayResult:
    """Ingest every ``*.txt`` under ``day_path`` (one inbox day-directory).

    A corrupted/empty file is skipped + logged in ``errors``; it never aborts
    the day. Returns the aggregated ``InboxDayResult``.
    """
    if not os.path.isdir(day_path):
        return InboxDayResult(
            day_path=day_path,
            errors=[{"file": day_path, "reason": "not a directory"}],
        )
    txt_files = sorted(
        os.path.join(day_path, name)
        for name in os.listdir(day_path)
        if name.lower().endswith(".txt") and os.path.isfile(os.path.join(day_path, name))
    )
    # Accumulate into locals, then build the (frozen) result once —
    # InboxDayResult is frozen, so in-place += on it would FrozenInstanceError.
    file_results: list[InboxFileResult] = []
    errors: list[dict[str, str]] = []
    documents_added = 0
    chunks_added = 0
    skipped_dup = 0
    for path in txt_files:
        try:
            file_result = ingest_inbox_file(
                path,
                investigation_id=investigation_id,
                db_path=db_path,
                source_tier=source_tier,
                embedder=embedder,
            )
            file_results.append(file_result)
            if file_result.status == "ingested":
                documents_added += 1
                chunks_added += file_result.chunks_written
            else:
                skipped_dup += 1
        except Exception as exc:  # noqa: BLE001 — surface, never abort the day
            errors.append({"file": path, "reason": f"{type(exc).__name__}: {exc}"})
    return InboxDayResult(
        day_path=os.path.abspath(day_path),
        files_seen=len(txt_files),
        documents_added=documents_added,
        chunks_added=chunks_added,
        skipped_dup=skipped_dup,
        file_results=file_results,
        errors=errors,
    )
