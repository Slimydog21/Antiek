"""Cross-document links HTTP API (SPR-07 / M1).

FastAPI route handler for:

  POST /api/cross_doc/links — given an operator highlight, return up to
                              top_k connected passages (gutter pills).

The substrate-side ``services.cross_doc.query.get_cross_doc_links``
does the score-fusion across similarity / user-asserted / citation legs;
this handler is the HTTP wrapper. The TS client at
``apps/reading/api/cross_doc/links.ts`` POSTs the same body shape and
consumes the response array.

Distinct from ``cross_doc.py`` in the same directory — that's the
old bus-based handler for `cross_doc.question_answered` events.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from services.cross_doc.query import (  # noqa: E402
    DEFAULT_MAX_PER_DOCUMENT,
    DEFAULT_TOP_K,
    Highlight,
    get_cross_doc_links,
)
from substrate.graph.search import SentenceTransformerEmbedding  # noqa: E402
from runtime.db_lock import connect_read  # noqa: E402


class HighlightModel(BaseModel):
    document_id: str = Field(min_length=1)
    page: int = Field(ge=0)
    bbox: list[float] = Field(min_length=4, max_length=4)
    selected_text: str = Field(min_length=1)


class CrossDocLinksRequest(BaseModel):
    """Body for ``POST /api/cross_doc/links``."""

    highlight: HighlightModel
    top_k: int = Field(ge=1, le=10, default=DEFAULT_TOP_K)
    include_public_graph: bool = False
    policy_tag: str = "operator_only"
    max_per_document: int = Field(ge=1, le=10, default=DEFAULT_MAX_PER_DOCUMENT)


class CrossDocLinkOut(BaseModel):
    chunk_id: str
    doc_title: str
    document_id: str
    page: int
    snippet: str
    score: float
    source: str
    source_tier: int


def register_cross_doc_links_routes(
    app: FastAPI,
    *,
    db_path: Optional[str] = None,
    embedder: Optional[Any] = None,
) -> None:
    """Mount cross-doc-links routes on ``app``."""

    _embedder_singleton = embedder or SentenceTransformerEmbedding()

    @app.post(
        "/api/cross_doc/links",
        response_model=list[CrossDocLinkOut],
        tags=["cross-doc"],
    )
    async def post_cross_doc_links(
        body: CrossDocLinksRequest,
    ) -> list[CrossDocLinkOut]:
        h = body.highlight
        try:
            x0, y0, x1, y1 = h.bbox
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "bad_bbox", "message": str(exc)}},
            ) from exc

        highlight = Highlight(
            document_id=h.document_id,
            page=h.page,
            bbox=(x0, y0, x1, y1),
            selected_text=h.selected_text,
        )

        # Read-only path is fine here; the substrate edges are
        # never mutated by the gutter.
        with connect_read(db_path) as con:
            links = get_cross_doc_links(
                highlight,
                con=con,
                model=_embedder_singleton,
                top_k=body.top_k,
                include_public_graph=body.include_public_graph,
                policy_tag=body.policy_tag,
                max_per_document=body.max_per_document,
            )

        return [
            CrossDocLinkOut(
                chunk_id=link.chunk_id,
                doc_title=link.doc_title,
                document_id=link.document_id,
                page=link.page,
                snippet=link.snippet,
                score=link.score,
                source=link.source,
                source_tier=link.source_tier,
            )
            for link in links
        ]
