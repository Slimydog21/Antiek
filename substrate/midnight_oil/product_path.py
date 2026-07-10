"""Product path: goals + duration → recommended ceiling → explicit approve.

Composes existing ``create_job`` / ``approve_job`` / ``recommend_price_ceiling``
without reimplementing ceiling math or the worker. Human view is HTML-first.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .ceiling import ModelPricing, recommend_price_ceiling
from .job import (
    JobStore,
    MidnightOilJob,
    approve_job,
    create_job,
    get_job,
)

if TYPE_CHECKING:
    from .worker import WorkerStepResult


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
            "research_tier": j.research_tier,
            # Residual (adb): fanout used for recommended ceiling formula honesty.
            "fanout_depth": int(j.fanout_depth),
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
    research_tier: str | None = None,
) -> MidnightOilProductResult:
    """Product entry: create draft job and surface recommended price ceiling.

    Does not start work. Operator must call ``approve_price_ceiling`` next.
    """
    # Pre-compute recommendation for stable double-run checks on same inputs
    # (create_job uses the same math; assert identity below).
    # Residual (jl): pass research_tier so ceiling intensity matches create_job.
    recommended = recommend_price_ceiling(
        duration_minutes,
        model_id=model_id,
        fanout_depth=fanout_depth,
        pricing=pricing,
        research_tier=research_tier,
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
        research_tier=research_tier,
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
) -> WorkerStepResult:
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


def offline_goal_project_fn(
    job: MidnightOilJob,
    *,
    spent_per_goal: float = 0.05,
) -> float:
    """Projected max cost of the next ``offline_goal_step_fn`` step.

    Exact upper bound: the stub spends ``spent_per_goal`` while goals
    remain and 0.0 on the terminal step.
    """
    if len(job.spawn_ids) >= len(job.goals):
        return 0.0
    return float(spent_per_goal)


# Residual (bs): optional live step injector — default OFF, no silent network.
# Env ``ANTIEK_MIDNIGHT_OIL_LIVE_STEP``: 0/empty/false → offline only (default).
# When enabled AND a process-local injector is configured, run uses that
# step_fn; still never auto-enables without both env + configure call.
ANTIEK_MIDNIGHT_OIL_LIVE_STEP_ENV = "ANTIEK_MIDNIGHT_OIL_LIVE_STEP"

_LiveStepFn = Callable[[MidnightOilJob], "WorkerStepResult"]
_LiveProjectFn = Callable[[MidnightOilJob], float]
_live_step_fn: _LiveStepFn | None = None
_live_project_fn: _LiveProjectFn | None = None


def configure_midnight_oil_live_step(
    step_fn: _LiveStepFn | None,
    project_fn: _LiveProjectFn | None = None,
) -> None:
    """Install or clear the process-local live worker step injector.

    A live step spends real money, so installing one REQUIRES a matching
    ``project_fn`` declaring each step's projected maximum cost — the worker
    reserves that projection against the approved ceiling before the step
    runs. Passing ``step_fn=None`` clears both.

    Does nothing by itself — ``live_step_enabled()`` must also be true
    for ``run_job_offline`` to use the injector.
    """
    global _live_step_fn, _live_project_fn
    if step_fn is not None and project_fn is None:
        raise ValueError(
            "a live step_fn requires an explicit project_fn: live steps "
            "spend real money and the worker must reserve the projected "
            "maximum cost before each step runs"
        )
    _live_step_fn = step_fn
    _live_project_fn = project_fn if step_fn is not None else None


def clear_midnight_oil_live_step() -> None:
    configure_midnight_oil_live_step(None)


def live_step_enabled() -> bool:
    """True only when operator explicitly enables live Midnight Oil steps."""
    raw = (os.environ.get(ANTIEK_MIDNIGHT_OIL_LIVE_STEP_ENV) or "").strip().lower()
    return raw not in ("", "0", "false", "off", "no", "disabled")


def live_step_fn_installed() -> bool:
    """Residual (hy): True when a process-local live worker step fn is set."""
    return _live_step_fn is not None


def live_step_status_payload(
    *,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Residual (hy): offline-vs-live Midnight Oil step readiness (never enables)."""
    env = environ if environ is not None else None
    if env is not None:
        raw = str(env.get(ANTIEK_MIDNIGHT_OIL_LIVE_STEP_ENV) or "").strip().lower()
        live_env = raw not in ("", "0", "false", "off", "no", "disabled")
    else:
        live_env = live_step_enabled()
    injector = live_step_fn_installed()
    offline_honest = not (live_env and injector)
    notes: list[str] = []
    if offline_honest:
        notes.append(
            "Midnight Oil default: offline stub steps — no live multi-provider swarm."
        )
    else:
        notes.append(
            "Live step dual-gate satisfied (env + injector) — run may use live step_fn."
        )
    if live_env and not injector:
        notes.append(
            f"{ANTIEK_MIDNIGHT_OIL_LIVE_STEP_ENV}=on but no process injector "
            "(configure_midnight_oil_live_step required)."
        )
    return {
        "view_format": "html",
        "product_panel": "midnight_oil_live_step_status",
        "source": "substrate.midnight_oil.product_path",
        "offline_honest": offline_honest,
        "live_env": live_env,
        "injector_installed": injector,
        "live_env_flag": ANTIEK_MIDNIGHT_OIL_LIVE_STEP_ENV,
        "notes": notes,
        "html": (
            "<section data-view-format=\"html\" "
            'data-product-panel="midnight_oil_live_step_status">'
            f"<p>offline_honest={str(offline_honest).lower()} · "
            f"live_env={str(live_env).lower()} · "
            f"injector={str(injector).lower()}</p>"
            "<ul>"
            + "".join(f"<li>{n}</li>" for n in notes)
            + "</ul></section>"
        ),
    }


def resolve_worker_step_fn(
    *,
    spent_per_goal: float = 0.05,
    force_offline: bool = False,
    step_fn: _LiveStepFn | None = None,
    project_fn: _LiveProjectFn | None = None,
) -> tuple[_LiveStepFn, _LiveProjectFn, bool]:
    """Return (step_fn, project_fn, used_live).

    Live path requires: not force_offline, env enabled, and either explicit
    ``step_fn`` or process-local configured injector. Otherwise offline stub.
    A live step is only ever returned with a matching cost projection —
    an explicit live ``step_fn`` without ``project_fn`` fails closed.
    """
    offline = (
        lambda j: offline_goal_step_fn(j, spent_per_goal=spent_per_goal),
        lambda j: offline_goal_project_fn(j, spent_per_goal=spent_per_goal),
        False,
    )
    if force_offline:
        return offline
    if live_step_enabled():
        if step_fn is not None:
            if project_fn is None:
                raise ValueError(
                    "explicit live step_fn requires an explicit project_fn "
                    "(reserve-before-spend needs a projected max cost per step)"
                )
            return (step_fn, project_fn, True)
        if _live_step_fn is not None and _live_project_fn is not None:
            return (_live_step_fn, _live_project_fn, True)
    return offline


def run_job_offline(
    job_id: str,
    *,
    store: JobStore,
    max_steps: int | None = None,
    spent_per_goal: float = 0.05,
    advance_ms_per_step: int = 60_000,
    force_offline: bool = False,
    step_fn: _LiveStepFn | None = None,
    project_fn: _LiveProjectFn | None = None,
) -> dict[str, Any]:
    """Product entry: run approved job with worker loop + FakeClock.

    Default is **offline** stub steps (no live models). Live multi-provider
    injectors only run when:
      1. ``ANTIEK_MIDNIGHT_OIL_LIVE_STEP`` is explicitly on, AND
      2. a step_fn is passed or configured via ``configure_midnight_oil_live_step``

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
    resolved_fn, resolved_project_fn, used_live = resolve_worker_step_fn(
        spent_per_goal=spent_per_goal,
        force_offline=force_offline,
        step_fn=step_fn,
        project_fn=project_fn,
    )

    final = run_worker_loop(
        job_id,
        store=store,
        step_fn=resolved_fn,
        project_fn=resolved_project_fn,
        clock=clock,
        max_steps=steps_cap,
        advance_ms_per_step=advance_ms_per_step,
    )
    notes_list = [
        (
            "Live step injector active (env + configured step_fn)."
            if used_live
            else "Offline worker simulation — no live multi-provider calls."
        ),
        "Deposit separately to land HTML twins + usage/progress.",
        f"Live env {ANTIEK_MIDNIGHT_OIL_LIVE_STEP_ENV}="
        f"{'on' if live_step_enabled() else 'off (default)'}.",
    ]
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
        "offline": not used_live,
        "live_step": used_live,
        "live_step_env": ANTIEK_MIDNIGHT_OIL_LIVE_STEP_ENV,
        "live_step_env_enabled": live_step_enabled(),
        "product_panel": "midnight_oil_run",
        "source": "midnight_oil.run_job_offline",
        "notes_list": notes_list,
        "html": job_summary_html(final),
    }
