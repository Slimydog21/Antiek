"""Marketplace metrics API.

Thin HTTP adapter over ``substrate.marketplace_metrics``. The route is
read-only against DuckDB; POST only supplies operator-entered override maps for
data the substrate does not persist yet.
"""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.marketplace_metrics import (
    MarketplaceMetricsSourceError,
    MarketplaceSnapshot,
    build_snapshot_from_conn,
)


class MarketplaceSnapshotOverrideRequest(BaseModel):
    creator_paid_cents: dict[str, int] | None = Field(default=None)
    current_advertiser_spend: dict[str, int] | None = Field(default=None)
    prior_advertiser_spend: dict[str, int] | None = Field(default=None)


def _resolve_db_path() -> str:
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def _snapshot_payload(
    *,
    creator_paid_cents_override: Mapping[str, int] | None = None,
    current_advertiser_spend_override: Mapping[str, int] | None = None,
    prior_advertiser_spend_override: Mapping[str, int] | None = None,
) -> dict:
    from runtime.db_lock import connect_read

    try:
        with connect_read(_resolve_db_path()) as con:
            snapshot = build_snapshot_from_conn(
                con,
                creator_paid_cents_override=creator_paid_cents_override,
                current_advertiser_spend_override=current_advertiser_spend_override,
                prior_advertiser_spend_override=prior_advertiser_spend_override,
            )
    except MarketplaceMetricsSourceError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": {
                    "code": "marketplace_source_unavailable",
                    "message": str(exc),
                }
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "invalid_marketplace_override",
                    "message": str(exc),
                }
            },
        ) from exc
    return _encode_snapshot(snapshot)


def _encode_snapshot(snapshot: MarketplaceSnapshot) -> dict:
    publishers = snapshot.publishers
    status_counts = publishers.status_counts
    advertisers = snapshot.advertisers
    return {
        "creators": {
            "creator_count": snapshot.creators.creator_count,
            "total_paid_cents": snapshot.creators.total_paid_cents,
            "median_cents": snapshot.creators.median_cents,
            "p90_cents": snapshot.creators.p90_cents,
            "p99_cents": snapshot.creators.p99_cents,
            "long_tail_mass": snapshot.creators.long_tail_mass,
            "buckets": [
                {
                    "lower_cents": bucket.lower_cents,
                    "upper_cents": bucket.upper_cents,
                    "creator_count": bucket.creator_count,
                }
                for bucket in snapshot.creators.buckets
            ],
        },
        "publishers": {
            "status_counts": {
                "pre_onboarded": status_counts.pre_onboarded,
                "invited": status_counts.invited,
                "claimed": status_counts.claimed,
                "opted_out": status_counts.opted_out,
                "total": status_counts.total,
                "claim_rate": status_counts.claim_rate,
                "opt_out_rate": status_counts.opt_out_rate,
            },
            "total_escrow_accrued_cents": publishers.total_escrow_accrued_cents,
            "total_escrow_paid_cents": publishers.total_escrow_paid_cents,
            "unclaimed_escrow_cents": publishers.unclaimed_escrow_cents,
            "publishers_with_nontrivial_accrual": (
                publishers.publishers_with_nontrivial_accrual
            ),
        },
        "advertisers": {
            "advertiser_count_current": advertisers.advertiser_count_current,
            "advertiser_count_prior": advertisers.advertiser_count_prior,
            "retained_advertiser_count": advertisers.retained_advertiser_count,
            "new_advertiser_count": advertisers.new_advertiser_count,
            "churned_advertiser_count": advertisers.churned_advertiser_count,
            "total_spend_current_cents": advertisers.total_spend_current_cents,
            "total_spend_prior_cents": advertisers.total_spend_prior_cents,
            "retention_rate": advertisers.retention_rate,
            "crosses_self_service_threshold": (
                advertisers.crosses_self_service_threshold
            ),
        },
        "health": snapshot.health.value,
        "health_signals": list(snapshot.health_signals),
    }


def register_marketplace_routes(app: FastAPI) -> None:
    @app.get("/marketplace/snapshot", tags=["marketplace"])
    async def get_marketplace_snapshot() -> dict:
        return _snapshot_payload()

    @app.post("/marketplace/snapshot", tags=["marketplace"])
    async def post_marketplace_snapshot(
        req: MarketplaceSnapshotOverrideRequest,
    ) -> dict:
        return _snapshot_payload(
            creator_paid_cents_override=req.creator_paid_cents,
            current_advertiser_spend_override=req.current_advertiser_spend,
            prior_advertiser_spend_override=req.prior_advertiser_spend,
        )


__all__ = [
    "MarketplaceSnapshotOverrideRequest",
    "register_marketplace_routes",
]
