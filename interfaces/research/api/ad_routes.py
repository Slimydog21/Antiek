"""Ad-border HTTP surface (Read SPR-09 M2 + M3).

Two thin adapters over the EXISTING SPR-05 ad-economics substrate. Neither
re-implements weighting, accrual, or fill — they compose the substrate
functions and adapt them to HTTP.

* ``POST /api/ad/frame-telemetry`` receives the per-window ``WindowFrameBatch``
  the SPR-07 frontend emitter flushes, and hands it to the SPR-05 accrual engine
  (``frame_attention_accrual.accrue_window`` → per-second ``weigh_second`` →
  the ONE sanctioned escrow seam ``ip_holders.accrue_escrow`` + house seconds).
  The route's only added responsibilities are (a) version-gating the wire shape
  (v2 and v3 accepted; the client-priced v1 stays rejected),
  (b) deserializing into the frozen dataclasses (their ``__post_init__`` ranges
  validate the payload → 422), (c) resolving the AUTHORITATIVE per-asset
  ``content_class`` + ``ip_holder_id`` server-side (the client hint is NEVER
  trusted — the module contract requires the backend to resolve it),
  (d) MINTING the window's ad value server-side by joining the server's OWN
  fill/pricing record (``ad_fill_decisions``) on (owner_user_id, window_id) —
  the client-supplied ``ad_value_usd_cents`` is accepted only as an IGNORED
  HINT, logged as ``client_hint`` (``frame_telemetry_client_hints``) for
  auditability, never consulted, (e) classifying the batch via
  ``substrate.anti_gaming.frame_ivt`` and
  reporting the honest filtered-seconds/verdict/cap outcome in the response
  (AFA-S2, the anti-gaming pre-accrual filter), and (f) persisting through the
  single-writer lock.

* ``GET /api/ad/fill`` wraps ``reader_slots.fill_slot``: a matched advertiser
  creative if any, else the real ``HousePromo`` house fill (never blank).

§9.0: no gated body text crosses either surface. The telemetry route reads only
``content_class`` / ``ip_holder_id`` (the gate columns) per asset — never
``raw_text``. The fill route surfaces only display title/author for a house
promo and the advertiser's own creative metadata. Accrual ≠ disbursement:
``disbursable`` stays False (G2/G3 untouched); ``payout.py`` / ``stripe_connect``
are not imported here.
"""

from __future__ import annotations

from typing import Literal, cast

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from runtime.db_lock import LockedConnection, ReadConnection
from substrate.ad_inventory.frame_attention import (
    FRAME_TELEMETRY_SCHEMA_VERSION,
    SUPPORTED_FRAME_TELEMETRY_SCHEMA_VERSIONS,
)
from substrate.anti_gaming.frame_ivt import (
    DEFAULT_DAILY_ASSET_DWELL_CAP_MS,
    classify_batch,
)

from .books import _resolve_db_path

# ── Wire shapes (pydantic mirrors of the frozen dataclass contract) ──
#
# The canonical contract is the frozen dataclasses in
# ``substrate/ad_inventory/frame_attention.py`` (their ``__post_init__`` is the
# range authority). These pydantic models are the HTTP-deserialization mirror;
# the route reconstructs the dataclasses from them so the dataclass validation
# (and thus the ONE source of truth for ranges) runs on every request.


class FrameAttentionSampleIn(BaseModel):
    asset_id: str
    viewport_area_fraction: float
    prominence: float
    focused_dwell_ms: int
    # The client MAY echo a content_class hint, but the backend NEVER trusts it
    # (the authoritative value is resolved server-side from the documents gate
    # columns). Accepted for wire-compatibility; overwritten on resolution.
    content_class: str | None = None
    chunk_id: str | None = None


class FrameSecondIn(BaseModel):
    second_index: int
    lens: str
    samples: list[FrameAttentionSampleIn] = Field(default_factory=list)


class WindowFrameBatchIn(BaseModel):
    window_id: str
    seconds: list[FrameSecondIn] = Field(default_factory=list)
    # NOTE (ad-pipeline gap S1, frame-telemetry-v3): ``ad_value_usd_cents`` is
    # RE-ACCEPTED on the inbound shape as an OPTIONAL IGNORED HINT — the field
    # a legacy emitter still sends. It is NEVER trusted: the SERVER prices the
    # window (``resolve_window_value_cents`` joins the server's OWN
    # fill/pricing record — ``ad_fill_decisions`` — on (owner_user_id,
    # window_id)), and the hint is only logged to
    # ``frame_telemetry_client_hints`` (``client_hint``) for auditability. It
    # can never influence the accrued value. The red-proof is
    # ``test_ad_routes.py::test_frame_telemetry_ignores_client_supplied_value``.
    ad_value_usd_cents: int | None = Field(default=None, ge=0)
    schema_version: str = FRAME_TELEMETRY_SCHEMA_VERSION


class FrameTelemetryResponse(BaseModel):
    """The reconciled outcome of accruing one window batch. Carries no body —
    only the trace anchor + the conserved cents split (per the M6 invariant
    Σ contributor + house == total) + the AFA-S2 anti-gaming audit fields.

    Anti-gaming fields (the pre-accrual filter's honest report — every dropped
    second is counted, never silently removed):

    * ``fraud_verdict`` — the frame_ivt window verdict ("pass"/"review"/"block").
    * ``filtered_seconds`` — seconds withheld from allocation: the per-second
      GIVT/SIVT exclusions for a "pass" window; ALL of the window's seconds for
      a "review"/"block" window (held/zeroed — never allocated).
    * ``filtered_second_counts`` — per-reason invalid-second counts (the
      classifier's ``counts_by_reason``, exactly as persisted).
    * ``verdict_signals`` — the window verdict's signal name → detail (why the
      window was held/blocked; a SIVT heuristic's name lives here).
    * ``clamped_dwell_ms`` / ``clamped_cents`` — the per-identity saturation
      cap's reported exclusions for this window (0 when no cap is defined)."""

    batch_ref: str
    window_id: str
    total_ad_value_cents: int
    contributor_cents: int
    house_cents: int
    asset_count: int
    reconciles: bool
    telemetry_version: str
    weighting_version: str
    fraud_verdict: Literal["pass", "review", "block"]
    filtered_seconds: int
    filtered_second_counts: dict[str, int]
    verdict_signals: dict[str, str]
    clamped_dwell_ms: int
    clamped_cents: int


class HousePromoResponse(BaseModel):
    promoted_document_id: str
    title: str | None
    author: str | None


class AdCreativeResponse(BaseModel):
    """The advertiser's own creative metadata — never gated book text."""

    inventory_id: str
    advertiser_display_name: str
    creative_url: str
    landing_url: str


class AdFillResponse(BaseModel):
    slot_id: str
    document_id: str
    page_index: int
    position: str
    kind: Literal["ad", "house"]
    revenue_usd_cents: int
    ad: AdCreativeResponse | None = None
    house: HousePromoResponse | None = None


class EdgeFillResponse(BaseModel):
    fill_decision_id: str
    slot_id: str
    position: str
    kind: Literal["ad", "house"]
    revenue_usd_cents: int
    ad: AdCreativeResponse | None = None
    house: HousePromoResponse | None = None
    price_status: Literal["unpriced", "settled"]


class MultiEdgeFillRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_id: str = Field(min_length=1, max_length=256)
    lens: Literal["read", "research", "write", "speak"]
    positions: list[Literal["top", "bottom", "left", "right"]] = Field(
        min_length=1, max_length=4
    )
    document_id: str | None = Field(default=None, max_length=256)
    page_index: int | None = Field(default=None, ge=0)


class MultiEdgeFillResponse(BaseModel):
    window_id: str
    fills: list[EdgeFillResponse]


def _resolve_asset_gate(
    con: ReadConnection, asset_ids: set[str]
) -> dict[str, tuple[str | None, str | None]]:
    """Resolve each asset's AUTHORITATIVE (content_class, ip_holder_id) from the
    documents gate columns — server-side, never from the client hint. An asset
    with no documents row resolves to (None, None): NULL content_class is
    treated as ineligible by ``monetization_eligible`` (deny-by-default), so an
    unknown asset earns nothing rather than leaking earnings. Reads only the
    two gate columns — never ``raw_text`` (§9.0)."""
    if not asset_ids:
        return {}
    placeholders = ",".join("?" for _ in asset_ids)
    rows = con.execute(
        f"SELECT document_id, content_class, ip_holder_id FROM documents "
        f"WHERE document_id IN ({placeholders})",
        sorted(asset_ids),
    ).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


def resolve_window_value_cents(
    *,
    owner_user_id: str,
    window_id: str,
    con: ReadConnection | LockedConnection | None = None,
) -> int:
    """Mint the window's ad value SERVER-SIDE (ad-pipeline gap S1,
    frame-telemetry-v3).

    This is the trust seam that replaces the client-supplied
    ``ad_value_usd_cents`` (which is now accepted only as an IGNORED HINT and
    logged as ``client_hint``). The server joins ITS OWN fill/pricing record —
    ``ad_fill_decisions``, the durable snapshot ``POST /api/ad/fills`` persists
    at fill time (``fill_decisions.decide_fills``) — on
    ``(owner_user_id, window_id)`` and returns the record's revenue ONLY when
    ``price_status = 'settled'``. A missing fill record, or an ``unpriced`` one
    (CPM is a ranking signal, not settlement evidence — the fill ledger itself
    refuses to price), mints 0: the window accrues house/zero honestly, and the
    server NEVER fabricates a price. It NEVER reads anything the client sent.

    ``con`` is the connection to join on. The route passes its single-writer
    connection so the join happens under the write lock (the same lock under
    which fill decisions are persisted — no torn ordering). When ``con`` is
    None the resolver opens its own read connection via the DB path resolver;
    a missing ``ad_fill_decisions`` table is treated as "no fill record
    exists" → 0.

    SPR-10 (the auction / a billing authority) settles a decision's price by
    writing ``revenue_usd_cents`` + ``price_status='settled'`` on the existing
    fill record; that settled row then feeds real value here WITHOUT any client
    change. Keeping the seam here (module scope, not nested) makes it
    unit-testable and monkeypatchable: accrual-math tests inject a nonzero
    value; the production default is the fill-ledger join.
    """
    if con is None:
        from runtime.db_lock import connect_read

        con = connect_read(_resolve_db_path())
        try:
            return _resolve_from_fill_record(con, owner_user_id, window_id)
        finally:
            con.close()
    return _resolve_from_fill_record(con, owner_user_id, window_id)


def _resolve_from_fill_record(
    con: ReadConnection | LockedConnection,
    owner_user_id: str,
    window_id: str,
) -> int:
    """The actual (owner_user_id, window_id) → settled-cents join. Kept
    separate so both connection paths (caller-supplied vs self-opened) share
    one implementation."""
    import duckdb as _duckdb

    try:
        row = con.execute(
            "SELECT revenue_usd_cents, price_status FROM ad_fill_decisions "
            "WHERE owner_user_id = ? AND window_id = ?",
            [owner_user_id, window_id],
        ).fetchone()
    except _duckdb.CatalogException:
        # No ad_fill_decisions table yet → no fill decision was ever
        # persisted → no server-side price exists. Honest zero, never an
        # error that would bounce the telemetry flush.
        return 0
    if row is None or row[1] != "settled":
        # No fill record for this window, or the record is still unpriced
        # (CPM is a ranking signal, not settlement evidence).
        return 0
    return int(row[0])


def resolve_dwell_cap_ms(*, owner_user_id: str) -> int | None:
    """Resolve the per-identity dwell saturation cap (AFA-S2, W2-S2).

    The cap bounds one identity's countable focused dwell per (asset, day): past
    the cap, further dwell on the same asset the same day earns nothing (the
    sybil's extractable value is bounded). It is resolved PER IDENTITY here so a
    cap can be defined for some identities and not others: return ``None`` for
    an identity with no cap (unbounded), a positive ms ceiling otherwise.

    Today every identity gets the published structural ceiling
    (``DEFAULT_DAILY_ASSET_DWELL_CAP_MS`` — 6h of countable dwell on ONE asset in
    ONE day, an un-calibrated "no honest single-document day exceeds this"
    ceiling, documented in ``frame_ivt``; calibration against real traffic is a
    recorded follow-up). Module-scope seam (mirrors the value-mint seam) so
    tests can monkeypatch per-identity caps without touching the route.
    """
    _ = owner_user_id
    return DEFAULT_DAILY_ASSET_DWELL_CAP_MS


def register_ad_routes(app: FastAPI) -> None:
    """Mount the ad-border routes. Mirrors ``register_book_routes`` — one call
    from ``create_app``."""

    @app.post(
        "/api/ad/frame-telemetry",
        response_model=FrameTelemetryResponse,
        status_code=202,
        tags=["ad"],
    )
    async def frame_telemetry(
        batch_in: WindowFrameBatchIn, request: Request
    ) -> FrameTelemetryResponse:
        """Accrue one window's per-second frame-attention batch (Read SPR-09).

        Version-gates the wire shape (v2 and v3 accepted; v1 client-priced
        rejected), deserializes into the frozen SPR-05 contract (range
        validation → 422), resolves the authoritative per-asset content_class +
        ip_holder server-side, MINTS the window's ad value server-side from the
        server's own fill/pricing record (the client's ad_value_usd_cents is an
        IGNORED HINT — logged as client_hint, never trusted), CLASSIFIES the
        batch via the frame IVT anti-gaming classifier (AFA-S2:
        GIVT/SIVT-invalid seconds are
        dropped BEFORE allocation — never allocated, honestly counted in the
        response; a REVIEW window is held, never allocated), applies the
        per-identity dwell saturation cap when defined, and hands the
        batch to the SPR-05 accrual engine through the single-writer lock.
        Weighting + accrual + escrow are COMPOSED, not re-implemented.
        Accrual ≠ disbursement."""
        from runtime.db_lock import connect_write
        from substrate.ad_inventory import fill_decisions
        from substrate.ad_inventory.frame_attention import (
            FrameAttentionSample,
            FrameSecond,
            WindowFrameBatch,
        )
        from substrate.ad_inventory.frame_attention_accrual import (
            accrue_window,
            record_client_hint,
            window_reconciliation,
        )

        # (a) Version gate: a batch flushed by an emitter on a different contract
        # shape must not be silently mis-aggregated. 409 — the shape conflicts
        # with what this backend accrues against. The CURRENT version and the
        # previous one (v2 — a strict wire subset of v3: the value hint is
        # simply absent) are accepted so old emitters keep working; v1 — the
        # client-priced shape — is NOT in the accepted set and stays rejected.
        if batch_in.schema_version not in SUPPORTED_FRAME_TELEMETRY_SCHEMA_VERSIONS:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"frame-telemetry schema mismatch: emitter sent "
                    f"{batch_in.schema_version!r}, backend accrues "
                    f"{FRAME_TELEMETRY_SCHEMA_VERSION!r} (accepted: "
                    f"{sorted(SUPPORTED_FRAME_TELEMETRY_SCHEMA_VERSIONS)})"
                ),
            )

        db = _resolve_db_path()

        # (c) Resolve the authoritative per-asset gate values server-side. The
        # client's content_class hint is discarded; the documents table is the
        # single source of truth (the same column the §9.0 retrieval gate reads,
        # so the earn gate cannot drift from the read gate).
        asset_ids = {
            s.asset_id for sec in batch_in.seconds for s in sec.samples
        }
        from runtime.db_lock import connect_read

        con_r = connect_read(db)
        try:
            gate = _resolve_asset_gate(con_r, asset_ids)
        finally:
            con_r.close()
        asset_to_ip_holder: dict[str, str | None] = {
            aid: gate.get(aid, (None, None))[1] for aid in asset_ids
        }

        # (b) Deserialize into the frozen contract with the SERVER-resolved
        # content_class (never the client hint). The dataclass __post_init__
        # ranges validate every sample → ValueError → 422.
        try:
            seconds = tuple(
                FrameSecond(
                    second_index=sec.second_index,
                    lens=sec.lens,
                    samples=tuple(
                        FrameAttentionSample(
                            asset_id=s.asset_id,
                            viewport_area_fraction=s.viewport_area_fraction,
                            prominence=s.prominence,
                            focused_dwell_ms=s.focused_dwell_ms,
                            content_class=gate.get(s.asset_id, (None, None))[0],
                            chunk_id=s.chunk_id,
                        )
                        for s in sec.samples
                    ),
                )
                for sec in batch_in.seconds
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        owner_user_id = str(
            getattr(request.state, "user_id", None) or "__operator__"
        )

        # Accrue through the single-writer lock. This route runs inside the
        # --workers 1 uvicorn; accrue_window does not open its own writer.
        con_w = connect_write(db, purpose="ad/frame_telemetry")
        try:
            # (e) SERVER-MINTED value (ad-pipeline gap S1, frame-telemetry-v3):
            # ensure the fill ledger exists on this connection, then join the
            # server's OWN fill/pricing record — the durable snapshot
            # POST /api/ad/fills persisted at fill time. A missing/unsettled
            # record mints 0 (honest house/zero; never a fabricated price).
            # The client hint (if any) is captured but ONLY logged below —
            # never consulted. The module-level seam is monkeypatchable so
            # accrual-math tests can inject a value.
            fill_decisions.ensure_table(con_w)
            try:
                batch = WindowFrameBatch(
                    window_id=batch_in.window_id,
                    seconds=seconds,
                    ad_value_usd_cents=resolve_window_value_cents(
                        owner_user_id=owner_user_id,
                        window_id=batch_in.window_id,
                        con=con_w,
                    ),
                    schema_version=batch_in.schema_version,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

            # AFA-S2 — classify once and pass that exact result into accrual so
            # invalid seconds are removed before allocation and held windows
            # never allocate contributor value.
            classification = classify_batch(batch)

            result = accrue_window(
                con_w,
                batch,
                asset_to_ip_holder=asset_to_ip_holder,
                owner_user_id=owner_user_id,
                dwell_cap_ms=resolve_dwell_cap_ms(
                    owner_user_id=owner_user_id
                ),
                classification=classification,
            )
            if batch_in.ad_value_usd_cents is not None:
                # (f) The client's ad_value_usd_cents is an IGNORED HINT: it
                # never feeds the accrual (the value was minted server-side),
                # but it IS logged to the client-hint ledger for auditability —
                # what the client CLAIMED vs what the server minted.
                record_client_hint(
                    con_w,
                    window_id=batch_in.window_id,
                    batch_ref=result.batch_ref,
                    client_hint_ad_value_usd_cents=batch_in.ad_value_usd_cents,
                    telemetry_version=result.telemetry_version,
                )
            recon = window_reconciliation(con_w, batch.window_id)
        finally:
            con_w.close()

        # Filtered seconds: per-second exclusions for a PASS window; for a
        # REVIEW/BLOCK window NO second was allocated, so the whole window
        # counts as filtered (the verdict + signals explain why).
        if result.fraud_verdict in ("review", "block"):
            filtered_seconds = len(batch.seconds)
        else:
            filtered_seconds = sum(
                count for _, count in result.excluded_second_counts
            )

        return FrameTelemetryResponse(
            batch_ref=result.batch_ref,
            window_id=result.window_id,
            total_ad_value_cents=result.total_ad_value_cents,
            contributor_cents=recon["contributor_cents"],
            house_cents=recon["house_cents"],
            asset_count=len(result.asset_lines),
            reconciles=result.reconciles(),
            telemetry_version=result.telemetry_version,
            weighting_version=result.weighting_version,
            fraud_verdict=cast(
                Literal["pass", "review", "block"], result.fraud_verdict
            ),
            filtered_seconds=filtered_seconds,
            filtered_second_counts=dict(result.excluded_second_counts),
            verdict_signals=dict(result.verdict_signals),
            clamped_dwell_ms=result.clamped_dwell_ms,
            clamped_cents=result.clamped_cents,
        )

    @app.get("/api/ad/fill", response_model=AdFillResponse, tags=["ad"])
    async def ad_fill(
        document_id: str,
        page_index: int = Query(ge=0),
        position: str = "top",
    ) -> AdFillResponse:
        """Fill one reader ad-border slot (Read SPR-09 M3). Tries the paid
        advertiser matcher; on no match returns the real HOUSE fill — a
        promotion of a servable book (never blank). House candidates are drawn
        from the servable corpus (display title/author only — no gated body).

        The targeting signals are the allowlisted page topics; this v1 surface
        keeps the topic set empty (the operator-curated lead-gen inventory is
        typically unpopulated → the house path is the realistic default, per
        SPR-05 rigor #1). A richer topic resolution is a later wiring."""
        from runtime.db_lock import connect_read
        from substrate.ad_inventory.ad_bidding import LeadGenAdInventory
        from substrate.ad_inventory.reader_slots import (
            HousePromo,
            ReaderAdSlot,
            fill_slot,
        )
        from substrate.books.model import list_book_assets
        from substrate.constants import READER_AD_SLOT_POSITIONS

        if position not in READER_AD_SLOT_POSITIONS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"unknown slot position {position!r}; expected "
                    f"{list(READER_AD_SLOT_POSITIONS)}"
                ),
            )

        # House candidates: servable books only (gated bodies never promoted;
        # the summary carries display title/author only). The fill function
        # skips the book currently being read.
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            servable = list_book_assets(con, servable_only=True)
        finally:
            con.close()
        house_candidates = [
            HousePromo(
                promoted_document_id=a.document_id, title=a.title, author=a.author
            )
            for a in servable
        ]

        slot = ReaderAdSlot(
            document_id=document_id, page_index=page_index, position=position
        )
        # No operator-curated inventory wired into this v1 surface → the matcher
        # finds nothing and the house path fills (the honest zero-buyer default).
        fill = fill_slot(
            slot,
            LeadGenAdInventory(),
            page_topics=[],
            house_candidates=house_candidates,
        )

        ad_resp: AdCreativeResponse | None = None
        if fill.ad is not None:
            ad_resp = AdCreativeResponse(
                inventory_id=fill.ad.inventory_id,
                advertiser_display_name=fill.ad.advertiser_display_name,
                creative_url=fill.ad.creative_url,
                landing_url=fill.ad.landing_url,
            )
        house_resp: HousePromoResponse | None = None
        if fill.house is not None:
            house_resp = HousePromoResponse(
                promoted_document_id=fill.house.promoted_document_id,
                title=fill.house.title,
                author=fill.house.author,
            )

        return AdFillResponse(
            slot_id=slot.slot_id,
            document_id=document_id,
            page_index=page_index,
            position=position,
            kind=fill.kind,  # type: ignore[arg-type]
            revenue_usd_cents=fill.revenue_usd_cents,
            ad=ad_resp,
            house=house_resp,
        )

    @app.post("/api/ad/fills", response_model=MultiEdgeFillResponse, tags=["ad"])
    async def ad_fills(
        request: Request,
        body: MultiEdgeFillRequest,
    ) -> MultiEdgeFillResponse:
        """Decide every active border edge as one durable snapshot.

        Exact retries return the stored snapshot; they do not re-read or
        re-rank inventory.  Only active inventory belonging to an advertiser
        whose latest registry state is ACTIVE is eligible.  A selected ad is
        still *unpriced*: CPM is a ranking signal, not settlement evidence, so
        this route records and returns zero revenue.
        """
        from runtime.db_lock import connect_write
        from substrate.ad_inventory.ad_bidding import LeadGenAdInventory
        from substrate.ad_inventory.fill_decisions import (
            FillDecisionConflictError,
            decide_fills,
        )
        from substrate.ad_inventory.inventory_persistence import (
            load_serving_for_matcher,
        )
        from substrate.ad_inventory.reader_slots import (
            HousePromo,
            ReaderAdSlot,
            fill_slot,
        )
        from substrate.books.model import list_book_assets
        requested_positions = tuple(body.positions)
        if len(set(requested_positions)) != len(requested_positions):
            raise HTTPException(
                status_code=422,
                detail="positions must not contain duplicate edges",
            )

        owner_user_id = str(
            getattr(request.state, "user_id", None) or "__operator__"
        )
        db = _resolve_db_path()
        with connect_write(db, purpose="ad/fills:decide") as con:
            def _select() -> list[dict[str, object]]:
                targeted, flat = load_serving_for_matcher(con)
                # ``fill_slot`` is the canonical v1 matcher.  Second-generation
                # targeting items retain their flat item payload here; the
                # lens is the only allowlisted signal this border currently has.
                inventory = LeadGenAdInventory(
                    items=[item.item for item in targeted] + list(flat)
                )
                servable = list_book_assets(con, servable_only=True)
                houses = [
                    HousePromo(
                        promoted_document_id=asset.document_id,
                        title=asset.title,
                        author=asset.author,
                    )
                    for asset in servable
                ]
                selected: list[dict[str, object]] = []
                for position in requested_positions:
                    slot = ReaderAdSlot(
                        # Internal matching locator only.  It is never persisted
                        # or returned as a document identity when the caller has
                        # no document (Research/Write/Speak windows).
                        document_id=body.document_id or f"window:{body.window_id}",
                        page_index=body.page_index or 0,
                        position=position,
                    )
                    fill = fill_slot(
                        slot,
                        inventory,
                        page_topics=[body.lens],
                        cpm_to_cents=0,
                        house_candidates=houses,
                    )
                    selected.append(
                        {
                            "position": position,
                            "kind": fill.kind,
                            "revenue_usd_cents": 0,
                            "ad": (
                                {
                                    "inventory_id": fill.ad.inventory_id,
                                    "advertiser_display_name": (
                                        fill.ad.advertiser_display_name
                                    ),
                                    "creative_url": fill.ad.creative_url,
                                    "landing_url": fill.ad.landing_url,
                                }
                                if fill.ad is not None
                                else None
                            ),
                            "house": (
                                {
                                    "promoted_document_id": (
                                        fill.house.promoted_document_id
                                    ),
                                    "title": fill.house.title,
                                    "author": fill.house.author,
                                }
                                if fill.house is not None
                                else None
                            ),
                        }
                    )
                return selected

            try:
                decision = decide_fills(
                    con,
                    owner_user_id=owner_user_id,
                    window_id=body.window_id,
                    document_id=body.document_id,
                    page_index=body.page_index,
                    lens=body.lens,
                    positions=requested_positions,
                    select_fills=_select,
                )
            except FillDecisionConflictError as exc:
                raise HTTPException(
                    status_code=409,
                    detail="ad_fill_window_conflict",
                ) from exc

        return MultiEdgeFillResponse(
            window_id=decision.window_id,
            fills=[
                EdgeFillResponse.model_validate(
                    {
                        **fill,
                        "fill_decision_id": (
                            f"{decision.decision_id}:{fill['position']}"
                        ),
                        "slot_id": (
                            f"slot:{decision.decision_id}:{fill['position']}"
                        ),
                        "price_status": decision.price_status,
                    }
                )
                for fill in decision.fills
            ],
        )
