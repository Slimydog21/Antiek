"""Midnight Oil REST surface — create → recommend ceiling → approve → deposit.

Standalone APIRouter (same discipline as engagement_routes). Process-local
InMemoryJobStore by default; tests call reset_midnight_oil_store().
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.midnight_oil import (
    approve_price_ceiling,
    create_with_recommended_ceiling,
    deposit_job_results,
    get_job,
    job_summary_html,
    product_result_html,
)
from substrate.midnight_oil.job import InMemoryJobStore, JobStore, put_job_state, _job_from_row

midnight_oil_router = APIRouter(prefix="/midnight-oil", tags=["midnight-oil"])

_job_store: JobStore | None = None


def reset_midnight_oil_store(store: JobStore | None = None) -> None:
    global _job_store
    _job_store = store if store is not None else InMemoryJobStore()


def _store() -> JobStore:
    global _job_store
    if _job_store is None:
        _job_store = InMemoryJobStore()
    return _job_store


class CreateJobBody(BaseModel):
    goals: list[str] = Field(min_length=1)
    duration_minutes: int = Field(gt=0)
    model_id: str | None = None
    fanout_depth: int = 3
    asset_id: str | None = None
    job_id: str | None = None


class ApproveBody(BaseModel):
    job_id: str
    ceiling_usd: float | None = None
    use_recommended: bool = False
    force_below: bool = False


class DepositBody(BaseModel):
    """Deposit job results into engagement twins + HTML (progress + usage)."""

    job_id: str
    draft_combined: bool = True
    record_progress: bool = True
    mark_complete: bool = True
    include_progress_html: bool = True


@midnight_oil_router.post("/create")
def post_create(body: CreateJobBody) -> dict[str, Any]:
    try:
        result = create_with_recommended_ceiling(
            body.goals,
            body.duration_minutes,
            store=_store(),
            model_id=body.model_id,
            fanout_depth=body.fanout_depth,
            job_id=body.job_id,
            asset_id=body.asset_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    out = result.to_dict()
    out["html"] = product_result_html(result)
    return out


@midnight_oil_router.post("/approve")
def post_approve(body: ApproveBody) -> dict[str, Any]:
    try:
        result = approve_price_ceiling(
            body.job_id,
            body.ceiling_usd,
            store=_store(),
            force_below=body.force_below,
            use_recommended=body.use_recommended,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    out = result.to_dict()
    out["html"] = product_result_html(result)
    return out


@midnight_oil_router.get("/jobs/{job_id}")
def get_job_route(job_id: str) -> dict[str, Any]:
    job = get_job(job_id, store=_store())
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown job_id: {job_id}")
    return {
        "job_id": job.job_id,
        "goals": list(job.goals),
        "duration_minutes": job.duration_minutes,
        "model_id": job.model_id,
        "status": job.status,
        "recommended_price_ceiling_usd": job.recommended_price_ceiling_usd,
        "approved_ceiling_usd": job.approved_ceiling_usd,
        "force_below_recommended": job.force_below_recommended,
        "asset_id": job.asset_id,
        "spawn_ids": list(job.spawn_ids),
        "notes": job.notes,
        "view_format": "html",
        "runnable": job.status == "approved",
        "html": job_summary_html(job),
    }


@midnight_oil_router.post("/deposit")
def post_deposit(body: DepositBody) -> dict[str, Any]:
    """Deposit job results as HTML + twins; record progress/usage when available.

    Residual (bh) product path for operator-visible deposit outcome after
    approve (or simulated complete). Worker may still run out of band.
    """
    from interfaces.research.api.engagement_routes import (
        get_bench_usage_store,
        _eng,
    )
    from substrate.engagement_spine import progress_payload

    job = get_job(body.job_id, store=_store())
    if job is None:
        raise HTTPException(status_code=404, detail=f"unknown job_id: {body.job_id}")

    if body.mark_complete and job.status in ("approved", "running"):
        row = dict(_store().get_job(body.job_id) or {})
        row["status"] = "complete"
        put_job_state(_job_from_row(row), store=_store())

    try:
        deposit = deposit_job_results(
            body.job_id,
            job_store=_store(),
            engagement_store=_eng(),
            draft_combined=body.draft_combined,
            bench_usage_store=get_bench_usage_store(create_if_missing=True),
            record_progress=body.record_progress,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    progress: dict[str, Any] | None = None
    if deposit.spawn_ids:
        try:
            progress = progress_payload(
                deposit.spawn_ids[0],
                store=_eng(),
                include_html=body.include_progress_html,
            )
        except Exception:
            progress = None

    job_after = get_job(body.job_id, store=_store())
    return {
        "job_id": deposit.job_id,
        "asset_id": deposit.asset_id,
        "document_id": deposit.document_id,
        "twin_count": deposit.twin_count,
        "spawn_ids": list(deposit.spawn_ids),
        "draft_combined": deposit.draft_combined,
        "usage_recorded": deposit.usage_recorded,
        "usage_event": deposit.usage_event,
        "progress_seeded": deposit.progress_seeded,
        "progress": progress,
        "job_status": job_after.status if job_after else None,
        "view_format": "html",
        "html": deposit.html,
        "product_panel": "midnight_oil_deposit",
        "source": "midnight_oil.deposit_job_results",
        "notes": [
            "Deposit lands HTML research asset + twin notes.",
            "Progress plan→cite→complete seeded when spawn ids exist.",
        ],
    }


def register_midnight_oil_routes(app: FastAPI) -> None:
    app.include_router(midnight_oil_router)


__all__ = [
    "midnight_oil_router",
    "register_midnight_oil_routes",
    "reset_midnight_oil_store",
]
