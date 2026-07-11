"""Authenticated, owner-bound Midnight Oil HTTP surface.

The durable owner store is the authorization boundary.  The legacy job store
remains an execution/detail substrate until the worker migration, but is never
queried until ownership has been established.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from substrate.midnight_oil import (
    create_with_recommended_ceiling,
    deposit_job_results,
    get_job,
    job_summary_html,
    product_result_html,
)
from substrate.midnight_oil.job import InMemoryJobStore, JobStore, _job_from_row, put_job_state
from substrate.midnight_oil.job_store import OperationState, OwnerJob, OwnerJobStore
from substrate.midnight_oil.spend_consent import (
    MAX_CEILING_CENTS,
    ConsentReceipt,
    JobConsentConfig,
    SpendConsentStore,
    decode_and_verify,
)

midnight_oil_router = APIRouter(prefix="/midnight-oil", tags=["midnight-oil"])
_DEPENDENCIES = "midnight_oil_dependencies"
CONSENT_TTL_MS = 15 * 60 * 1000


@dataclass(frozen=True)
class MidnightOilDependencies:
    owner_jobs: OwnerJobStore
    jobs: JobStore
    consents: SpendConsentStore
    active_key_id: str
    signing_key: bytes
    verification_keys: Mapping[str, bytes]
    clock_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000
    random_token: Callable[[int], str] = secrets.token_urlsafe

    def __post_init__(self) -> None:
        if not self.active_key_id.strip():
            raise ValueError("an active consent key id is required")
        if len(self.signing_key) < 32:
            raise ValueError("a 256-bit consent signing key is required")
        if self.verification_keys.get(self.active_key_id) != self.signing_key:
            raise ValueError("the active signing key must be in the verification keyring")


def reset_midnight_oil_store(store: JobStore | None = None) -> None:
    """Removed insecure compatibility hook.

    Tests must pass an explicit :class:`MidnightOilDependencies` bundle to
    ``register_midnight_oil_routes``.  Production must do the same.
    """
    del store
    raise RuntimeError("Midnight Oil dependencies must be explicitly injected")


def _deps(request: Request) -> MidnightOilDependencies:
    value = getattr(request.app.state, _DEPENDENCIES, None)
    if not isinstance(value, MidnightOilDependencies):
        raise RuntimeError("Midnight Oil durable dependencies are not configured")
    return value


def _owner(request: Request) -> str:
    value = getattr(request.state, "user_id", None)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=401, detail="authentication required")
    return value.strip()


def _owned(request: Request, job_id: str) -> tuple[MidnightOilDependencies, OwnerJob]:
    deps = _deps(request)
    job = deps.owner_jobs.get_job(owner_user_id=_owner(request), job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return deps, job


class CreateJobBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goals: list[str] = Field(min_length=1)
    duration_minutes: int = Field(gt=0)
    model_id: str | None = None
    fanout_depth: int = 3
    asset_id: str | None = None
    job_id: str | None = None
    research_tier: str | None = None


class ConsentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ceiling_cents: StrictInt | None = Field(default=None, ge=1, le=MAX_CEILING_CENTS)
    use_recommended: StrictBool = False
    force_below: StrictBool = False


class LegacyApproveBody(BaseModel):
    """Identifier-only tombstone; float approval authority is intentionally gone."""

    model_config = ConfigDict(extra="forbid")
    job_id: str


class DepositBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    draft_combined: bool = True
    record_progress: bool = True
    mark_complete: bool = True
    include_progress_html: bool = True


class RunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    max_steps: int | None = None
    spent_per_goal: float = 0.05
    auto_deposit: bool = False
    draft_combined: bool = True
    force_offline: bool = False


def _owner_payload(job: Any) -> dict[str, object]:
    return {
        "goals": list(job.goals),
        "duration_minutes": job.duration_minutes,
        "model_id": job.model_id,
        "research_tier": job.research_tier,
        "fanout_depth": int(job.fanout_depth),
        "asset_id": job.asset_id,
        "force_below_recommended": False,
        "display_usd": job.recommended_price_ceiling_usd,
    }


@midnight_oil_router.post("/create")
def post_create(request: Request, body: CreateJobBody) -> dict[str, Any]:
    deps = _deps(request)
    owner = _owner(request)
    try:
        staging = InMemoryJobStore()
        result = create_with_recommended_ceiling(
            body.goals,
            body.duration_minutes,
            store=staging,
            model_id=body.model_id,
            fanout_depth=body.fanout_depth,
            job_id=body.job_id,
            asset_id=body.asset_id,
            research_tier=body.research_tier,
        )
        deps.owner_jobs.put_job(
            OwnerJob(
                owner_user_id=owner,
                job_id=result.job.job_id,
                state_version=0,
                approved_ceiling_cents=None,
                consent_receipt_id=None,
                consent_config_hash=None,
                consent_issued_at_ms=None,
                consent_expires_at_ms=None,
                consent_claimed_at_ms=None,
                operation_id=None,
                operation_state=OperationState.NONE,
                dispatch_started_at_ms=None,
                dispatched_at_ms=None,
                completed_at_ms=None,
                payload=_owner_payload(result.job),
            )
        )
        legacy_row = staging.get_job(result.job.job_id)
        if legacy_row is None:
            raise RuntimeError("staged Midnight Oil job disappeared")
        deps.jobs.put_job(legacy_row)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    out = result.to_dict()
    out["html"] = product_result_html(result)
    return out


def _config(row: OwnerJob) -> JobConsentConfig:
    payload = row.payload
    goals = payload["goals"]
    duration = payload["duration_minutes"]
    fanout = payload["fanout_depth"]
    if not isinstance(goals, list) or any(not isinstance(goal, str) for goal in goals):
        raise ValueError("stored goals are invalid")
    if type(duration) is not int or type(fanout) is not int:
        raise ValueError("stored numeric configuration is invalid")
    return JobConsentConfig(
        job_id=row.job_id,
        goals=tuple(goals),
        duration_minutes=duration,
        model_id=None if payload.get("model_id") is None else str(payload["model_id"]),
        research_tier=str(payload["research_tier"]),
        fanout_depth=fanout,
        asset_id=None if payload.get("asset_id") is None else str(payload["asset_id"]),
    )


def _recommended_cents(row: OwnerJob) -> int:
    value = row.payload.get("display_usd")
    return int((Decimal(str(value)) * 100).to_integral_value(rounding=ROUND_FLOOR))


@midnight_oil_router.post("/jobs/{job_id}/spend-consent")
def post_spend_consent(
    request: Request, job_id: str, body: ConsentBody, response: Response
) -> dict[str, Any]:
    deps, row = _owned(request, job_id)
    owner = _owner(request)
    if row.operation_state is not OperationState.NONE:
        raise HTTPException(status_code=409, detail="job already has spend consent")
    try:
        config = _config(row)
        recommended = _recommended_cents(row)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="stored job configuration is invalid") from exc
    legacy_job = get_job(job_id, store=deps.jobs)
    if legacy_job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if body.use_recommended:
        if body.ceiling_cents is not None:
            raise HTTPException(status_code=400, detail="choose ceiling_cents or use_recommended")
        ceiling = recommended
    elif body.ceiling_cents is None:
        raise HTTPException(status_code=400, detail="ceiling_cents is required")
    else:
        ceiling = body.ceiling_cents
    if ceiling < recommended and not body.force_below:
        raise HTTPException(status_code=400, detail="ceiling is below the recommendation")
    if not 1 <= ceiling <= MAX_CEILING_CENTS:
        raise HTTPException(status_code=400, detail="ceiling_cents is outside authority bounds")

    now = deps.clock_ms()
    operation_id = deps.random_token(24)
    nonce = deps.random_token(32)
    token = deps.consents.issue(
        operator_id=owner,
        config=config,
        operation_id=operation_id,
        ceiling_cents=ceiling,
        issued_at_ms=now,
        expires_at_ms=now + CONSENT_TTL_MS,
        nonce=nonce,
        key_id=deps.active_key_id,
        signing_key=deps.signing_key,
    )
    receipt: ConsentReceipt = decode_and_verify(token, verification_keys=deps.verification_keys)
    published = deps.owner_jobs.publish_consent(
        owner_user_id=owner,
        job_id=job_id,
        expected_version=row.state_version,
        operation_id=operation_id,
        approved_ceiling_cents=ceiling,
        consent_receipt_id=receipt.receipt_id,
        consent_config_hash=receipt.config_hash,
        consent_issued_at_ms=receipt.issued_at_ms,
        consent_expires_at_ms=receipt.expires_at_ms,
    )
    if not published.applied:
        raise HTTPException(status_code=409, detail="job changed while consent was issued")
    response.headers["Cache-Control"] = "no-store"
    return {
        "token": token,
        "operation_id": operation_id,
        "ceiling_cents": ceiling,
        "issued_at_ms": receipt.issued_at_ms,
        "expires_at_ms": receipt.expires_at_ms,
    }


@midnight_oil_router.get("/jobs/{job_id}")
def get_job_route(request: Request, job_id: str) -> dict[str, Any]:
    deps, _ = _owned(request, job_id)
    job = get_job(job_id, store=deps.jobs)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "job_id": job.job_id,
        "goals": list(job.goals),
        "duration_minutes": job.duration_minutes,
        "model_id": job.model_id,
        "research_tier": job.research_tier,
        "fanout_depth": int(job.fanout_depth),
        "status": job.status,
        "recommended_price_ceiling_usd": job.recommended_price_ceiling_usd,
        "approved_ceiling_usd": job.approved_ceiling_usd,
        "force_below_recommended": job.force_below_recommended,
        "asset_id": job.asset_id,
        "spawn_ids": list(job.spawn_ids),
        "notes": job.notes,
        "view_format": "html",
        "runnable": False,
        "html": job_summary_html(job),
    }


@midnight_oil_router.post("/approve")
def post_approve(request: Request, body: LegacyApproveBody) -> None:
    _owned(request, body.job_id)
    raise HTTPException(status_code=410, detail="use the integer-cent spend-consent endpoint")


@midnight_oil_router.post("/run")
def post_run(request: Request, body: RunBody) -> dict[str, Any]:
    _owned(request, body.job_id)
    raise HTTPException(status_code=409, detail="dispatch is disabled until durable enqueue")


@midnight_oil_router.post("/deposit")
def post_deposit(request: Request, body: DepositBody) -> dict[str, Any]:
    from interfaces.research.api.engagement_routes import _eng, get_bench_usage_store
    from substrate.engagement_spine import progress_payload

    deps, _ = _owned(request, body.job_id)
    job = get_job(body.job_id, store=deps.jobs)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if body.mark_complete and job.status in ("approved", "running"):
        row = dict(deps.jobs.get_job(body.job_id) or {})
        row["status"] = "complete"
        put_job_state(_job_from_row(row), store=deps.jobs)
    try:
        deposit = deposit_job_results(
            body.job_id,
            job_store=deps.jobs,
            engagement_store=_eng(),
            draft_combined=body.draft_combined,
            bench_usage_store=get_bench_usage_store(create_if_missing=True),
            record_progress=body.record_progress,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    progress: dict[str, Any] | None = None
    if deposit.spawn_ids:
        try:
            progress = progress_payload(
                deposit.spawn_ids[0],
                store=_eng(),
                include_html=body.include_progress_html,
            )
        except (KeyError, ValueError):
            progress = None
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
        "job_status": (get_job(body.job_id, store=deps.jobs) or job).status,
        "view_format": "html",
        "html": deposit.html,
        "product_panel": "midnight_oil_deposit",
        "source": "midnight_oil.deposit_job_results",
    }


@midnight_oil_router.get("/live-step-status")
def get_live_step_status(request: Request) -> dict[str, Any]:
    _owner(request)
    from substrate.midnight_oil import live_step_status_payload

    return live_step_status_payload()


def register_midnight_oil_routes(
    app: FastAPI, *, dependencies: MidnightOilDependencies | None = None
) -> None:
    if dependencies is None:
        raise RuntimeError("Midnight Oil durable dependencies must be configured at startup")
    setattr(app.state, _DEPENDENCIES, dependencies)
    app.include_router(midnight_oil_router)


__all__ = ["MidnightOilDependencies", "midnight_oil_router", "register_midnight_oil_routes"]
