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

import json
import logging
from typing import Literal, cast
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from substrate.books.model import BookAsset, get_book_asset, list_book_assets
from substrate.books.serve import ServeResult

from .operator_allowlist import operator_allowlist_from_env
from .serve_guard import serve_full_text_guarded

logger = logging.getLogger("antiek.interfaces.books")

# §9.0 owner-read policy tags. The owner's OWN-corpus read path (talk-to-book +
# corpus search) passes the PRIVILEGED ``operator_only`` tag so the retrieval
# gate admits the owner's gated/personal content; everything else stays on the
# non-privileged default. The string is the canonical privileged tag from
# ``substrate.graph.retrieval_gate.PRIVILEGED_POLICY_TAGS`` — kept here as a
# named local so the owner-read intent is legible at the call site (the gate
# module remains the single source of which tags are privileged).
_OWNER_READ_POLICY_TAG = "operator_only"
_PUBLIC_READ_POLICY_TAG = "attribution_eligible"

# Auth methods the middleware (``app.py::_operator_auth_middleware``) stamps on
# ``request.state.auth_method`` once a caller has PROVEN owner identity with a
# real credential. These four are the ONLY paths past the middleware when
# enforcement is ON (an unauthenticated caller is 401'd and never reaches the
# endpoint), so each one is a positive proof that THIS request is the owner.
#
# ``unauthenticated_local`` is deliberately EXCLUDED: it means enforcement is
# OFF (no ANTIEK_OPERATOR_EMAIL / _TOKEN / _SECRET set). The §9.0 gated-content
# bypass must bind to a real credential, never to "auth happened to be disabled"
# — otherwise a box accidentally deployed without auth would serve the owner's
# gated/personal corpus to any caller. Fail-closed by construction: the bypass
# is granted only on an explicit authenticated method, never by default. (The
# rest of the app gives ``unauthenticated_local`` full operator SCOPES for
# local dev convenience; the §9.0 retrieval bypass is held to the stricter
# bar deliberately — see the handoff steelman.)
#
# ── SINGLE-OPERATOR ENFORCEMENT (CLAUDE.md invariant #5) ─────────────────────
# ``authenticated ⇒ owner`` holds ONLY under the single-operator invariant.
# ``ANTIEK_OPERATOR_EMAIL`` is parsed as a COMMA-SEPARATED allowlist
# (app.py:1215), and this helper keys on ``auth_method`` — it never consults
# ``request.state``'s ``user_id`` / ``user_email``, and ``search()`` applies no
# ``owner_user_id`` filter (the column exists, schema.py:81). So with TWO+
# operator emails, two distinct tenants would both authenticate and a shared
# ``operator_only`` could read each other's ``personal_reading`` corpus.
# ``_owner_read_policy_tag`` therefore grants the privilege ONLY when the
# deployment is provably single-operator (``operator_allowlist_from_env``
# resolves ≤ 1 operator); a multi-operator config FAILS CLOSED to the
# non-privileged tag, so the cross-tenant path is STRUCTURALLY IMPOSSIBLE, not
# merely documented. When Sprint-22 multi-user lands, restoring multi-operator
# owner-read requires scoping retrieval by ``request.state.user_id`` against
# ``owner_user_id``; ``operator_only`` alone is not sufficient.
_OWNER_AUTH_METHODS: frozenset[str] = frozenset({
    "antiek_session_cookie",
    "cloudflare_access_email",
    "cloudflare_service_token",
    "bearer_token",
})


def _owner_read_policy_tag(request: Request) -> str:
    """Resolve the §9.0 retrieval policy_tag for an OWNER read endpoint.

    Returns the PRIVILEGED ``operator_only`` tag ONLY when the auth middleware
    has stamped ``request.state.auth_method`` with one of the four AUTHENTICATED
    methods (a real credential proven: session cookie, Cloudflare Access email,
    Cloudflare service token, or operator bearer). For ANY other value — see the
    ``_OWNER_AUTH_METHODS`` comment above for why ``unauthenticated_local`` and
    absent state are EXCLUDED (the fail-closed, bind-to-a-real-credential rule) —
    it returns the non-privileged default, so the §9.0 gate keeps excluding
    gated/personal content. The privileged bypass requires a positive,
    middleware-set authenticated signal; it is NEVER the default.

    The signal is SERVER-DERIVED: ``auth_method`` is written only by the auth
    middleware on the request object; a caller cannot set ``request.state`` or
    spoof it via a header/param. When enforcement is on, a non-owner caller is
    rejected with 401 BEFORE this runs, so it can only ever see owner requests.

    PRIVILEGE == OWNER is ENFORCED, not merely assumed: the bypass is granted
    only when the deployment is single-operator (``operator_allowlist_from_env``
    resolves ≤ 1 operator); a multi-operator config FAILS CLOSED to the
    non-privileged tag. See the SINGLE-OPERATOR ENFORCEMENT note above
    ``_OWNER_AUTH_METHODS``.
    """
    auth_method = getattr(getattr(request, "state", None), "auth_method", None)
    # SINGLE-OPERATOR ENFORCEMENT: the privilege is owner-scoped only when the
    # deployment has ≤ 1 operator. With 2+ operator emails the bypass would be
    # cross-tenant (this helper keys on auth_method, not user_id), so it FAILS
    # CLOSED to the non-privileged tag.
    if auth_method in _OWNER_AUTH_METHODS and len(operator_allowlist_from_env()) <= 1:
        return _OWNER_READ_POLICY_TAG
    return _PUBLIC_READ_POLICY_TAG

# arXiv canonical-link prefix; the serve guard stamps result.canonical_url as
# ``https://arxiv.org/abs/<arxiv_id>`` for an arXiv doc (None otherwise), so the
# arxiv_id is recoverable from it for the M4 serve-audit without re-reading the DB.
_ARXIV_ABS_PREFIX = "https://arxiv.org/abs/"


def _resolve_db_path() -> str:
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def _record_arxiv_serve_audit(db_path: str, document_id: str, result: ServeResult) -> None:
    """SPR-09 M4 — record an ``arxiv.serve`` leg for an arXiv full-text serve.

    Defensively isolated: a failure here must NEVER break the serve, so the whole
    body is wrapped. Only an arXiv doc carries a ``canonical_url`` (the
    ``https://arxiv.org/abs/<id>`` link the guard stamps) — we derive the arxiv_id
    from it and skip non-arXiv books. §9.0: we record only the served/gated REASON
    + tier + servable flag, never the body. The audit takes its OWN write lock
    (the serve itself ran on a read connection)."""
    try:
        canonical = getattr(result, "canonical_url", None)
        if not canonical or not canonical.startswith(_ARXIV_ABS_PREFIX):
            return  # non-arXiv book — no arXiv audit leg
        arxiv_id = canonical[len(_ARXIV_ABS_PREFIX):]
        if not arxiv_id:
            return
        from runtime.db_lock import connect_write
        from substrate.audit.arxiv_audit import ARXIV_SERVE, record_event

        con = connect_write(db_path, purpose="arxiv_serve_audit")
        try:
            record_event(
                con,
                arxiv_id=arxiv_id,
                document_id=document_id,
                kind=ARXIV_SERVE,
                reason=result.reason,
                tier=result.tier,
                detail={
                    "servable": bool(result.servable),
                    "ad_eligible": bool(result.ad_eligible),
                    "served_body": result.full_text is not None,
                },
            )
        finally:
            con.close()
    except Exception:
        logger.exception(
            "arxiv_audit serve-leg failed for document_id=%s; serve unaffected",
            document_id,
        )


# ── Response shapes ─────────────────────────────────────────────────


class TocItemResponse(BaseModel):
    title: str
    page_index: int | None
    level: int


class BookSummary(BaseModel):
    document_id: str
    title: str | None
    author: str | None
    servability: str
    servable_full_text: bool
    page_count: int
    cover_uri: str | None
    ip_holder_id: str | None
    taken_down: bool

    @classmethod
    def from_asset(cls, a: BookAsset) -> BookSummary:
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
    provenance: str | None
    license_basis: str | None
    toc: list[TocItemResponse]

    @classmethod
    def from_asset(cls, a: BookAsset) -> BookDetail:
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
    title: str | None
    author: str | None
    score: float


class CurateResponse(BaseModel):
    prompt: str
    books: list[CuratedBookResponse]


class SpinResearchRequest(BaseModel):
    page_index: int = Field(ge=0)
    # The reader's selected text. For a gated book it is IGNORED server-
    # side and replaced by the bounded snippet — the seed can never carry
    # gated full text, even if the client sends it (defense in depth).
    passage_text: str | None = None
    # Residual (jm): closed research tier for investigation start event.
    research_tier: Literal["fast", "deep", "wrestle"] = "deep"


class SpinResearchResponse(BaseModel):
    investigation_id: str
    document_id: str
    page_index: int
    gated: bool
    servability: str
    seed_preview: str
    # Residual (jm): echo research_tier recorded on start.
    research_tier: Literal["fast", "deep", "wrestle"] = "deep"


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
    servability: str | None
    full_text: str | None
    snippet: str | None
    title: str | None
    author: str | None
    reason: str
    # Rights context (Read SPR-05) — the data the reader renders off the
    # backend response instead of a local flag. ``tier`` is the arXiv
    # RightsTier value ('T1'|'T2'|'T3') or None for a non-arXiv document;
    # ``ad_eligible`` is the ad-rail gate (T1-only for arXiv; == servable for
    # non-arXiv, preserving today's behaviour); ``canonical_url`` is the
    # arxiv.org/abs link or None; ``license`` is the license_uri or None.
    tier: str | None = None
    ad_eligible: bool = False
    canonical_url: str | None = None
    license: str | None = None
    chunks: list[ReaderChunkResponse] = Field(default_factory=list)


class ReaderChunkResponse(BaseModel):
    """A graph chunk the caller is already permitted to read.

    The manifest is absent for snippet-only and taken-down responses. Page
    ownership is exact only when the ingestion section is a ``Page N`` marker;
    unresolved chunks remain honest rather than being assigned heuristically.
    """

    chunk_id: str
    chunk_index: int
    page_index: int | None
    text: str


class BookChunkAnchorResponse(BaseModel):
    document_id: str
    chunk_id: str
    page_index: int | None
    page_resolved: bool
    reason: str


# ── SPR-08 M2 — talk-to-book (multi-turn, page-cited) ───────────────


class TalkTurn(BaseModel):
    """One prior conversation turn the client carries forward (the multi-turn
    thread lives in the reader's session state — the floating bookmark — NOT in
    substrate truth). ``question`` is user-sourced; ``answer`` the model's prior
    reply, kept distinct."""

    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)


class AskBookRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    # The recent tail of the running conversation (server bounds it again).
    history: list[TalkTurn] = Field(default_factory=list)
    # Residual (gy): closed ResearchTier includes wrestle (parity with dispatch gp).
    research_tier: Literal["fast", "deep", "wrestle"] = "deep"


class CitationResponse(BaseModel):
    chunk_id: str
    document_id: str
    # The 0-based reader page the cited chunk anchors to, or null when the
    # chunk's section_path did not resolve to a page marker (then
    # ``page_resolved`` is False and the surface shows an honest "page not
    # pinpointed" — never a fabricated page).
    page_index: int | None = None
    page_resolved: bool = False
    snippet: str


class AskBookResponse(BaseModel):
    answer: str
    citations: list[CitationResponse]
    # False when the book had no extractable text to ground on (scanned-image
    # PDF / fully-withheld) — the honest no-context state, never a hallucination.
    grounded: bool
    context_chunk_count: int


# ── SPR-08 M1 — corpus search (NET-NEW) ─────────────────────────────


class CorpusSearchHit(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str | None
    page_index: int | None = None
    page_resolved: bool = False
    snippet: str
    similarity: float


class CorpusSearchResponse(BaseModel):
    query: str
    hits: list[CorpusSearchHit]
    count: int


# ── SPR-08 M4 — meta-reading deliverable (PROPOSED boundary) ────────


class MetaReadingRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    length_unit: Literal["pages", "minutes"]
    length_amount: int = Field(ge=1)
    # Residual (gy): closed ResearchTier includes wrestle.
    research_tier: Literal["fast", "deep", "wrestle"] = "deep"
    # The owned-corpus scope. "hard" is the PROPOSED Research↔Read boundary
    # (owned servable docs, optionally an explicit pick); "soft" is the rollback
    # when operator sign-off is withheld (the whole owned readable corpus).
    # NEITHER reaches the open internet — meta-reading is internet-agnostic.
    corpus_scope: Literal["hard", "soft"] = "hard"
    # An explicit pick of owned document ids (intersected with the owned set
    # under "hard" scope). Omit to scope to the whole owned servable corpus.
    document_ids: list[str] | None = None


class MetaReadingResponse(BaseModel):
    asset_id: str
    report: str
    citations: list[CitationResponse]
    length_unit: Literal["pages", "minutes"]
    length_amount: int
    word_budget: int
    truncated: bool
    corpus_scope: Literal["hard", "soft"]
    corpus_document_ids: list[str]
    # True when the owned corpus had nothing to synthesize from (honest empty,
    # never a fabricated report).
    empty: bool
    context_chunk_count: int


# ── SPR-13 — personal document space (collect / categorize / file) ──


class PersonalAssetResponse(BaseModel):
    """One item in the personal space (a created deliverable or a saved read).
    Substrate-backed — reconstructed from the event log, NOT a new store."""

    asset_id: str
    kind: Literal["meta_reading", "saved_read", "canonical_research"]
    title: str
    prompt: str | None
    document_ids: list[str]
    emitted_at: str | None
    # The in-app route that re-opens the item (the meta-doc view / the reader).
    open_route: str


class PersonalSpaceResponse(BaseModel):
    assets: list[PersonalAssetResponse]
    count: int


class AssetCategoryResponse(BaseModel):
    # Stable, unique key the surface renders on — two clusters can share a
    # human label, so the id (not the label) is the safe list key.
    category_id: str
    label: str
    asset_ids: list[str]
    # "theme" when the label emerged from clustering; "recency" when the corpus
    # was below the stability bound and we fell back honestly (never a fake label).
    ordering: Literal["theme", "recency"]


class CategorizedSpaceResponse(BaseModel):
    categories: list[AssetCategoryResponse]
    ordering: Literal["theme", "recency"]
    # The asset-count below which categories don't stabilize → recency fallback.
    stability_bound: int


class ProjectMatchResponse(BaseModel):
    investigation_id: str
    question: str
    score: float


class FileSuggestionResponse(BaseModel):
    document_id: str
    # The candidate projects above the suggestion threshold (top match first;
    # >1 when the doc matches several — the surface names them, never auto-files).
    matches: list[ProjectMatchResponse]


class SavedMetaReadingResponse(BaseModel):
    """A previously-saved meta-reading asset, re-opened by id from the event log
    (Read SPR-13 M1 — the item opens back into the meta-doc view). The same
    shape MetaReadingResponse carries, minus the generation-only word_budget."""

    asset_id: str
    prompt: str
    report: str
    citations: list[CitationResponse]
    length_unit: Literal["pages", "minutes"]
    length_amount: int
    truncated: bool
    corpus_scope: Literal["hard", "soft"]
    corpus_document_ids: list[str]


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
        from substrate.books.page_anchor import page_index_from_section_path

        db = _resolve_db_path()
        con = connect_read(db)
        try:
            result = serve_full_text_guarded(con, document_id)
            chunk_rows = []
            if result.full_text is not None:
                chunk_rows = con.execute(
                    "SELECT chunk_id, chunk_index, section_path, text "
                    "FROM chunks WHERE document_id = ? ORDER BY chunk_index",
                    [document_id],
                ).fetchall()
        finally:
            con.close()
        if not result.found:
            raise HTTPException(status_code=404, detail="book_not_found")
        # SPR-09 M4 — record the SERVE leg into the arXiv fetch→serve→accrue
        # compliance trace. Hooked at the ENDPOINT (not inside serve_guard.py,
        # which a parallel builder owns), AFTER the guard returns. Only an arXiv
        # doc carries a canonical_url (https://arxiv.org/abs/<id>), from which we
        # derive the arxiv_id; non-arXiv books emit no audit row. §9.0: we record
        # the served/gated REASON + tier + servable flag only — NEVER the body.
        # Defensively isolated: a failure in the audit layer must never break the
        # serve (wrap + log), and the audit write takes its own write lock.
        _record_arxiv_serve_audit(db, document_id, result)
        return FullTextResponse(
            document_id=result.document_id,
            servable=result.servable,
            servability=result.servability.value if result.servability else None,
            full_text=result.full_text,
            snippet=result.snippet,
            title=result.title,
            author=result.author,
            reason=result.reason,
            tier=result.tier,
            ad_eligible=result.ad_eligible,
            canonical_url=result.canonical_url,
            license=result.license,
            chunks=[
                ReaderChunkResponse(
                    chunk_id=row[0],
                    chunk_index=int(row[1]),
                    page_index=page_index_from_section_path(row[2]),
                    text=row[3],
                )
                for row in chunk_rows
            ],
        )

    @app.get(
        "/books/{document_id}/chunk-anchors/{chunk_id}",
        response_model=BookChunkAnchorResponse,
        tags=["books"],
    )
    async def get_book_chunk_anchor(
        document_id: str,
        chunk_id: str,
    ) -> BookChunkAnchorResponse:
        from runtime.db_lock import connect_read
        from substrate.books.page_anchor import page_index_from_section_path

        db = _resolve_db_path()
        con = connect_read(db)
        try:
            served = serve_full_text_guarded(con, document_id)
            if not served.found:
                raise HTTPException(status_code=404, detail="book_not_found")
            if not served.servable or served.full_text is None:
                raise HTTPException(status_code=403, detail="book_body_not_servable")
            row = con.execute(
                "SELECT section_path FROM chunks "
                "WHERE chunk_id = ? AND document_id = ?",
                [chunk_id, document_id],
            ).fetchone()
        finally:
            con.close()
        if row is None:
            raise HTTPException(status_code=404, detail="chunk_not_in_book")
        page_index = page_index_from_section_path(row[0])
        return BookChunkAnchorResponse(
            document_id=document_id,
            chunk_id=chunk_id,
            page_index=page_index,
            page_resolved=page_index is not None,
            reason="page_resolved" if page_index is not None else "page_not_resolved",
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
        # Residual (jm): record closed research_tier on investigation start.
        event_id = emit_typed(
            investigation_id,
            InvestigationStartRequestedPayload(
                question=seed.seed_text,
                context=f"Spun from a book passage. Servability: {seed.servability}.",
                spawn_context=spawn_context,
                research_tier=req.research_tier,
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
            research_tier=req.research_tier,
        )

    # ── SPR-08 M2 — talk-to-book (multi-turn, page-cited, gate-safe) ──
    @app.post(
        "/books/{document_id}/ask",
        response_model=AskBookResponse,
        tags=["books"],
    )
    async def ask_book(
        document_id: str, req: AskBookRequest, request: Request,
    ) -> AskBookResponse:
        """Answer one talk-to-book turn, page-cited, over THIS book only.

        Retrieval is scoped to ``document_id`` through the §9.0 gate. For the
        AUTHENTICATED OWNER (resolved server-side from the auth middleware via
        ``_owner_read_policy_tag``) the gate runs on the PRIVILEGED
        ``operator_only`` tag, so the owner can talk to HIS OWN gated/personal
        book in full. For any non-owner / unauthenticated caller (which, when
        enforcement is on, is 401'd by the middleware before reaching here) the
        gate stays non-privileged, so a withheld book's body never reaches the
        model context or a citation. A book with no extractable text (or one the
        gate fully withholds) returns an honest ungrounded answer WITHOUT
        dispatching a model (no hallucination). The model is dispatched through
        the ONE Hermes-routed path (§16); 503 when no provider is keyed.
        """
        from runtime.db_lock import connect_read
        from substrate.books.book_qa import Turn, answer_book_question
        from substrate.dispatch.base import ProviderError
        from substrate.graph.search import SentenceTransformerEmbedding

        # Confirm the book exists (honest 404 rather than an empty answer).
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            asset = get_book_asset(con, document_id)
        finally:
            con.close()
        if asset is None:
            raise HTTPException(status_code=404, detail="book_not_found")

        try:
            model = SentenceTransformerEmbedding()
        except RuntimeError as exc:  # sentence-transformers not installed
            raise HTTPException(status_code=503, detail=f"embedding_unavailable: {exc}") from exc

        con = connect_read(db)
        try:
            try:
                result = answer_book_question(
                    con,
                    document_id=document_id,
                    question=req.question,
                    model=model,
                    investigation_id=f"read-{document_id}",
                    history=[Turn(question=t.question, answer=t.answer) for t in req.history],
                    research_tier=req.research_tier,
                    # §9.0: privileged ONLY for the authenticated owner (resolved
                    # server-side); non-owner / unauth callers stay gated.
                    policy_tag=_owner_read_policy_tag(request),
                )
            except ProviderError as exc:
                # No keyed provider — honest 503, never a fabricated answer.
                raise HTTPException(status_code=503, detail=f"dispatch_unavailable: {exc}") from exc
        finally:
            con.close()

        return AskBookResponse(
            answer=result.answer,
            citations=[
                CitationResponse(
                    chunk_id=c.chunk_id,
                    document_id=c.document_id,
                    page_index=c.page_index,
                    page_resolved=c.page_resolved,
                    snippet=c.snippet,
                )
                for c in result.citations
            ],
            grounded=result.grounded,
            context_chunk_count=result.context_chunk_count,
        )

    # ── SPR-08 M1 — corpus search over the owned graph (NET-NEW) ──
    @app.get(
        "/corpus/search",
        response_model=CorpusSearchResponse,
        tags=["books"],
    )
    async def corpus_search(
        request: Request,
        q: str,
        limit: int = 20,
        document_id: str | None = None,
    ) -> CorpusSearchResponse:
        """Search the owned corpus by a natural-language query. Wraps
        ``substrate.graph.search.search`` through the §9.0 gate. For the
        AUTHENTICATED OWNER (resolved server-side from the auth middleware via
        ``_owner_read_policy_tag``) the gate runs on the PRIVILEGED
        ``operator_only`` tag, so the owner can search across HIS OWN
        gated/personal corpus. For any non-owner / unauthenticated caller (401'd
        by the middleware before reaching here when enforcement is on) the gate
        stays non-privileged and excludes restricted/personal content.
        ``document_id`` optionally scopes to one document. The Library's typed
        query + file-drop bias both POST text here (file = a query SIGNAL, never
        ingested)."""
        from runtime.db_lock import connect_read
        from substrate.books.page_anchor import page_index_from_section_path
        from substrate.graph.search import SentenceTransformerEmbedding, search

        if not q.strip():
            return CorpusSearchResponse(query=q, hits=[], count=0)
        try:
            model = SentenceTransformerEmbedding()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=f"embedding_unavailable: {exc}") from exc

        db = _resolve_db_path()
        con = connect_read(db)
        try:
            res = search(
                con, q, model=model, top_k=max(1, limit), document_id=document_id,
                # §9.0: privileged ONLY for the authenticated owner (resolved
                # server-side); non-owner / unauth callers stay gated.
                policy_tag=_owner_read_policy_tag(request),
            )
        finally:
            con.close()

        hits: list[CorpusSearchHit] = []
        for r in res["results"]:
            page_index = page_index_from_section_path(r.get("section_path"))
            text = r.get("chunk_text", "") or ""
            hits.append(
                CorpusSearchHit(
                    chunk_id=r.get("chunk_id", ""),
                    document_id=r.get("document_id", ""),
                    document_title=r.get("document_title"),
                    page_index=page_index,
                    page_resolved=page_index is not None,
                    snippet=text[:240] + ("…" if len(text) > 240 else ""),
                    similarity=r.get("similarity", 0.0),
                )
            )
        return CorpusSearchResponse(query=q, hits=hits, count=len(hits))

    # ── SPR-08 M4 — meta-reading deliverable (PROPOSED, owned-corpus-only) ──
    @app.post(
        "/corpus/meta-reading",
        response_model=MetaReadingResponse,
        status_code=201,
        tags=["books"],
    )
    async def meta_reading(req: MetaReadingRequest) -> MetaReadingResponse:
        """Generate + SAVE a one-shot, READ-ONLY, page-cited synthesis over the
        OWNED corpus (Read SPR-08 M4). INTERNET-AGNOSTIC: retrieval is ONLY
        ``search`` over owned document ids — no acquisition / open-web call. The
        HARD length-box is built up front (a degenerate size → 422 with a stated
        bound). The deliverable is persisted as a re-openable Read asset through
        the single-writer typed-event funnel (NOT a new silo). PROPOSED boundary
        (sign-off pending) — reversible to a soft corpus scope.
        """
        import uuid as _uuid

        from runtime.db_lock import connect_read
        from substrate.books.meta_reading import MetaReadingError, generate_meta_reading
        from substrate.dispatch.base import ProviderError
        from substrate.event_log import emit_typed
        from substrate.graph.search import SentenceTransformerEmbedding
        from substrate.schemas.events import (
            MetaReadingCitation,
            ReadMetaReadingGeneratedPayload,
        )

        try:
            model = SentenceTransformerEmbedding()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=f"embedding_unavailable: {exc}") from exc

        asset_id = f"mr-{_uuid.uuid4().hex[:12]}"
        investigation_id = f"read-meta-{asset_id}"
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            try:
                deliverable = generate_meta_reading(
                    con,
                    prompt=req.prompt,
                    unit=req.length_unit,
                    amount=req.length_amount,
                    model=model,
                    investigation_id=investigation_id,
                    scope=req.corpus_scope,
                    document_ids=req.document_ids,
                    research_tier=req.research_tier,
                )
            except MetaReadingError as exc:
                # Degenerate length (0 / negative / above the cap) — stated bound.
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except ProviderError as exc:
                raise HTTPException(status_code=503, detail=f"dispatch_unavailable: {exc}") from exc
        finally:
            con.close()

        citations = [
            CitationResponse(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                page_index=c.page_index,
                page_resolved=c.page_resolved,
                snippet=c.snippet,
            )
            for c in deliverable.citations
        ]

        # Persist the deliverable as substrate truth (re-open / narrate /
        # promote). NOT a side-store — it rides the single-writer funnel. An
        # empty deliverable is NOT saved (nothing to re-open); honest empty.
        if not deliverable.empty:
            event_id = emit_typed(
                investigation_id,
                ReadMetaReadingGeneratedPayload(
                    asset_id=asset_id,
                    prompt=req.prompt,
                    report=deliverable.report,
                    length_unit=deliverable.length_box.unit,
                    length_amount=deliverable.length_box.amount,
                    truncated=deliverable.truncated,
                    corpus_scope=deliverable.corpus_scope,
                    corpus_document_ids=deliverable.corpus_document_ids,
                    citations=[
                        MetaReadingCitation(
                            chunk_id=c.chunk_id,
                            document_id=c.document_id,
                            page_index=c.page_index,
                            page_resolved=c.page_resolved,
                        )
                        for c in deliverable.citations
                    ],
                ),
                role="read/meta_reading",
                policy_id="read/meta_reading",
            )
            if event_id is None:
                raise HTTPException(
                    status_code=503,
                    detail="Event log is disabled (ANTIEK_EVENTS_DISABLED).",
                )

        return MetaReadingResponse(
            asset_id=asset_id,
            report=deliverable.report,
            citations=citations,
            length_unit=deliverable.length_box.unit,
            length_amount=deliverable.length_box.amount,
            word_budget=deliverable.length_box.word_budget,
            truncated=deliverable.truncated,
            corpus_scope=deliverable.corpus_scope,
            corpus_document_ids=deliverable.corpus_document_ids,
            empty=deliverable.empty,
            context_chunk_count=deliverable.context_chunk_count,
        )

    # ── SPR-13 — personal document space ────────────────────────────
    #
    # The reader's "personal bed of information that labels itself": their
    # CREATED deliverables (SPR-08 meta-readings) + saved reads (SPR-07
    # source.read history), reconstructed from the event log — NO new store.
    # Distinct from /books (the raw library of source books). These selectors
    # live in substrate/books/personal_space.py and reuse the SAME embedding
    # model SPR-04 curate + §7 search use (no new embedder).

    def _book_title_resolver(document_id: str) -> str | None:
        """Map a read document_id → its book title so a saved read shows the
        book's name, not its id. Best-effort: a non-book / missing doc resolves
        to None and the caller falls back to the id (honest, never fabricated)."""
        from runtime.db_lock import connect_read

        try:
            con = connect_read(_resolve_db_path())
            try:
                asset = get_book_asset(con, document_id)
            finally:
                con.close()
            return asset.title if asset else None
        except Exception:
            return None

    def _personal_space_assets():
        from runtime.db_lock import connect_read
        from substrate.books.personal_space import PersonalAsset, list_personal_assets
        from substrate.engagement_spine.canonical_commit import (
            CanonicalMergeConflict,
            load_latest_reviewed_document_model,
        )

        assets = list_personal_assets(book_title_resolver=_book_title_resolver)
        con = connect_read(_resolve_db_path())
        try:
            rows = con.execute(
                "SELECT deliverable_id, title, metadata, "
                "strftime(updated_at, '%Y-%m-%dT%H:%M:%S') "
                "FROM deliverables ORDER BY updated_at DESC"
            ).fetchall()
            known = {asset.asset_id for asset in assets}
            for deliverable_id, title, raw_metadata, updated_at in rows:
                try:
                    metadata = json.loads(str(raw_metadata or "{}"))
                except (TypeError, ValueError):
                    continue
                if not isinstance(metadata, dict) or deliverable_id in known:
                    continue
                try:
                    load_latest_reviewed_document_model(con, str(deliverable_id))
                except (KeyError, CanonicalMergeConflict):
                    continue
                source_id = str(metadata.get("source_document_id") or "").strip()
                assets.append(
                    PersonalAsset(
                        asset_id=str(deliverable_id),
                        kind="canonical_research",
                        title=str(title),
                        prompt=None,
                        document_ids=[source_id] if source_id else [],
                        emitted_at=str(updated_at) if updated_at else None,
                        open_route=(
                            f"/read/canonical/{quote(str(deliverable_id), safe='')}"
                        ),
                    )
                )
        finally:
            con.close()
        assets.sort(key=lambda asset: asset.emitted_at or "", reverse=True)
        return assets

    @app.get("/meta-readings", response_model=PersonalSpaceResponse, tags=["books"])
    async def list_personal_space() -> PersonalSpaceResponse:
        """List the personal-space assets — created deliverables + saved reads,
        newest first (Read SPR-13 M1). Substrate-backed (event-log scan), NOT a
        new document store. Each asset's ``open_route`` re-opens it into the
        SPR-08 meta-doc view / the SPR-07 reader."""
        assets = _personal_space_assets()
        return PersonalSpaceResponse(
            assets=[PersonalAssetResponse(**a.to_dict()) for a in assets],
            count=len(assets),
        )

    @app.get(
        "/meta-readings/categories",
        response_model=CategorizedSpaceResponse,
        tags=["books"],
    )
    async def personal_space_categories() -> CategorizedSpaceResponse:
        """Cluster the personal-space assets into SYSTEM-named categories (Read
        SPR-13 M2). The system names the categories from each cluster's salient
        terms; the user never hand-organizes folders. Deterministic on a fixed
        corpus; honest recency fallback below the stability bound (rigor #1).
        Reuses the SAME embedding model — NO new embedder; an unavailable model
        degrades to the recency fallback rather than failing the request."""
        from substrate.books.personal_space import (
            categorize_assets,
        )

        assets = _personal_space_assets()
        try:
            from substrate.graph.search import SentenceTransformerEmbedding

            model: object | None = SentenceTransformerEmbedding()
        except RuntimeError:
            model = None

        if model is None:
            # No embedder → the honest recency fallback (one bucket), never a
            # fabricated theme label. categorize_assets also self-falls-back
            # below the bound, but with no model we short-circuit here.
            from substrate.books.personal_space import (
                MIN_ASSETS_FOR_CLUSTERING,
                AssetCategory,
                CategorizedSpace,
            )

            space = CategorizedSpace(
                categories=[
                    AssetCategory(
                        category_id="recency",
                        label="Recently read & created",
                        asset_ids=[a.asset_id for a in assets],
                        ordering="recency",
                    )
                ]
                if assets
                else [],
                ordering="recency",
                stability_bound=MIN_ASSETS_FOR_CLUSTERING,
            )
        else:
            space = categorize_assets(assets, model=model)  # type: ignore[arg-type]

        return CategorizedSpaceResponse(
            categories=[
                AssetCategoryResponse(
                    category_id=c.category_id,
                    label=c.label,
                    asset_ids=c.asset_ids,
                    ordering=cast(Literal["theme", "recency"], c.ordering),
                )
                for c in space.categories
            ],
            ordering=cast(Literal["theme", "recency"], space.ordering),
            stability_bound=space.stability_bound,
        )

    @app.get(
        "/meta-readings/file-suggestion",
        response_model=FileSuggestionResponse,
        tags=["books"],
    )
    async def file_suggestion(document_id: str) -> FileSuggestionResponse:
        """Suggest research projects a personal-space document could be filed
        into (Read SPR-13 M3). Ranks candidate projects by the doc's semantic
        similarity to each project's question; returns matches above the
        justified threshold, best first (top match, or >1 on a tie — never
        auto-files). SUGGEST-ONLY: this endpoint ranks; filing is the separate
        explicit-accept ``document.filed_into_investigation`` event.

        The doc's match text is its title + its prompt (for a meta-reading) /
        title (for a saved read), reconstructed from the personal-space list —
        the reader's OWN deliverable text, not a withheld source body (§9.0)."""
        from substrate.books.personal_space import (
            list_personal_assets,
            match_document_to_investigations,
        )

        try:
            from substrate.graph.search import SentenceTransformerEmbedding

            model = SentenceTransformerEmbedding()
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503, detail=f"embedding_unavailable: {exc}"
            ) from exc

        # Build the doc's match text from the personal-space asset (its own
        # deliverable text). If the id isn't a personal asset we fall back to
        # the raw document_id as the match text (still no source body).
        assets = list_personal_assets(book_title_resolver=_book_title_resolver)
        asset = next(
            (a for a in assets if document_id in (a.asset_id, *a.document_ids)),
            None,
        )
        if asset is not None:
            doc_text = " ".join(p for p in (asset.prompt, asset.title) if p)
        else:
            doc_text = document_id

        matches = match_document_to_investigations(doc_text=doc_text, model=model)
        return FileSuggestionResponse(
            document_id=document_id,
            matches=[
                ProjectMatchResponse(
                    investigation_id=m.investigation_id,
                    question=m.question,
                    score=m.score,
                )
                for m in matches
            ],
        )

    # Registered AFTER the static /meta-readings/{categories,file-suggestion}
    # routes so neither is captured as an asset_id (FastAPI matches in
    # registration order; static segments declared first win).
    @app.get(
        "/meta-readings/{asset_id}",
        response_model=SavedMetaReadingResponse,
        tags=["books"],
    )
    async def get_saved_meta_reading(asset_id: str) -> SavedMetaReadingResponse:
        """Re-open a saved meta-reading asset by id (Read SPR-13 M1). Reads the
        ``read.meta_reading.generated`` event off the log (the asset rides
        ``read-meta-{asset_id}``) — the substrate's source of truth, NOT a new
        store. The saved citations carry references (chunk/document/page), never
        a body; the generation-time snippet preview was not persisted, so it is
        an honest empty string on re-open (the page link still resolves)."""
        from substrate.event_log.events import trajectory

        investigation_id = f"read-meta-{asset_id}"
        rows = trajectory(investigation_id)
        payload = next(
            (
                (r.get("payload") or {})
                for r in rows
                if r.get("action_type") == "read.meta_reading.generated"
                and (r.get("payload") or {}).get("asset_id") == asset_id
            ),
            None,
        )
        if payload is None:
            raise HTTPException(
                status_code=404, detail=f"meta-reading asset {asset_id!r} not found."
            )
        return SavedMetaReadingResponse(
            asset_id=asset_id,
            prompt=payload.get("prompt", ""),
            report=payload.get("report", ""),
            citations=[
                CitationResponse(
                    chunk_id=c.get("chunk_id", ""),
                    document_id=c.get("document_id", ""),
                    page_index=c.get("page_index"),
                    page_resolved=bool(c.get("page_resolved", False)),
                    snippet="",
                )
                for c in (payload.get("citations") or [])
            ],
            length_unit=payload.get("length_unit", "pages"),
            length_amount=int(payload.get("length_amount", 1)),
            truncated=bool(payload.get("truncated", False)),
            corpus_scope=payload.get("corpus_scope", "hard"),
            corpus_document_ids=list(payload.get("corpus_document_ids") or []),
        )
