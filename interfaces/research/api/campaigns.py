"""Advertiser campaigns API (Sprint 23-24 phase 5).

GET /campaigns/{advertiser_id} — campaign-performance report.
Aggregates impressions, spend, click-through (where available)
for one advertiser.

The substrate currently has no separate ``campaigns`` table —
campaigns are a downstream conceptual rollup over (advertiser,
inventory_id, time window). This router computes the rollup from
the substrate's event log + the payout_transfers table on demand.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from runtime.db_lock import connect_read


class CampaignSummaryResponse(BaseModel):
    advertiser_id: str
    impressions: int
    spend_usd_cents: int
    creator_payout_usd_cents: int
    platform_share_usd_cents: int
    # Where the advertiser stands relative to their monthly budget,
    # if a budget was specified at submission.
    monthly_budget_usd_cents: int | None


def _refuse(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message}},
    )


def _resolve_db_path() -> str:
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def _load_advertiser_budget(
    con: Any,
    advertiser_id: str,
) -> tuple[bool, int | None]:
    """Returns (advertiser_exists, monthly_budget_usd_cents)."""
    try:
        row = con.execute(
            "SELECT monthly_budget_usd_cents FROM advertisers "
            "WHERE advertiser_id = ? "
            "ORDER BY row_inserted_at DESC LIMIT 1",
            [advertiser_id],
        ).fetchone()
    except Exception:
        return (False, None)
    if row is None:
        return (False, None)
    return (True, int(row[0]) if row[0] is not None else None)


def register_campaign_routes(app: FastAPI) -> None:
    """Mount the campaigns endpoint."""

    @app.get(
        "/campaigns/{advertiser_id}",
        response_model=CampaignSummaryResponse,
        tags=["campaigns"],
    )
    async def get_campaign_summary(
        advertiser_id: str,
    ) -> CampaignSummaryResponse:
        db = _resolve_db_path()
        con = connect_read(db)
        try:
            exists, monthly_budget = _load_advertiser_budget(
                con, advertiser_id,
            )
            if not exists:
                raise _refuse(
                    404, "advertiser_not_found",
                    f"advertiser_id {advertiser_id!r} not found",
                )
            # Impressions + spend are NOT yet emitted to the substrate
            # event log on the live path (the orchestrator integration
            # is the gap that follows this commit). For now the
            # endpoint returns zeros for the metrics with the budget
            # context — UI surfaces can render "no data yet" cleanly.
            impressions = 0
            spend = 0
            creator_payout = 0
            platform_share = 0
        finally:
            con.close()
        return CampaignSummaryResponse(
            advertiser_id=advertiser_id,
            impressions=impressions,
            spend_usd_cents=spend,
            creator_payout_usd_cents=creator_payout,
            platform_share_usd_cents=platform_share,
            monthly_budget_usd_cents=monthly_budget,
        )


__all__ = [
    "CampaignSummaryResponse",
    "register_campaign_routes",
]
