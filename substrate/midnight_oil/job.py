"""Midnight Oil job schema: create → recommend ceiling → approve."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from typing import Any, Literal, Protocol, runtime_checkable

from substrate.dispatch.research_tier import (
    DEFAULT_RESEARCH_TIER,
    normalize_research_tier,
)

from .ceiling import ModelPricing, recommend_price_ceiling

JobStatus = Literal[
    "draft",
    "awaiting_approval",
    "approved",
    "running",
    "complete",
    "timed_out",
    "budget_halted",
    "failed",
]


@dataclass(frozen=True)
class MidnightOilJob:
    job_id: str
    goals: tuple[str, ...]
    duration_minutes: int
    model_id: str | None
    recommended_price_ceiling_usd: float
    status: JobStatus
    approved_ceiling_usd: float | None = None
    spent_usd: float = 0.0
    # Projected max USD reserved for an in-flight step (reserve-before-spend).
    # None = no step in flight; any float (including 0.0) marks an in-flight
    # step, so a crash mid-step is detectable even for zero-cost projections.
    # Non-None on a loaded row means a prior step never settled — fail closed.
    reserved_usd: float | None = None
    # Unique token written with the reservation; re-read before the step runs
    # to detect an interleaved concurrent worker (best-effort under a
    # put/get store — the platform invariant is single-writer per job).
    reservation_token: str | None = None
    asset_id: str | None = None
    spawn_ids: tuple[str, ...] = ()
    started_at_ms: int | None = None
    elapsed_ms: int = 0
    force_below_recommended: bool = False
    notes: str = ""
    # Residual (gs): curated research tier for autonomous runs (fast|deep|wrestle).
    research_tier: str = DEFAULT_RESEARCH_TIER
    # Residual (adb): fan-out depth used for recommended ceiling (parity formula).
    fanout_depth: int = 3


@runtime_checkable
class JobStore(Protocol):
    def put_job(self, job: dict[str, Any]) -> None: ...
    def get_job(self, job_id: str) -> dict[str, Any] | None: ...


@dataclass
class InMemoryJobStore:
    _jobs: dict[str, dict[str, Any]] = field(default_factory=dict)

    def put_job(self, job: dict[str, Any]) -> None:
        self._jobs[job["job_id"]] = dict(job)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        row = self._jobs.get(job_id)
        return dict(row) if row is not None else None


def _job_to_row(job: MidnightOilJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "goals": list(job.goals),
        "duration_minutes": job.duration_minutes,
        "model_id": job.model_id,
        "recommended_price_ceiling_usd": job.recommended_price_ceiling_usd,
        "status": job.status,
        "approved_ceiling_usd": job.approved_ceiling_usd,
        "spent_usd": job.spent_usd,
        "reserved_usd": job.reserved_usd,
        "reservation_token": job.reservation_token,
        "asset_id": job.asset_id,
        "spawn_ids": list(job.spawn_ids),
        "started_at_ms": job.started_at_ms,
        "elapsed_ms": job.elapsed_ms,
        "force_below_recommended": job.force_below_recommended,
        "notes": job.notes,
        "research_tier": job.research_tier,
        "fanout_depth": int(job.fanout_depth),
    }


def _job_from_row(row: dict[str, Any]) -> MidnightOilJob:
    fanout = int(row.get("fanout_depth") or 3)
    if fanout <= 0:
        fanout = 3
    return MidnightOilJob(
        job_id=row["job_id"],
        goals=tuple(row.get("goals") or ()),
        duration_minutes=int(row["duration_minutes"]),
        model_id=row.get("model_id"),
        recommended_price_ceiling_usd=float(row["recommended_price_ceiling_usd"]),
        status=row["status"],
        approved_ceiling_usd=(
            None
            if row.get("approved_ceiling_usd") is None
            else float(row["approved_ceiling_usd"])
        ),
        spent_usd=float(row.get("spent_usd") or 0.0),
        reserved_usd=(
            None
            if row.get("reserved_usd") is None
            else float(row["reserved_usd"])
        ),
        reservation_token=row.get("reservation_token"),
        asset_id=row.get("asset_id"),
        spawn_ids=tuple(row.get("spawn_ids") or ()),
        started_at_ms=row.get("started_at_ms"),
        elapsed_ms=int(row.get("elapsed_ms") or 0),
        force_below_recommended=bool(row.get("force_below_recommended") or False),
        notes=str(row.get("notes") or ""),
        research_tier=normalize_research_tier(row.get("research_tier")),
        fanout_depth=fanout,
    )


def create_job(
    goals: list[str] | tuple[str, ...],
    duration_minutes: int,
    *,
    store: JobStore,
    model_id: str | None = None,
    fanout_depth: int = 3,
    pricing: ModelPricing | None = None,
    job_id: str | None = None,
    asset_id: str | None = None,
    research_tier: str | None = None,
) -> MidnightOilJob:
    """Create a draft Midnight Oil job with a recommended price ceiling.

    Does **not** start work — operator must ``approve_job`` first.
    """
    cleaned = tuple(g.strip() for g in goals if g and str(g).strip())
    if not cleaned:
        raise ValueError("at least one non-empty goal is required")
    if duration_minutes <= 0:
        raise ValueError("duration_minutes must be positive")

    jid = job_id or f"moil_{uuid.uuid4().hex[:16]}"
    tier = normalize_research_tier(research_tier)
    # Residual (jl): ceiling recommendation scales with research_tier.
    ceiling = recommend_price_ceiling(
        duration_minutes,
        model_id=model_id,
        fanout_depth=fanout_depth,
        pricing=pricing,
        research_tier=tier,
    )
    job = MidnightOilJob(
        job_id=jid,
        goals=cleaned,
        duration_minutes=duration_minutes,
        model_id=model_id,
        recommended_price_ceiling_usd=ceiling,
        status="awaiting_approval",
        asset_id=asset_id or f"moil_asset_{jid.removeprefix('moil_')}",
        research_tier=tier,
        # Residual (adb): persist fanout used for ceiling so API/UI formula match.
        fanout_depth=int(fanout_depth) if int(fanout_depth) > 0 else 3,
    )
    store.put_job(_job_to_row(job))
    return job


def approve_job(
    job_id: str,
    ceiling_usd: float,
    *,
    store: JobStore,
    force_below: bool = False,
) -> MidnightOilJob:
    """Explicitly approve a price ceiling before the worker may run.

    Requires ``ceiling_usd >= recommended`` unless ``force_below`` is True
    (operator override with a recorded warning note).
    """
    row = store.get_job(job_id)
    if row is None:
        raise KeyError(f"unknown job_id: {job_id}")
    job = _job_from_row(row)
    if job.status not in ("awaiting_approval", "draft"):
        raise ValueError(f"job {job_id} status is {job.status!r}; cannot approve")
    if ceiling_usd <= 0:
        raise ValueError("ceiling_usd must be positive")
    if ceiling_usd < job.recommended_price_ceiling_usd and not force_below:
        raise ValueError(
            f"ceiling_usd {ceiling_usd} is below recommended "
            f"{job.recommended_price_ceiling_usd}; pass force_below=True to override"
        )
    notes = job.notes
    if ceiling_usd < job.recommended_price_ceiling_usd and force_below:
        notes = (
            notes + " | "
            if notes
            else ""
        ) + (
            f"force_below: approved {ceiling_usd} < recommended "
            f"{job.recommended_price_ceiling_usd}"
        )
    updated = replace(
        job,
        status="approved",
        approved_ceiling_usd=float(ceiling_usd),
        force_below_recommended=bool(
            force_below and ceiling_usd < job.recommended_price_ceiling_usd
        ),
        notes=notes,
    )
    store.put_job(_job_to_row(updated))
    return updated


def get_job(job_id: str, *, store: JobStore) -> MidnightOilJob | None:
    row = store.get_job(job_id)
    return _job_from_row(row) if row else None


def put_job_state(job: MidnightOilJob, *, store: JobStore) -> MidnightOilJob:
    store.put_job(_job_to_row(job))
    return job
