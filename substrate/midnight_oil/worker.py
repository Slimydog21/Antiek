"""Offline worker loop for Midnight Oil jobs.

Injectable clock and step function — unit tests never sleep or hit the
network. Reserves the projected step cost BEFORE dispatch and halts when the
reservation would exceed the approved ceiling — a step whose conservative
projection would breach is never attempted (SPR-05 reserve-before-spend).
Honest bound: if a step's ACTUAL cost exceeds its projection, the full actual
is still recorded and the next iteration halts — overshoot is bounded by a
single step's (actual − projected), not eliminated by fiat.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Protocol

from .job import JobStore, MidnightOilJob, _job_from_row, put_job_state
from .reservation import (
    BudgetCeilingExceeded,
    absorb_orphaned_reservation,
    project_step_cost,
    reserve_step,
    settle_step,
)


class Clock(Protocol):
    def now_ms(self) -> int: ...


@dataclass
class FakeClock:
    """Injectable clock for tests."""

    _now: int = 0

    def now_ms(self) -> int:
        return self._now

    def advance(self, ms: int) -> None:
        self._now += int(ms)


@dataclass(frozen=True)
class WorkerStepResult:
    """Outcome of one worker iteration (one goal chase / spawn)."""

    spent_usd: float
    spawn_id: str | None = None
    output_text: str = ""
    insights: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()
    done: bool = False


StepFn = Callable[[MidnightOilJob], WorkerStepResult]


def _duration_ms(job: MidnightOilJob) -> int:
    return int(job.duration_minutes) * 60_000


def run_worker_iteration(
    job_id: str,
    *,
    store: JobStore,
    step_fn: StepFn,
    clock: Clock,
    on_spawn: Callable[[MidnightOilJob, WorkerStepResult], None] | None = None,
    project_fn: Callable[[MidnightOilJob], float] | None = None,
) -> MidnightOilJob:
    """Run one worker step. Hard-halts on budget; times out on duration.

    Raises if the job was never approved.
    """
    row = store.get_job(job_id)
    if row is None:
        raise KeyError(f"unknown job_id: {job_id}")
    job = _job_from_row(row)

    if job.status in ("complete", "timed_out", "budget_halted", "failed"):
        return job

    if job.status not in ("approved", "running"):
        raise ValueError(
            f"job {job_id} status is {job.status!r}; must approve before running"
        )

    if job.approved_ceiling_usd is None:
        raise ValueError("approved_ceiling_usd is required before running")
    ceiling = job.approved_ceiling_usd

    now = clock.now_ms()
    if job.started_at_ms is None:
        job = replace(job, status="running", started_at_ms=now, elapsed_ms=0)
    else:
        elapsed = max(0, now - job.started_at_ms)
        job = replace(job, status="running", elapsed_ms=elapsed)

    # Absorb before ANY terminal return: a timed-out recovery must still charge
    # the unknown prior outcome, or spent_usd understates the conservative truth.
    job = absorb_orphaned_reservation(job, store=store)

    if job.elapsed_ms >= _duration_ms(job):
        job = replace(job, status="timed_out")
        return put_job_state(job, store=store)

    # Pre-flight: if already at/over ceiling, halt without calling step_fn.
    if job.spent_usd >= ceiling:
        job = replace(job, status="budget_halted")
        return put_job_state(job, store=store)

    projected = (project_fn or project_step_cost)(job)
    try:
        job = reserve_step(job, projected, store=store)
    except BudgetCeilingExceeded:
        job = replace(
            job,
            status="budget_halted",
            notes=(job.notes + " | " if job.notes else "")
            + f"budget_halt_preflight: projected={projected} spent={job.spent_usd} "
            f"reserved={job.reserved_usd} ceiling={ceiling}",
        )
        return put_job_state(job, store=store)

    result = step_fn(job)
    job = settle_step(job, float(result.spent_usd), store=store)

    spawn_ids = job.spawn_ids
    if result.spawn_id and result.spawn_id not in spawn_ids:
        spawn_ids = spawn_ids + (result.spawn_id,)
    job = replace(
        job,
        spawn_ids=spawn_ids,
        elapsed_ms=max(0, clock.now_ms() - (job.started_at_ms or clock.now_ms())),
    )
    if on_spawn is not None:
        on_spawn(job, result)
    if result.done:
        job = replace(job, status="complete")
    # Re-check duration after step.
    elif job.elapsed_ms >= _duration_ms(job):
        job = replace(job, status="timed_out")
    return put_job_state(job, store=store)


def run_worker_loop(
    job_id: str,
    *,
    store: JobStore,
    step_fn: StepFn,
    clock: Clock,
    max_steps: int = 100,
    advance_ms_per_step: int = 60_000,
    on_spawn: Callable[[MidnightOilJob, WorkerStepResult], None] | None = None,
    project_fn: Callable[[MidnightOilJob], float] | None = None,
) -> MidnightOilJob:
    """Drive iterations until terminal status or max_steps.

    When ``clock`` is a ``FakeClock``, advances it each step so duration
    tests terminate without wall time.
    """
    for _ in range(max_steps):
        job = run_worker_iteration(
            job_id,
            store=store,
            step_fn=step_fn,
            clock=clock,
            on_spawn=on_spawn,
            project_fn=project_fn,
        )
        if job.status in ("complete", "timed_out", "budget_halted", "failed"):
            return job
        if hasattr(clock, "advance"):
            clock.advance(advance_ms_per_step)
    job = get_or_raise(job_id, store=store)
    if job.status == "running":
        job = replace(job, status="failed", notes=(job.notes + " | max_steps" if job.notes else "max_steps"))
        return put_job_state(job, store=store)
    return job


def get_or_raise(job_id: str, *, store: JobStore) -> MidnightOilJob:
    row = store.get_job(job_id)
    if row is None:
        raise KeyError(job_id)
    return _job_from_row(row)
