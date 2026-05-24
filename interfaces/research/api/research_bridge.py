"""FastAPI router for the Deep Research Bridge.

Mounted by ``interfaces/research/api/app.py`` via
``register_research_bridge_routes``.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from runtime.db_lock import connect_write
from substrate.research_bridge import (
    EXTRACTOR_VERSION,
    KNOWN_SOURCES,
    PASTE_DOCUMENT_TYPE,
    ExtractorError,
    GapFinderError,
    PasteEmptyError,
    PasteTooLargeError,
    detect_source,
    ensure_research_bridge_initialized,
    extract_paste,
    find_gaps,
    ingest_paste,
    list_gap_runs,
    list_insights,
    list_open_questions,
    list_paste_events,
    read_gap_run,
    record_prompt_answer,
    record_prompt_signal,
    would_run_percentage,
)
from substrate.research_bridge.llm_dispatch import build_dispatch_llm_callable


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class DetectRequest(BaseModel):
    raw_text: str = Field(..., min_length=1)


class DetectResponse(BaseModel):
    source: str
    confidence: float
    parser_version: int
    per_source: dict[str, float]


class PasteRequest(BaseModel):
    raw_text: str = Field(..., min_length=1)
    operator_label: Optional[str] = Field(default=None, max_length=200)
    session_id: Optional[str] = Field(default=None, max_length=64)
    source_override: Optional[str] = None
    source_tier: int = Field(default=4, ge=1, le=5)
    investigation_id: Optional[str] = None


class PasteResponse(BaseModel):
    document_id: str
    source: str
    source_confidence: float
    raw_sha256: str
    paste_byte_length: int
    parser_version: int
    chunk_count: int
    per_source_scores: dict[str, float]


class PasteSummary(BaseModel):
    document_id: str
    source: str
    source_confidence: float
    paste_byte_length: int
    operator_label: Optional[str]
    session_id: Optional[str]
    pasted_at: str
    title: Optional[str]


class ListPastesResponse(BaseModel):
    count: int
    pastes: list[PasteSummary]


class PasteEventSummary(BaseModel):
    event_id: str
    occurred_at: str
    paste_byte_length: int
    source: str
    call_site: str


class PasteDetailResponse(BaseModel):
    document_id: str
    source: str
    source_confidence: float
    raw_sha256: str
    paste_byte_length: int
    parser_version: int
    operator_label: Optional[str]
    session_id: Optional[str]
    pasted_at: str
    title: Optional[str]
    chunk_count: int
    raw_text: str
    events: list[PasteEventSummary]


class RawTextResponse(BaseModel):
    document_id: str
    raw_text: str
    raw_sha256: str
    paste_byte_length: int


class ExtractRequest(BaseModel):
    regenerate: bool = False


class ExtractedItemPayload(BaseModel):
    summary: str
    quote: str
    quote_start_offset: int
    quote_end_offset: int
    llm_confidence: float


class ExtractResponse(BaseModel):
    extraction_id: str
    document_id: str
    extractor_version: int
    model_id: str
    status: str
    insights: list[ExtractedItemPayload]
    open_questions: list[ExtractedItemPayload]
    quote_drops: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class StoredItemPayload(BaseModel):
    item_id: str
    summary: str
    quote: str
    quote_start_offset: int
    quote_end_offset: int
    llm_confidence: float
    extractor_version: int
    model_id: str


class ListItemsResponse(BaseModel):
    document_id: str
    insights: list[StoredItemPayload]
    open_questions: list[StoredItemPayload]


class FindGapsRequest(BaseModel):
    scope_block_ids: list[str] = Field(..., min_length=1)
    operator_label: Optional[str] = Field(default=None, max_length=200)
    session_id: Optional[str] = Field(default=None, max_length=64)


class GapClusterPayload(BaseModel):
    cluster_id: str
    label: str
    priority_rank: int
    rationale: Optional[str]


class GapPromptPayload(BaseModel):
    prompt_id: str
    cluster_id: Optional[str]
    order_index: int
    prompt_text: str
    target_provider: str
    expected_output_shape: Optional[str]
    depends_on_prior_order_index: Optional[int]
    rationale: Optional[str]
    input_tokens: int
    output_tokens: int
    cost_usd: float


class GapRunPayload(BaseModel):
    run_id: str
    operator_label: Optional[str]
    session_id: Optional[str]
    scope_block_ids: list[str]
    scope_question_ids: list[str]
    cluster_model_id: str
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float
    created_at: str


class FindGapsResponse(BaseModel):
    run: GapRunPayload
    clusters: list[GapClusterPayload]
    prompts: list[GapPromptPayload]
    grounding_drops: int


class ListGapRunsResponse(BaseModel):
    count: int
    runs: list[GapRunPayload]


class SignalRequest(BaseModel):
    signal_type: str


class SignalResponse(BaseModel):
    signal_id: str


class AnswerRequest(BaseModel):
    answer_document_id: str = Field(..., min_length=1)


class AnswerResponse(BaseModel):
    answer_id: str


class WouldRunPercentageResponse(BaseModel):
    would_run_count: int
    total_signalled: int
    percentage: float
    run_id: Optional[str]


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


router = APIRouter(prefix="/research", tags=["research_bridge"])


def _open_read(db_path: str):
    import duckdb
    return duckdb.connect(db_path, read_only=True)


@router.post("/detect", response_model=DetectResponse)
def post_detect(req: DetectRequest) -> DetectResponse:
    """Run source detection WITHOUT writing. Powers the paste page's
    live-preview affordance: the operator sees the detected provider
    (and the per-source scores when it's ambiguous) before committing
    the paste. Mirrors the CLI ``detect`` subcommand over HTTP."""
    result = detect_source(req.raw_text)
    return DetectResponse(
        source=result.source,
        confidence=result.confidence,
        parser_version=result.parser_version,
        per_source=dict(result.per_source),
    )


@router.post("/pastes", response_model=PasteResponse, status_code=201)
def post_paste(req: PasteRequest) -> PasteResponse:
    if req.source_override is not None and req.source_override not in KNOWN_SOURCES:
        raise HTTPException(
            status_code=422,
            detail=f"source_override={req.source_override!r} is not in KNOWN_SOURCES={list(KNOWN_SOURCES)}",
        )
    db = ensure_research_bridge_initialized()
    try:
        with connect_write(db, purpose="research_bridge/paste") as con:
            result = ingest_paste(
                con,
                raw_text=req.raw_text,
                operator_label=req.operator_label,
                session_id=req.session_id,
                source_override=req.source_override,
                source_tier=req.source_tier,
                investigation_id=req.investigation_id,
                call_site="http_api",
            )
    except PasteTooLargeError as e:
        raise HTTPException(status_code=413, detail=str(e))
    except PasteEmptyError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return PasteResponse(
        document_id=result.document_id,
        source=result.source,
        source_confidence=result.source_confidence,
        raw_sha256=result.raw_sha256,
        paste_byte_length=result.paste_byte_length,
        parser_version=result.parser_version,
        chunk_count=len(result.chunk_ids),
        per_source_scores=dict(result.detection.per_source),
    )


@router.get("/pastes", response_model=ListPastesResponse)
def list_pastes(
    limit: int = Query(default=50, ge=1, le=500),
    source: Optional[str] = Query(default=None),
    session_id: Optional[str] = Query(default=None),
) -> ListPastesResponse:
    if source is not None and source not in KNOWN_SOURCES:
        raise HTTPException(
            status_code=422,
            detail=f"source={source!r} is not in KNOWN_SOURCES={list(KNOWN_SOURCES)}",
        )
    db = ensure_research_bridge_initialized()
    con = _open_read(db)
    try:
        where = []
        params: list[Any] = []
        if source is not None:
            where.append("rp.source = ?")
            params.append(source)
        if session_id is not None:
            where.append("rp.session_id = ?")
            params.append(session_id)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        params.append(int(limit))
        rows = con.execute(
            f"""
            SELECT rp.document_id, rp.source, rp.source_confidence,
                   rp.paste_byte_length, rp.operator_label, rp.session_id,
                   rp.pasted_at, d.title
            FROM research_pastes rp
            JOIN documents d ON d.document_id = rp.document_id
            {where_sql}
            ORDER BY rp.pasted_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    finally:
        con.close()
    summaries = [
        PasteSummary(
            document_id=r[0], source=r[1], source_confidence=float(r[2]),
            paste_byte_length=int(r[3]), operator_label=r[4],
            session_id=r[5], pasted_at=str(r[6]), title=r[7],
        )
        for r in rows
    ]
    return ListPastesResponse(count=len(summaries), pastes=summaries)


@router.get("/pastes/{document_id}", response_model=PasteDetailResponse)
def get_paste(document_id: str) -> PasteDetailResponse:
    db = ensure_research_bridge_initialized()
    con = _open_read(db)
    try:
        row = con.execute(
            """
            SELECT rp.document_id, rp.source, rp.source_confidence,
                   rp.raw_sha256, rp.paste_byte_length, rp.parser_version,
                   rp.operator_label, rp.session_id, rp.pasted_at,
                   d.title, d.raw_text,
                   (SELECT COUNT(*) FROM chunks c WHERE c.document_id = rp.document_id)
            FROM research_pastes rp
            JOIN documents d ON d.document_id = rp.document_id
            WHERE rp.document_id = ?
            """,
            [document_id],
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"paste {document_id} not found")
        events = list_paste_events(con, document_id=document_id, limit=50)
    finally:
        con.close()
    return PasteDetailResponse(
        document_id=row[0], source=row[1], source_confidence=float(row[2]),
        raw_sha256=row[3], paste_byte_length=int(row[4]),
        parser_version=int(row[5]), operator_label=row[6], session_id=row[7],
        pasted_at=str(row[8]), title=row[9], chunk_count=int(row[11] or 0),
        raw_text=row[10] or "",
        events=[
            PasteEventSummary(
                event_id=e.event_id, occurred_at=str(e.occurred_at),
                paste_byte_length=e.paste_byte_length,
                source=e.source, call_site=e.call_site,
            )
            for e in events
        ],
    )


@router.get("/pastes/{document_id}/raw", response_model=RawTextResponse)
def get_paste_raw(document_id: str) -> RawTextResponse:
    db = ensure_research_bridge_initialized()
    con = _open_read(db)
    try:
        row = con.execute(
            """
            SELECT rp.document_id, d.raw_text, rp.raw_sha256, rp.paste_byte_length
            FROM research_pastes rp
            JOIN documents d ON d.document_id = rp.document_id
            WHERE rp.document_id = ?
            """,
            [document_id],
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"paste {document_id} not found")
    finally:
        con.close()
    return RawTextResponse(
        document_id=row[0], raw_text=row[1] or "",
        raw_sha256=row[2], paste_byte_length=int(row[3]),
    )


@router.post(
    "/pastes/{document_id}/extract",
    response_model=ExtractResponse,
    status_code=200,
)
def post_extract(
    document_id: str, req: Optional[ExtractRequest] = None,
) -> ExtractResponse:
    req = req or ExtractRequest()
    db = ensure_research_bridge_initialized()
    llm = build_dispatch_llm_callable()
    try:
        with connect_write(db, purpose="research_bridge/extract") as con:
            r = extract_paste(con, document_id, llm_callable=llm, regenerate=req.regenerate)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ExtractorError as e:
        raise HTTPException(status_code=502, detail=str(e))

    def _p(item) -> ExtractedItemPayload:
        return ExtractedItemPayload(
            summary=item.summary, quote=item.quote,
            quote_start_offset=item.quote_start_offset,
            quote_end_offset=item.quote_end_offset,
            llm_confidence=item.llm_confidence,
        )

    return ExtractResponse(
        extraction_id=r.extraction_id, document_id=r.document_id,
        extractor_version=r.extractor_version, model_id=r.model_id,
        status=r.status,
        insights=[_p(i) for i in r.insights],
        open_questions=[_p(q) for q in r.open_questions],
        quote_drops=r.quote_drops,
        input_tokens=r.input_tokens, output_tokens=r.output_tokens,
        cost_usd=r.cost_usd,
    )


@router.get("/pastes/{document_id}/items", response_model=ListItemsResponse)
def get_items(
    document_id: str,
    version: Optional[int] = Query(default=None),
) -> ListItemsResponse:
    db = ensure_research_bridge_initialized()
    con = _open_read(db)
    try:
        ins = list_insights(con, document_id=document_id, version=version)
        q = list_open_questions(con, document_id=document_id, version=version)
    finally:
        con.close()
    return ListItemsResponse(
        document_id=document_id,
        insights=[
            StoredItemPayload(
                item_id=i.item_id, summary=i.summary, quote=i.quote,
                quote_start_offset=i.quote_start_offset,
                quote_end_offset=i.quote_end_offset,
                llm_confidence=i.llm_confidence,
                extractor_version=i.extractor_version, model_id=i.model_id,
            )
            for i in ins
        ],
        open_questions=[
            StoredItemPayload(
                item_id=i.item_id, summary=i.summary, quote=i.quote,
                quote_start_offset=i.quote_start_offset,
                quote_end_offset=i.quote_end_offset,
                llm_confidence=i.llm_confidence,
                extractor_version=i.extractor_version, model_id=i.model_id,
            )
            for i in q
        ],
    )


def _run_to_payload(run, clusters, prompts) -> FindGapsResponse:
    return FindGapsResponse(
        run=GapRunPayload(
            run_id=run.run_id, operator_label=run.operator_label,
            session_id=run.session_id,
            scope_block_ids=list(run.scope_block_ids),
            scope_question_ids=list(run.scope_question_ids),
            cluster_model_id=run.cluster_model_id,
            total_input_tokens=run.total_input_tokens,
            total_output_tokens=run.total_output_tokens,
            total_cost_usd=run.total_cost_usd,
            created_at=run.created_at,
        ),
        clusters=[
            GapClusterPayload(
                cluster_id=c.cluster_id, label=c.label,
                priority_rank=c.priority_rank, rationale=c.rationale,
            )
            for c in clusters
        ],
        prompts=[
            GapPromptPayload(
                prompt_id=p.prompt_id, cluster_id=p.cluster_id,
                order_index=p.order_index, prompt_text=p.prompt_text,
                target_provider=p.target_provider,
                expected_output_shape=p.expected_output_shape,
                depends_on_prior_order_index=p.depends_on_prior_order_index,
                rationale=p.rationale,
                input_tokens=p.input_tokens, output_tokens=p.output_tokens,
                cost_usd=p.cost_usd,
            )
            for p in prompts
        ],
        grounding_drops=0,
    )


@router.post("/gaps", response_model=FindGapsResponse, status_code=201)
def post_find_gaps(req: FindGapsRequest) -> FindGapsResponse:
    db = ensure_research_bridge_initialized()
    llm = build_dispatch_llm_callable()
    try:
        with connect_write(db, purpose="research_bridge/find_gaps") as con:
            r = find_gaps(
                con,
                scope_block_ids=req.scope_block_ids,
                llm_callable=llm,
                operator_label=req.operator_label,
                session_id=req.session_id,
            )
            run, clusters, prompts = read_gap_run(con, r.run_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except GapFinderError as e:
        raise HTTPException(status_code=502, detail=str(e))
    if run is None:
        raise HTTPException(status_code=500, detail="run row vanished after write")
    payload = _run_to_payload(run, clusters, prompts)
    return FindGapsResponse(
        run=payload.run, clusters=payload.clusters, prompts=payload.prompts,
        grounding_drops=r.grounding_drops,
    )


@router.get("/gaps", response_model=ListGapRunsResponse)
def get_gap_runs(
    limit: int = Query(default=20, ge=1, le=200),
    session_id: Optional[str] = Query(default=None),
) -> ListGapRunsResponse:
    db = ensure_research_bridge_initialized()
    con = _open_read(db)
    try:
        runs = list_gap_runs(con, limit=limit, session_id=session_id)
    finally:
        con.close()
    return ListGapRunsResponse(
        count=len(runs),
        runs=[
            GapRunPayload(
                run_id=r.run_id, operator_label=r.operator_label,
                session_id=r.session_id,
                scope_block_ids=list(r.scope_block_ids),
                scope_question_ids=list(r.scope_question_ids),
                cluster_model_id=r.cluster_model_id,
                total_input_tokens=r.total_input_tokens,
                total_output_tokens=r.total_output_tokens,
                total_cost_usd=r.total_cost_usd,
                created_at=r.created_at,
            )
            for r in runs
        ],
    )


@router.get("/gaps/{run_id}", response_model=FindGapsResponse)
def get_gap_run(run_id: str) -> FindGapsResponse:
    db = ensure_research_bridge_initialized()
    con = _open_read(db)
    try:
        run, clusters, prompts = read_gap_run(con, run_id)
    finally:
        con.close()
    if run is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return _run_to_payload(run, clusters, prompts)


@router.post(
    "/gaps/prompts/{prompt_id}/signal",
    response_model=SignalResponse, status_code=201,
)
def post_signal(prompt_id: str, req: SignalRequest) -> SignalResponse:
    db = ensure_research_bridge_initialized()
    try:
        with connect_write(db, purpose="research_bridge/signal") as con:
            sid = record_prompt_signal(
                con, prompt_id=prompt_id, signal_type=req.signal_type,
            )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return SignalResponse(signal_id=sid)


@router.post(
    "/gaps/prompts/{prompt_id}/answer",
    response_model=AnswerResponse, status_code=201,
)
def post_answer(prompt_id: str, req: AnswerRequest) -> AnswerResponse:
    db = ensure_research_bridge_initialized()
    with connect_write(db, purpose="research_bridge/answer") as con:
        aid = record_prompt_answer(
            con, prompt_id=prompt_id, answer_document_id=req.answer_document_id,
        )
    return AnswerResponse(answer_id=aid)


@router.get("/gaps/signals/percentage", response_model=WouldRunPercentageResponse)
def get_would_run_percentage(
    run_id: Optional[str] = Query(default=None),
) -> WouldRunPercentageResponse:
    db = ensure_research_bridge_initialized()
    con = _open_read(db)
    try:
        would, total, pct = would_run_percentage(con, run_id=run_id)
    finally:
        con.close()
    return WouldRunPercentageResponse(
        would_run_count=would, total_signalled=total,
        percentage=pct, run_id=run_id,
    )


def register_research_bridge_routes(app) -> None:
    app.include_router(router)


__all__ = ["router", "register_research_bridge_routes"]
