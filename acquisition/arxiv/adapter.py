"""arXiv → Antiek substrate adapter.

Converts an ``ArxivPaper`` into typed substrate events + graph rows:

1. Emit ``document.loaded`` with the abstract as ``markdown``
   media_type. ``source_uri`` = abs URL; ``content_hash`` = sha256
   of the abstract.
2. Insert a ``documents`` row with stable doc id
   ``doc-arxiv-<sanitized_id>``. arXiv preprints default to source
   tier 3 (academic but not peer-reviewed); caller can override.
3. Chunk the abstract via ``processing.chunking.chunk_markdown``.
   Insert each chunk into the ``chunks`` table; insert one
   ``substrate/graph`` node per chunk (label = truncated text).

Result: ``IngestResult`` with ``document_id``, ``chunk_ids``,
``node_ids``, and the emitted ``document.loaded`` event id.

**Idempotency:** the doc id is content-stable (derived from the
arxiv id), and ``insert_document`` / ``insert_chunk`` / ``insert_node``
all use ``on_conflict='ignore'`` so re-ingesting the same paper
no-ops on the DB side. The ``document.loaded`` event still fires
each time — the trajectory log is append-only by design.

**What this does NOT do** (Sprint 10 day 3-4 + 4-5 work):
- Fetch the full-text PDF and extract its content. Use
  ``acquisition/books/`` once that lands.
- Run the ``parameter_extractor`` role to mint nodes + edges from
  the abstract. That's the Loop 1 orchestrator's job; this adapter
  just lands the source.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from typing import List, Optional

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

from .client import ArxivPaper

# Tier policy: arXiv preprints are academic but unrefereed → tier 3.
# Tier 1 = peer-reviewed primary; Tier 5 = uncited social. The
# operator can override via ``ingest_paper(..., source_tier=N)``.
DEFAULT_ARXIV_SOURCE_TIER = 3

# Cap on node label length. The full title would blow past graph
# search ergonomics; truncated with ellipsis matches the
# wrestling-bridge convention.
_NODE_LABEL_MAX = 160


# ---------------------------------------------------------------------------
# Stable document id
# ---------------------------------------------------------------------------


_ARXIV_ID_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9.\-]")


def arxiv_doc_id(arxiv_id: str) -> str:
    """Stable Antiek doc id for an arXiv paper.

    Same arXiv id → same doc id across sessions, so a paper
    resurfacing in a new search dedups against prior ingestion.
    Sanitization keeps only ``[A-Za-z0-9.-]`` so DuckDB string
    handling stays simple."""
    sanitized = _ARXIV_ID_SANITIZE_RE.sub("-", arxiv_id.strip())
    if not sanitized:
        raise ValueError(f"empty/unrepresentable arxiv_id: {arxiv_id!r}")
    return f"doc-arxiv-{sanitized}"


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IngestResult:
    """What ``ingest_paper`` returns. ``document_loaded_event_id`` is
    ``None`` when the event log is disabled
    (``ANTIEK_EVENTS_DISABLED``); the DB writes still happen."""

    document_id: str
    chunk_ids: List[str] = field(default_factory=list)
    node_ids: List[str] = field(default_factory=list)
    document_loaded_event_id: Optional[str] = None
    chunks_written: int = 0


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


def _format_abstract_markdown(paper: ArxivPaper) -> str:
    """Compose the abstract + light header so the chunker's
    heading-aware splitter has anchor metadata in the body.

    Authors + categories ride along so downstream nodes mint by
    parameter_extractor have access to provenance without re-fetch."""
    lines = [
        f"# {paper.title}",
        "",
        f"_arXiv {paper.arxiv_id}{paper.version} · {paper.abs_url}_",
        "",
    ]
    if paper.authors:
        lines.append("**Authors:** " + ", ".join(paper.authors))
        lines.append("")
    if paper.categories:
        lines.append("**Categories:** " + ", ".join(paper.categories))
        lines.append("")
    lines.append("## Abstract")
    lines.append("")
    lines.append(paper.abstract)
    return "\n".join(lines)


def ingest_paper(
    paper: ArxivPaper,
    *,
    investigation_id: str,
    source_tier: int = DEFAULT_ARXIV_SOURCE_TIER,
    db_path: Optional[str] = None,
    embedder: Optional[EmbeddingProvider] = None,
) -> IngestResult:
    """Ingest one arXiv abstract into the substrate.

    Emits ``document.loaded`` (typed), writes a ``documents`` row,
    chunks the abstract, writes chunks + per-chunk nodes. All DB
    writes are idempotent on the doc id; re-ingesting the same
    arXiv id is a no-op for the graph rows (the event still fires).

    ``investigation_id`` scopes the event + the node's
    ``investigation_id`` foreign key. For corpus-scoped sweeps not
    tied to a single investigation, callers can pass
    ``substrate.constants.SYSTEM_INVESTIGATION_ID``."""

    text = _format_abstract_markdown(paper)
    chash = "sha256:" + content_hash(text)
    document_id = arxiv_doc_id(paper.arxiv_id)

    # Emit document.loaded first so the trajectory carries the
    # ingestion signal before the graph rows land. The reading-UI
    # surface follows this ordering too.
    payload = DocumentLoadedPayload(
        media_type="markdown",
        content_hash=chash,
        size_bytes=len(text.encode("utf-8")),
        title=paper.title,
        page_count=None,
        source_uri=paper.abs_url,
    )
    event_id = emit_typed(
        investigation_id,
        payload,
        document_id=document_id,
        role="acquisition",
        policy_id="acquisition/arxiv",
    )

    # Open the DB. ensure_initialized creates the file + schema if
    # this is the operator's first ingest.
    resolved_db_path = db_path or default_db_path()
    ensure_initialized(resolved_db_path)

    chunks: List[Chunk] = chunk_markdown(text)
    chunk_ids: List[str] = []
    node_ids: List[str] = []
    chunks_written = 0

    emb = embedder or default_embedding_provider()

    # The graph schema requires LockedConnection. Open via the
    # write-lock helper so concurrent ingests serialize correctly.
    from runtime.db_lock import connect_write

    with connect_write(resolved_db_path, purpose="acquisition/arxiv") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=int(source_tier),
            document_type="academic_paper",
            source_uri=paper.abs_url,
            title=paper.title,
            author=", ".join(paper.authors) if paper.authors else None,
            published_at=paper.published_at,
            investigation_id=investigation_id,
            raw_text=text,
            metadata={
                "arxiv_id": paper.arxiv_id,
                "version": paper.version,
                "categories": list(paper.categories),
                "primary_category": paper.primary_category,
                "updated_at": paper.updated_at.isoformat(),
                "pdf_url": paper.pdf_url,
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
                label = f"{paper.arxiv_id}#{i}"

            node_id = insert_node(
                con,
                canonical_label=label,
                node_type="entity",
                graph_scope="cross_domain",
                investigation_id=investigation_id,
                embedding=emb.encode(label),
                metadata={
                    "source": "arxiv",
                    "arxiv_id": paper.arxiv_id,
                    "chunk_id": chunk_id,
                    "section": chunk.section,
                },
                parent_event_id=event_id,
                on_conflict="ignore",
            )
            node_ids.append(node_id)

    return IngestResult(
        document_id=document_id,
        chunk_ids=chunk_ids,
        node_ids=node_ids,
        document_loaded_event_id=event_id,
        chunks_written=chunks_written,
    )
