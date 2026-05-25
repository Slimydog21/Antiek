"""Prompt-to-curate — natural-language curation over the servable corpus
(Read SPR-04, backend).

The reader types a prompt ("stoicism for someone burned out") and gets a
curated reading list. The load-bearing decision: curation ranks **only
servable books**. The servable-corpus allowlist is baked into the SQL, so
a gated book can never be curated into a reading list — it wouldn't be
readable if it were. This is the same deny-by-default gate as
``substrate.books.serve``, applied to ranking instead of serving, so the
two can't drift.

Ranking reuses ``cosine_similarity_sql`` from the existing vector-search
layer (no second similarity implementation): the prompt is embedded once,
then each servable book is scored by its best-matching chunk. The
embedding model is injected (a Protocol), exactly as ``search.py`` does —
production passes ``SentenceTransformerEmbedding``; tests pass a stub.

v1 curates over the corpus Antiek already has. Web discovery (Exa) to pull
*new* candidate titles before they're ingested is a deliberate extension,
not part of this function — and it would still land each discovered title
through the SPR-01 servability gate before it could be curated.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.constants import SERVABLE_CONTENT_CLASSES
from substrate.graph.search import EmbeddingModel, cosine_similarity_sql


@dataclass(frozen=True)
class CuratedBook:
    document_id: str
    title: str | None
    author: str | None
    score: float


def curate_reading_list(
    con: Any,
    prompt: str,
    *,
    model: EmbeddingModel,
    limit: int = 20,
) -> list[CuratedBook]:
    """Rank servable books by relevance to ``prompt``.

    Embeds the prompt once and scores each servable, non-taken-down book
    by its best-matching chunk's cosine similarity. Gated / taken-down /
    non-book documents never appear — the servable allowlist is enforced
    in the WHERE clause, not in post-filtering, so there is no window in
    which a non-servable title leaks into a reading list.
    """
    if not prompt.strip():
        return []
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")

    query_vec = list(model.encode(prompt))
    dim = model.dimension
    if len(query_vec) != dim:
        raise ValueError(
            f"EmbeddingModel.encode returned {len(query_vec)} dims; "
            f"model.dimension is {dim}. Match them."
        )
    sim_expr = cosine_similarity_sql("c.embedding", query_vec, dim)

    placeholders = ",".join("?" for _ in SERVABLE_CONTENT_CLASSES)
    sql = f"""
        SELECT d.document_id, d.title, d.author, MAX({sim_expr}) AS score
        FROM chunks c
        JOIN documents d ON c.document_id = d.document_id
        JOIN book_assets b ON b.document_id = d.document_id
        WHERE c.embedding IS NOT NULL
          AND d.document_type = 'book'
          AND b.taken_down = FALSE
          AND d.content_class IN ({placeholders})
        GROUP BY d.document_id, d.title, d.author
        ORDER BY score DESC
        LIMIT ?
    """
    params: list[Any] = [*sorted(SERVABLE_CONTENT_CLASSES), int(limit)]
    rows = con.execute(sql, params).fetchall()
    return [
        CuratedBook(document_id=r[0], title=r[1], author=r[2], score=round(float(r[3]), 4))
        for r in rows
    ]
