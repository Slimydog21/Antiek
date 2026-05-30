"""Full-text search indexing for a stored T1 arXiv body (SPR-04 M3).

Once the storage layer (M2) has written a T1 paper's extracted body to
``documents.raw_text`` and promoted its ``content_class`` to a servable class,
the body must become SEARCHABLE — otherwise a compliant, hostable paper is
invisible to the retrieval layer that the whole corpus exists to feed.

This module does ONE thing: chunk the body and write the chunks (with
embeddings) through the SAME substrate path every other ingest uses — the
``processing.chunking.chunker.chunk_markdown`` splitter and
``substrate.graph.ops.insert_chunk``. It does NOT re-implement chunking, id
allocation, or embedding (diligence bar 4). It deliberately does NOT mint graph
nodes: the abstract-ingest path already lands per-chunk nodes for the same
``arxiv_doc_id`` (``acquisition.arxiv.adapter.ingest_paper``), and the §14.4
parameter_extractor role owns node/edge extraction from a body. This module's job
is the retrieval index, not the knowledge graph.

The embedder is injected as the ``EmbeddingModel`` Protocol
(``substrate.graph.search.EmbeddingModel`` / ``processing.embedding.embed``):
production passes the real sentence-transformers model; CI passes a deterministic
fake so a test never loads a multi-hundred-MB model. ``insert_chunk`` is
idempotent on a content-addressed chunk id, so re-indexing the same body (a
re-fetch) is a no-op rather than a duplicate-key error.
"""

from __future__ import annotations

from typing import List

from processing.chunking.chunker import Chunk, chunk_markdown
from processing.embedding.embed import EmbeddingProvider
from runtime.db_lock import LockedConnection
from substrate.graph.ops import insert_chunk


def index_body(
    con: LockedConnection,
    *,
    document_id: str,
    body: str,
    embedder: EmbeddingProvider,
) -> List[str]:
    """Chunk ``body`` and write each chunk (embedded) for ``document_id``.

    Runs on the caller's already-held ``LockedConnection`` so it joins the SAME
    single-writer critical section the storage write opened — the body write and
    its index land atomically under one lock, not as two racing writers.

    Returns the list of chunk ids written (idempotent: a re-index of the same
    body returns the same ids and inserts nothing new). An empty / whitespace
    body yields no chunks and writes nothing — the caller (M2) has already
    refused to store a husk, so this is just a defensive no-op.
    """
    if not body or not body.strip():
        return []

    chunks: List[Chunk] = chunk_markdown(body)
    chunk_ids: List[str] = []
    for i, chunk in enumerate(chunks):
        chunk_id = insert_chunk(
            con,
            document_id=document_id,
            chunk_index=i,
            text=chunk.text,
            section_path=chunk.section or None,
            embedding=embedder.encode(chunk.text),
            token_count=chunk.token_count,
        )
        chunk_ids.append(chunk_id)
    return chunk_ids


__all__ = ["index_body"]
