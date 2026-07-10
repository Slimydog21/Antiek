"""Crash-conservative reservation accounting for Midnight Oil worker steps.

Assumptions: projections use the single pricing and intensity configuration in
``ceiling.py``; outstanding reservations represent unknown provider outcomes and
are therefore charged rather than released on worker recovery — by every
finalization surface (worker recovery, deposit, mark_complete), never just one.
Known bound: a crash DURING a provider call whose actual cost exceeded its
projection under-charges by (actual − projected); the projection's safety
factor makes this rare, and it can only understate by one step's delta.
"""

from __future__ import annotations

from dataclasses import replace

from .ceiling import SAFETY_FACTOR, TOKENS_PER_MINUTE, resolve_pricing, tier_multiplier
from .job import JobStore, MidnightOilJob, put_job_state


class BudgetCeilingExceeded(Exception):
    """Raised before dispatch when a reservation would exceed approval."""

    def __init__(self, job_id: str, projected_max_usd: float, remaining_usd: float) -> None:
        self.job_id = job_id
        self.projected_max_usd = projected_max_usd
        self.remaining_usd = remaining_usd
        super().__init__(
            f"job_id={job_id} projected_max_usd={projected_max_usd} "
            f"remaining_usd={remaining_usd}"
        )


def project_step_cost(job: MidnightOilJob, *, step_minutes: float = 1.0) -> float:
    """Return an unrounded maximum step cost using ceiling.py assumptions."""
    rates = resolve_pricing(job.model_id)
    return (
        step_minutes
        * TOKENS_PER_MINUTE
        * (rates.input_usd_per_1m + rates.output_usd_per_1m)
        / 1_000_000.0
        * job.fanout_depth
        * SAFETY_FACTOR
        * tier_multiplier(job.research_tier)
    )


def reserve_step(
    job: MidnightOilJob, projected_max_usd: float, *, store: JobStore
) -> MidnightOilJob:
    """Persist a reservation before dispatch, assuming an approved ceiling."""
    if projected_max_usd <= 0:
        raise ValueError("projected_max_usd must be positive")
    ceiling = job.approved_ceiling_usd
    if ceiling is None:
        raise ValueError("approved_ceiling_usd is required before reserving")
    remaining = ceiling - job.spent_usd - job.reserved_usd
    if job.spent_usd + job.reserved_usd + projected_max_usd > ceiling + 1e-12:
        raise BudgetCeilingExceeded(job.job_id, projected_max_usd, remaining)
    return put_job_state(
        replace(job, reserved_usd=job.reserved_usd + projected_max_usd), store=store
    )


def settle_step(job: MidnightOilJob, actual_usd: float, *, store: JobStore) -> MidnightOilJob:
    """Record full actual spend and release the single outstanding reservation."""
    notes = job.notes
    if actual_usd > job.reserved_usd + 1e-12:
        note = f"settle_over_projection: actual={actual_usd} projected={job.reserved_usd}"
        notes = f"{notes} | {note}" if notes else note
    return put_job_state(
        replace(
            job,
            spent_usd=job.spent_usd + actual_usd,
            reserved_usd=0.0,
            notes=notes,
        ),
        store=store,
    )


def absorb_orphaned_reservation(job: MidnightOilJob, *, store: JobStore) -> MidnightOilJob:
    """Charge an unknown prior outcome at its durable reservation amount."""
    if job.reserved_usd <= 0:
        return job
    amount = job.reserved_usd
    note = f"orphaned_reservation_absorbed: {amount}"
    notes = f"{job.notes} | {note}" if job.notes else note
    return put_job_state(
        replace(
            job,
            spent_usd=job.spent_usd + amount,
            reserved_usd=0.0,
            notes=notes,
        ),
        store=store,
    )
