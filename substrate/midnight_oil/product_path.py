"""Product path: goals + duration → recommended ceiling → explicit approve.

Composes existing ``create_job`` / ``approve_job`` / ``recommend_price_ceiling``
without reimplementing ceiling math or the worker. Human view is HTML-first.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .ceiling import ModelPricing, recommend_price_ceiling
from .job import (
    JobStore,
    MidnightOilJob,
    approve_job,
    create_job,
    get_job,
)


@dataclass(frozen=True)
class MidnightOilProductResult:
    """Outcome of the create→recommend product entry."""

    job: MidnightOilJob
    recommended_price_ceiling_usd: float
    view_format: str = "html"
    runnable: bool = False

    def to_dict(self) -> dict[str, Any]:
        j = self.job
        return {
            "job_id": j.job_id,
            "goals": list(j.goals),
            "duration_minutes": j.duration_minutes,
            "model_id": j.model_id,
            "status": j.status,
            "recommended_price_ceiling_usd": self.recommended_price_ceiling_usd,
            "approved_ceiling_usd": j.approved_ceiling_usd,
            "force_below_recommended": j.force_below_recommended,
            "asset_id": j.asset_id,
            "notes": j.notes,
            "view_format": self.view_format,
            "runnable": self.runnable,
        }


def create_with_recommended_ceiling(
    goals: Sequence[str],
    duration_minutes: int,
    *,
    store: JobStore,
    model_id: str | None = None,
    fanout_depth: int = 3,
    pricing: ModelPricing | None = None,
    job_id: str | None = None,
    asset_id: str | None = None,
) -> MidnightOilProductResult:
    """Product entry: create draft job and surface recommended price ceiling.

    Does not start work. Operator must call ``approve_price_ceiling`` next.
    """
    # Pre-compute recommendation for stable double-run checks on same inputs
    # (create_job uses the same math; assert identity below).
    recommended = recommend_price_ceiling(
        duration_minutes,
        model_id=model_id,
        fanout_depth=fanout_depth,
        pricing=pricing,
    )
    job = create_job(
        list(goals),
        duration_minutes,
        store=store,
        model_id=model_id,
        fanout_depth=fanout_depth,
        pricing=pricing,
        job_id=job_id,
        asset_id=asset_id,
    )
    if job.recommended_price_ceiling_usd != recommended:
        raise RuntimeError(
            "create_job ceiling diverged from recommend_price_ceiling product surface"
        )
    return MidnightOilProductResult(
        job=job,
        recommended_price_ceiling_usd=recommended,
        view_format="html",
        runnable=False,
    )


def approve_price_ceiling(
    job_id: str,
    ceiling_usd: float | None = None,
    *,
    store: JobStore,
    force_below: bool = False,
    use_recommended: bool = False,
) -> MidnightOilProductResult:
    """Product entry: explicit operator approve of a price ceiling.

    * ``use_recommended=True`` approves at the system recommendation.
    * ``ceiling_usd`` below recommended fails unless ``force_below=True``.
    * After approve, ``runnable`` is True (worker may start; not auto-launched).
    """
    prior = get_job(job_id, store=store)
    if prior is None:
        raise KeyError(f"unknown job_id: {job_id}")
    if use_recommended:
        amount = prior.recommended_price_ceiling_usd
    elif ceiling_usd is not None:
        amount = float(ceiling_usd)
    else:
        raise ValueError("ceiling_usd is required unless use_recommended=True")

    job = approve_job(
        job_id,
        amount,
        store=store,
        force_below=force_below,
    )
    return MidnightOilProductResult(
        job=job,
        recommended_price_ceiling_usd=job.recommended_price_ceiling_usd,
        view_format="html",
        runnable=job.status == "approved",
    )


def create_recommend_and_approve(
    goals: Sequence[str],
    duration_minutes: int,
    *,
    store: JobStore,
    ceiling_usd: float | None = None,
    use_recommended: bool = True,
    force_below: bool = False,
    model_id: str | None = None,
    fanout_depth: int = 3,
    pricing: ModelPricing | None = None,
    job_id: str | None = None,
    asset_id: str | None = None,
) -> MidnightOilProductResult:
    """Product convenience: create + recommend, then approve in one call.

    Default approves at recommended ceiling. Still requires explicit approve
    step (this function *is* that approve); never starts the worker.
    """
    created = create_with_recommended_ceiling(
        goals,
        duration_minutes,
        store=store,
        model_id=model_id,
        fanout_depth=fanout_depth,
        pricing=pricing,
        job_id=job_id,
        asset_id=asset_id,
    )
    return approve_price_ceiling(
        created.job.job_id,
        ceiling_usd,
        store=store,
        force_below=force_below,
        use_recommended=use_recommended if ceiling_usd is None else False,
    )


def job_summary_html(job: MidnightOilJob) -> str:
    """HTML-first human view of a Midnight Oil job (never PDF)."""
    from substrate.engagement_spine.project import project_to_html

    lines = [
        f"Midnight Oil job {job.job_id}",
        f"Status: {job.status}",
        f"Duration: {job.duration_minutes} minutes",
        f"Recommended ceiling: ${job.recommended_price_ceiling_usd:.2f}",
    ]
    if job.approved_ceiling_usd is not None:
        lines.append(f"Approved ceiling: ${job.approved_ceiling_usd:.2f}")
    if job.force_below_recommended:
        lines.append("Force-below recommended: yes")
    if job.model_id:
        lines.append(f"Model: {job.model_id}")
    for i, g in enumerate(job.goals, 1):
        lines.append(f"Goal {i}: {g}")
    if job.notes:
        lines.append(f"Notes: {job.notes}")

    blocks: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": "Midnight Oil job receipt"}],
        }
    ]
    for line in lines:
        blocks.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": line}],
            }
        )
    return project_to_html(
        {"type": "doc", "content": blocks},
        document_id=job.job_id,
        creator="midnight_oil",
    )


def product_result_html(result: MidnightOilProductResult) -> str:
    return job_summary_html(result.job)


def offline_goal_step_fn(
    job: MidnightOilJob,
    *,
    spent_per_goal: float = 0.05,
) -> "WorkerStepResult":
    """Default offline step: one synthetic result per goal, no network.

    Used by product ``run_job_offline`` so operators can exercise the swarm
    path without a live multi-provider worker. Costs are fixed stubs for
    budget-halt testing honesty — not real API prices.
    """
    from .worker import WorkerStepResult

    idx = len(job.spawn_ids)
    if idx >= len(job.goals):
        return WorkerStepResult(spent_usd=0.0, done=True)
    goal = job.goals[idx]
    done = idx + 1 >= len(job.goals)
    return WorkerStepResult(
        spent_usd=float(spent_per_goal),
        spawn_id=f"spn_moil_{job.job_id}_{idx}",
        output_text=f"Offline worker synthesis for goal: {goal}",
        insights=(f"Insight on: {goal}",),
        questions=(f"What remains open for: {goal}?",),
        done=done,
    )


def run_job_offline(
    job_id: str,
    *,
    store: JobStore,
    max_steps: int | None = None,
    spent_per_goal: float = 0.05,
    advance_ms_per_step: int = 60_000,
) -> dict[str, Any]:
    """Product entry: run approved job with offline goal step_fn + FakeClock.

    Does **not** call live models. Returns job summary + step counts for UI.
    Terminal statuses: complete | timed_out | budget_halted | failed.
    """
    from .worker import FakeClock, run_worker_loop

    job = get_job(job_id, store=store)
    if job is None:
        raise KeyError(f"unknown job_id: {job_id}")
    if job.status not in ("approved", "running"):
        raise ValueError(
            f"job {job_id} status is {job.status!r}; must be approved before run"
        )

    steps_cap = max_steps if max_steps is not None else max(len(job.goals) + 2, 4)
    clock = FakeClock(0)

    def step_fn(j: MidnightOilJob):
        return offline_goal_step_fn(j, spent_per_goal=spent_per_goal)

    final = run_worker_loop(
        job_id,
        store=store,
        step_fn=step_fn,
        clock=clock,
        max_steps=steps_cap,
        advance_ms_per_step=advance_ms_per_step,
    )
    return {
        "job_id": final.job_id,
        "status": final.status,
        "spent_usd": final.spent_usd,
        "approved_ceiling_usd": final.approved_ceiling_usd,
        "spawn_ids": list(final.spawn_ids),
        "goals_total": len(final.goals),
        "steps_cap": steps_cap,
        "elapsed_ms": final.elapsed_ms,
        "notes": final.notes,
        "view_format": "html",
        "runnable": final.status == "approved",
        "offline": True,
        "product_panel": "midnight_oil_run",
        "source": "midnight_oil.run_job_offline",
        "notes_list": [
            "Offline worker simulation — no live multi-provider calls.",
            "Deposit separately to land HTML twins + usage/progress.",
        ],
        "html": job_summary_html(final),
    }
