"""Servable-corpus query API (Read SPR-01 M6).

The thin HTTP surface the Library (SPR-02) and Reader (SPR-03) consume.
The legal gate lives in the substrate (``substrate/books/``); this router
only adapts it to HTTP. Two guarantees it inherits, not re-implements:

- A gated book is returned in listings/detail FLAGGED (its servability
  status is always present) but its full text is never inline.
- The ``/full-text`` endpoint routes through ``substrate.books.serve``,
  so the deny-by-default gate is enforced at the data layer regardless of
  what the caller asks for.

Endpoints:

  GET /books                         list servable books (default)
  GET /books?status=gated            list gated metadata-only books
  GET /books?status=all              list both, each flagged
  GET /books/{document_id}           book detail + TOC (never full text)
  GET /books/{document_id}/full-text serve full text (gated by serve.py)

All endpoints are reads; they use ``connect_read`` and run concurrently
with the single writer.
"""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.books.model import BookAsset, get_book_asset, list_book_assets
from substrate.books.serve import serve_full_text


def _resolve_db_path() -> str:
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


# ── Response shapes ─────────────────────────────────────────────────


class TocItemResponse(BaseModel):
    title: str
    page_index: Optional[int]
    level: int


class BookSummary(BaseModel):
    document_id: str
    title: Optional[str]
    author: Optional[str]
    servability: str
    servable_full_text: bool
    page_count: int
    cover_uri: Optional[str]
    ip_holder_id: Optional[str]
    taken_down: bool

    @classmethod
    def from_asset(cls, a: BookAsset) -> "BookSummary":
        return cls(
            document_id=a.document_id,
            title=a.title,
            author=a.author,
            servability=a.servability.value,
            servable_full_text=a.servable_full_text,
            page_count=a.page_count,
            cover_uri=a.cover_uri,
            ip_holder_id=a.ip_holder_id,
            taken_down=a.taken_down,
        )


class BookDetail(BookSummary):
    pagination_scheme: str
    provenance: Optional[str]
    license_basis: Optional[str]
    toc: list[TocItemResponse]

    @classmethod
    def from_asset(cls, a: BookAsset) -> "BookDetail":
        return cls(
            **BookSummary.from_asset(a).model_dump(),
            pagination_scheme=a.pagination_scheme,
            provenance=a.provenance,
            license_basis=a.license_basis,
            toc=[
                TocItemResponse(title=t.title, page_index=t.page_index, level=t.level)
                for t in a.toc
            ],
        )


class BookListResponse(BaseModel):
    books: list[BookSummary]
    count: int


class CuratedBookResponse(BaseModel):
    document_id: str
    title: Optional[str]
    author: Optional[str]
    score: float


class CurateResponse(BaseModel):
    prompt: str
    books: list[CuratedBookResponse]


class SpinResearchRequest(BaseModel):
    page_index: int = Field(ge=0)
    # The reader's selected text. For a gated book it is IGNORED server-
    # side and replaced by the bounded snippet — the seed can never carry
    # gated full text, even if the client sends it (defense in depth).
    passage_text: Optional[str] = None


class SpinResearchResponse(BaseModel):
    investigation_id: str
    document_id: str
    page_index: int
    gated: bool
    servability: str
    seed_preview: str


class ImpressionItem(BaseModel):
    slot_id: str = Field(min_length=1, max_length=128)
    page_index: int = Field(ge=0)
    fill_kind: Literal["ad", "house"]
    revenue_usd_cents: int = Field(ge=0, default=0)
    focused_dwell_ms: int = Field(ge=0, default=0)
    tab_focused: bool = True


class RecordImpressionsRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    impressions: list[ImpressionItem] = Field(default_factory=list)


class RecordImpressionsResponse(BaseModel):
    document_id: str
    recorded: int
    attention_impressions: int
    accrued_to_escrow_cents: int


class FullTextResponse(BaseModel):
    document_id: str
    servable: bool
    servability: Optional[str]
    full_text: Optional[str]
    snippet: Optional[str]
    title: Optional[str]
    author: Optional[str]
    reason: str


# ── Routes ──────────────────────────────────────────────────────────


def register_book_routes(app: FastAPI) -> None:
    """Mount the servable-corpus query routes. Mirrors
    ``register_advertiser_routes`` — one call from ``create_app``."""

    @app.get("/books", response_model=BookListResponse, tags=["books"])
    async def list_books(
        status: Literal["servable", "gated", "all"] = "servable",
    ) -> BookListResponse:
        from runtime.db_lock import connect_read

        db = _resolve_db_path()
        con = connect_read(db)
        try:
            if status == "servable":
                assets = list_book_assets(con, servable_only=True)
            else:
                # "gated" and "all" both list non-taken-down books; the
                # servability flag on each lets the caller filter. We never
                # widen to taken-down books on a public listing.
                assets = list_book_assets(con, servable_only=False)
                if status == "gated":
                    assets = [a for a in assets if not a.servable_full_text]
        finally:
            con.close()
        summaries = [BookSummary.from_asset(a) for a in assets]
        return BookListResponse(books=summaries, count=len(summaries))

    # Registered BEFORE /books/{document_id} so "curate" is not matched as
    # a document id.
    @app.get("/books/curate", response_model=CurateResponse, tags=["books"])
    async def curate(prompt: str, limit: int = 20) -> CurateResponse:
        from runtime.db_lock import connect_read
        from substrate.books.curate import curate_reading_list
        from substrate.graph.search import SentenceTransformerEmbedding

        try:
            model = SentenceTransformerEmbedding()
        except RuntimeError as exc:  # sentence-transformers not installed
            raise HTTPException(status_code=503, detail=f"embedding_unavailable: {exc}") from exc

        db = _resolve_db_path()
        con = connect_read(db)
        try:
            curated = curate_reading_list(con, prompt, model=model, limit=limit)
        finally:
            con.close()
        return CurateResponse(
            prompt=prompt,
            books=[
                CuratedBookResponse(
                    document_id=c.document_id, title=c.title, author=c.author, score=c.score
                )
                for c in curated
            ],
        )

    @app.get("/books/{document_id}", response_model=BookDetail, tags=["books"])
    async def get_book(document_id: str) -> BookDetail:
        from runtime.db_lock import connect_read

        db = _resolve_db_path()
        con = connect_read(db)
        try:
            asset = get_book_asset(con, document_id)
        finally:
            con.close()
        if asset is None:
            raise HTTPException(status_code=404, detail="book_not_found")
        return BookDetail.from_asset(asset)

    @app.get(
        "/books/{document_id}/full-text",
        response_model=FullTextResponse,
        tags=["books"],
    )
    async def get_book_full_text(document_id: str) -> FullTextResponse:
        from runtime.db_lock import connect_read

        db = _resolve_db_path()
        con = connect_read(db)
        try:
            result = serve_full_text(con, document_id)
        finally:
            con.close()
        if not result.found:
            raise HTTPException(status_code=404, detail="book_not_found")
        return FullTextResponse(
            document_id=result.document_id,
            servable=result.servable,
            servability=result.servability.value if result.servability else None,
            full_text=result.full_text,
            snippet=result.snippet,
            title=result.title,
            author=result.author,
            reason=result.reason,
        )

    @app.post(
        "/books/{document_id}/ad-impressions",
        response_model=RecordImpressionsResponse,
        status_code=202,
        tags=["books"],
    )
    async def record_ad_impressions(
        document_id: str, req: RecordImpressionsRequest
    ) -> RecordImpressionsResponse:
        """Record reader ad impressions + attention for a session and
        accrue to the book's rights-holder escrow (Read SPR-05 → SPR-09).

        The browser flushes a session's slot impressions here. The
        attention rule (focused dwell ≥ threshold; idle tab excluded) is
        applied SERVER-SIDE — the client's claimed attention is not
        trusted. Accrual reuses ``accrue_reading_session`` (dedup by
        impression_id, zero-buyer-safe, accrual≠disbursement)."""
        from runtime.db_lock import connect_write
        from substrate.ad_inventory.reader_impressions import record_raw_impression
        from substrate.marketplace_metrics.book_escrow import accrue_reading_session

        impressions = [
            record_raw_impression(
                session_id=req.session_id,
                document_id=document_id,
                slot_id=item.slot_id,
                page_index=item.page_index,
                fill_kind=item.fill_kind,
                revenue_usd_cents=item.revenue_usd_cents,
                focused_dwell_ms=item.focused_dwell_ms,
                tab_focused=item.tab_focused,
            )
            for item in req.impressions
        ]
        db = _resolve_db_path()
        con = connect_write(db, purpose="read/ad_impressions")
        try:
            result = accrue_reading_session(
                con,
                document_id=document_id,
                impressions=impressions,
                session_id=req.session_id,
            )
        finally:
            con.close()
        return RecordImpressionsResponse(
            document_id=document_id,
            recorded=len(impressions),
            attention_impressions=result.attention_impressions,
            accrued_to_escrow_cents=result.accrued_to_escrow_cents,
        )

    @app.post(
        "/books/{document_id}/spin-research",
        response_model=SpinResearchResponse,
        status_code=202,
        tags=["books"],
    )
    async def spin_research(document_id: str, req: SpinResearchRequest) -> SpinResearchResponse:
        """Spin a deep research from a book passage (Read SPR-08).

        Builds the GATE-SAFE seed server-side (a gated book contributes
        only its snippet + metadata, never full text — even if the client
        sent the passage body), requests a child investigation seeded with
        it, and records the two-way passage↔research provenance link. The
        seed is built and consumed here so gated full text never crosses
        into a research via the browser.
        """
        from runtime.db_lock import connect_read
        from substrate.books.passage_research import (
            build_research_seed,
            link_passage_to_research,
        )
        from substrate.event_log import emit_typed
        from substrate.schemas import InvestigationStartRequestedPayload

        db = _resolve_db_path()
        con = connect_read(db)
        try:
            seed = build_research_seed(
                con,
                document_id=document_id,
                page_index=req.page_index,
                passage_text=req.passage_text,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        finally:
            con.close()

        import uuid as _uuid

        investigation_id = f"inv-{_uuid.uuid4().hex[:12]}"
        spawn_context = f"read: passage {document_id} p{req.page_index}"
        event_id = emit_typed(
            investigation_id,
            InvestigationStartRequestedPayload(
                question=seed.seed_text,
                context=f"Spun from a book passage. Servability: {seed.servability}.",
                spawn_context=spawn_context,
            ),
            role="read/spin_research",
            policy_id="read/books/spin_research",
        )
        if event_id is None:
            raise HTTPException(
                status_code=503,
                detail="Event log is disabled (ANTIEK_EVENTS_DISABLED).",
            )
        link_passage_to_research(
            document_id=document_id,
            page_index=req.page_index,
            investigation_id=investigation_id,
        )
        return SpinResearchResponse(
            investigation_id=investigation_id,
            document_id=document_id,
            page_index=req.page_index,
            gated=seed.gated,
            servability=seed.servability,
            seed_preview=seed.seed_text[:240] + ("…" if len(seed.seed_text) > 240 else ""),
        )
