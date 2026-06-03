"""Ad-border HTTP surface (Read SPR-09 M2 + M3).

Two thin adapters over the EXISTING SPR-05 ad-economics substrate. Neither
re-implements weighting, accrual, or fill — they compose the substrate
functions and adapt them to HTTP.

* ``POST /api/ad/frame-telemetry`` receives the per-window ``WindowFrameBatch``
  the SPR-07 frontend emitter flushes, and hands it to the SPR-05 accrual engine
  (``frame_attention_accrual.accrue_window`` → per-second ``weigh_second`` →
  the ONE sanctioned escrow seam ``ip_holders.accrue_escrow`` + house seconds).
  The route's only added responsibilities are (a) version-gating the wire shape,
  (b) deserializing into the frozen dataclasses (their ``__post_init__`` ranges
  validate the payload → 422), (c) resolving the AUTHORITATIVE per-asset
  ``content_class`` + ``ip_holder_id`` server-side (the client hint is NEVER
  trusted — the module contract requires the backend to resolve it), and
  (d) persisting through the single-writer lock.

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

from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from substrate.ad_inventory.frame_attention import FRAME_TELEMETRY_SCHEMA_VERSION

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
    ad_value_usd_cents: int
    schema_version: str = FRAME_TELEMETRY_SCHEMA_VERSION


class FrameTelemetryResponse(BaseModel):
    """The reconciled outcome of accruing one window batch. Carries no body —
    only the trace anchor + the conserved cents split (per the M6 invariant
    Σ contributor + house == total)."""

    batch_ref: str
    window_id: str
    total_ad_value_cents: int
    contributor_cents: int
    house_cents: int
    asset_count: int
    reconciles: bool
    telemetry_version: str
    weighting_version: str


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


def _resolve_asset_gate(
    con: object, asset_ids: set[str]
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


def register_ad_routes(app: FastAPI) -> None:
    """Mount the ad-border routes. Mirrors ``register_book_routes`` — one call
    from ``create_app``."""

    @app.post(
        "/api/ad/frame-telemetry",
        response_model=FrameTelemetryResponse,
        status_code=202,
        tags=["ad"],
    )
    async def frame_telemetry(batch_in: WindowFrameBatchIn) -> FrameTelemetryResponse:
        """Accrue one window's per-second frame-attention batch (Read SPR-09).

        Version-gates the wire shape, deserializes into the frozen SPR-05
        contract (range validation → 422), resolves the authoritative per-asset
        content_class + ip_holder server-side, and hands the batch to the SPR-05
        accrual engine through the single-writer lock. Weighting + accrual +
        escrow are COMPOSED, not re-implemented. Accrual ≠ disbursement."""
        from runtime.db_lock import connect_write
        from substrate.ad_inventory.frame_attention import (
            FrameAttentionSample,
            FrameSecond,
            WindowFrameBatch,
        )
        from substrate.ad_inventory.frame_attention_accrual import (
            accrue_window,
            window_reconciliation,
        )

        # (a) Version gate: a batch flushed by an emitter on a different contract
        # shape must not be silently mis-aggregated. 409 — the shape conflicts
        # with what this backend accrues against.
        if batch_in.schema_version != FRAME_TELEMETRY_SCHEMA_VERSION:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"frame-telemetry schema mismatch: emitter sent "
                    f"{batch_in.schema_version!r}, backend accrues "
                    f"{FRAME_TELEMETRY_SCHEMA_VERSION!r}"
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
            batch = WindowFrameBatch(
                window_id=batch_in.window_id,
                seconds=seconds,
                ad_value_usd_cents=batch_in.ad_value_usd_cents,
                schema_version=batch_in.schema_version,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        # (d) Accrue through the single-writer lock. This route runs inside the
        # --workers 1 uvicorn; accrue_window does not open its own writer.
        con_w = connect_write(db, purpose="ad/frame_telemetry")
        try:
            result = accrue_window(
                con_w, batch, asset_to_ip_holder=asset_to_ip_holder
            )
            recon = window_reconciliation(con_w, batch.window_id)
        finally:
            con_w.close()

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
