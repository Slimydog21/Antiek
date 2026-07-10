"""Offline worker loop for Midnight Oil jobs.

Injectable clock and step function — unit tests never sleep or hit the
network. Budget safety is reserve-before-spend: every step declares a
projected maximum cost via ``project_fn``, the projection is durably
reserved against the approved ceiling BEFORE the step runs, and a step
whose projection does not fit is never executed. When a step overruns its
own projection, the reported spend is recorded truthfully; when actual
spend is unknowable (crash mid-step, lost settlement write, nonsense spend
report), the job fails closed with the reservation left on the row for
operator reconciliation — spend is never silently discarded or guessed.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Protocol

from .job import (
    JobStore,
    MidnightOilJob,
    _job_from_row,
    _job_to_row,
    put_job_state,
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

# Projected maximum USD the next step may spend. Must be a finite value
# >= the step's true worst case; the worker refuses to run a step whose
# projection does not fit under the approved ceiling.
ProjectFn = Callable[[MidnightOilJob], float]


def _duration_ms(job: MidnightOilJob) -> int:
    return int(job.duration_minutes) * 60_000


def run_worker_iteration(
    job_id: str,
    *,
    store: JobStore,
    step_fn: StepFn,
    project_fn: ProjectFn,
    clock: Clock,
    on_spawn: Callable[[MidnightOilJob, WorkerStepResult], None] | None = None,
) -> MidnightOilJob:
    """Run one worker step with reserve-before-spend budget enforcement.

    Order per iteration: project → reserve durably → step → settle. A step
    whose projected maximum cost does not fit under the approved ceiling is
    never called. A crash between reserve and settle leaves the reservation
    on the job row; the next iteration fails closed for operator
    reconciliation instead of guessing whether the money moved.

    Raises if the job was never approved, or if ``project_fn`` returns a
    non-finite or negative projection.
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

    if job.elapsed_ms >= _duration_ms(job):
        job = replace(job, status="timed_out")
        return put_job_state(job, store=store)

    # Fail closed on a dangling reservation: a prior iteration reserved but
    # never settled (crash mid-step, or a settlement write that never landed).
    # Whether that money moved is unknowable here — only the operator can
    # reconcile against provider billing. reserved_usd of 0.0 still marks an
    # in-flight step; only None means no step is pending.
    if job.reserved_usd is not None:
        job = replace(
            job,
            status="failed",
            notes=(
                (job.notes + " | " if job.notes else "")
                + f"unsettled_reservation: {job.reserved_usd} USD was reserved "
                "by a prior step that never settled; operator reconciliation "
                "against provider billing is required before this job can be "
                "trusted"
            ),
        )
        return put_job_state(job, store=store)

    # Pre-flight: if already at/over ceiling, halt without calling step_fn.
    if job.spent_usd >= ceiling:
        job = replace(job, status="budget_halted")
        return put_job_state(job, store=store)

    projected = float(project_fn(job))
    if not math.isfinite(projected) or projected < 0.0:
        raise ValueError(
            f"project_fn returned {projected!r}; projected step cost must be "
            "a finite value >= 0"
        )

    # No epsilon, deliberately: float rounding here can only halt early,
    # never admit an over-ceiling step. Combined with the strict overrun
    # check below (actual <= projected) and the monotonicity of float
    # addition, settled spend can never exceed the approved ceiling:
    # spent + actual <= spent + projected <= ceiling, exactly.
    if job.spent_usd + projected > ceiling:
        # Prevention, not accounting: the step never runs, no money moves.
        job = replace(
            job,
            status="budget_halted",
            notes=(
                (job.notes + " | " if job.notes else "")
                + f"budget_halt_preflight: projected step max {projected} + "
                f"spent {job.spent_usd} exceeds ceiling {ceiling}; step not "
                "executed"
            ),
        )
        return put_job_state(job, store=store)

    # Reserve durably BEFORE the step so a crash mid-step is visible, then
    # re-read to detect an interleaved writer. A single concurrent worker
    # per job_id is a REQUIREMENT (platform single-writer invariant): under
    # a put/get-only store this check is a tripwire, not mutual exclusion —
    # two workers interleaving between re-read and step can still overlap.
    # The step runs against exactly the snapshot we validated and wrote; the
    # re-read must match it byte-for-byte, so even token-preserving
    # interference (e.g. mutated spent_usd or ceiling) stops the iteration
    # before any money moves.
    token = uuid.uuid4().hex
    job = replace(job, reserved_usd=projected, reservation_token=token)
    put_job_state(job, store=store)
    reread_row = store.get_job(job_id)
    if reread_row != _job_to_row(job):
        raise RuntimeError(
            f"interference detected on job {job_id}: the reserved row read "
            "back differently than written; a concurrent writer exists and "
            "single-writer per job is required"
        )

    try:
        result = step_fn(job)
    except BaseException:
        # Persist the fail-closed outcome durably BEFORE propagating: the
        # reservation stays on the row and the status says so, whether or
        # not anyone ever retries this job.
        put_job_state(
            replace(
                job,
                status="failed",
                notes=(
                    (job.notes + " | " if job.notes else "")
                    + f"step_exception: step raised before settlement; "
                    f"reservation {projected} kept for operator "
                    "reconciliation"
                ),
            ),
            store=store,
        )
        raise
    actual = float(result.spent_usd)
    if not math.isfinite(actual) or actual < 0.0:
        # The step reported an unusable spend value (NaN/inf: unknowable;
        # negative: a "refund" the worker must not credit against the
        # ceiling). Keep the reservation on the row as the audit trail and
        # stop the job for operator reconciliation against provider billing.
        job = replace(
            job,
            status="failed",
            notes=(
                (job.notes + " | " if job.notes else "")
                + f"invalid_step_spend: step reported {result.spent_usd!r}; "
                f"reservation {projected} kept for operator reconciliation"
            ),
        )
        return put_job_state(job, store=store)

    if actual > projected:
        # The step violated its own projection. The money already left, so
        # it is recorded truthfully — hiding it would falsify the ledger.
        job = replace(
            job,
            spent_usd=job.spent_usd + actual,
            reserved_usd=None,
            reservation_token=None,
            status="failed",
            notes=(
                (job.notes + " | " if job.notes else "")
                + f"reservation_overrun: step spent {actual} > reserved "
                f"{projected}; true spend recorded"
            ),
        )
        return put_job_state(job, store=store)

    spawn_ids = job.spawn_ids
    if result.spawn_id and result.spawn_id not in spawn_ids:
        spawn_ids = spawn_ids + (result.spawn_id,)
    job = replace(
        job,
        spent_usd=job.spent_usd + actual,
        reserved_usd=None,
        reservation_token=None,
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
    project_fn: ProjectFn,
    clock: Clock,
    max_steps: int = 100,
    advance_ms_per_step: int = 60_000,
    on_spawn: Callable[[MidnightOilJob, WorkerStepResult], None] | None = None,
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
            project_fn=project_fn,
            clock=clock,
            on_spawn=on_spawn,
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
