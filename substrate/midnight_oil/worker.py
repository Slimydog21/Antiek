"""Budget-guarded worker loop for Midnight Oil jobs."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation
from typing import Protocol

from .budget_ledger import BudgetCeilingExceeded, BudgetLedger
from .job import JobStore, MidnightOilJob, _job_from_row, put_job_state

_WORKER_ROLE = "research"


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
ProjectFn = Callable[[MidnightOilJob], float]


def _duration_ms(job: MidnightOilJob) -> int:
    return int(job.duration_minutes) * 60_000


def _usd_to_cents(value: float, *, ceiling: bool, field: str) -> int:
    """Convert a legacy USD boundary without ever increasing an approval.

    Approved ceilings round down. Projected and actual spend round up so
    sub-cent values cannot become free or under-reported.
    """
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{field} must be a finite value >= 0")
    try:
        amount = Decimal(str(value)) * 100
    except InvalidOperation as exc:
        raise ValueError(f"{field} must be valid USD") from exc
    rounding = ROUND_FLOOR if ceiling else ROUND_CEILING
    return int(amount.to_integral_value(rounding=rounding))


def _ledger_for(store: JobStore, job: MidnightOilJob) -> BudgetLedger:
    if job.approved_ceiling_usd is None:
        raise ValueError("approved_ceiling_usd is required before running")
    ceiling_cents = _usd_to_cents(
        job.approved_ceiling_usd, ceiling=True, field="approved_ceiling_usd"
    )
    if ceiling_cents <= 0:
        raise ValueError("approved_ceiling_usd must approve at least one cent")
    ledger = BudgetLedger(store.budget_db_path())
    ledger.ensure_schema()
    ledger.reserve(job.job_id, ceiling_cents, {_WORKER_ROLE: ceiling_cents})
    return ledger


def _sync_spend(job: MidnightOilJob, ledger: BudgetLedger) -> MidnightOilJob:
    balance = ledger.balance(job.job_id)
    return replace(job, spent_usd=balance.spent_cents / 100)


def run_worker_iteration(
    job_id: str,
    *,
    store: JobStore,
    step_fn: StepFn,
    project_fn: ProjectFn,
    clock: Clock,
    on_spawn: Callable[[MidnightOilJob, WorkerStepResult], None] | None = None,
) -> MidnightOilJob:
    """Run one project -> durable hold -> dispatch -> settle iteration."""
    row = store.get_job(job_id)
    if row is None:
        raise KeyError(f"unknown job_id: {job_id}")
    job = _job_from_row(row)
    if job.status in ("complete", "timed_out", "budget_halted", "failed"):
        return job
    if job.status not in ("approved", "running"):
        raise ValueError(f"job {job_id} status is {job.status!r}; must approve before running")

    ledger = _ledger_for(store, job)
    balance = ledger.balance(job.job_id)
    job = replace(job, spent_usd=balance.spent_cents / 100)
    if balance.held_cents > 0:
        failed = replace(
            job,
            status="failed",
            notes=(
                (job.notes + " | " if job.notes else "")
                + f"unsettled_reservation: ledger has {balance.held_cents} cents "
                "in open holds; provider reconciliation is required"
            ),
        )
        return put_job_state(failed, store=store)
    now = clock.now_ms()
    if job.started_at_ms is None:
        job = replace(job, status="running", started_at_ms=now, elapsed_ms=0)
    else:
        job = replace(job, status="running", elapsed_ms=max(0, now - job.started_at_ms))
    if job.elapsed_ms >= _duration_ms(job):
        return put_job_state(replace(job, status="timed_out"), store=store)

    projected_cents = _usd_to_cents(
        float(project_fn(job)), ceiling=False, field="project_fn result"
    )
    if projected_cents <= 0:
        raise ValueError(
            "project_fn result must be positive; a provider dispatch cannot be declared free"
        )

    def dispatch() -> tuple[WorkerStepResult, int]:
        result = step_fn(job)
        actual_cents = _usd_to_cents(float(result.spent_usd), ceiling=False, field="step spent_usd")
        return result, actual_cents

    def checkpoint_before_settle(result: WorkerStepResult, actual_cents: int) -> None:
        # Persist a terminal checkpoint while the ledger hold is still open.
        # A failed write becomes an unknown hold; a hard death leaves the open
        # hold. Either state blocks provider redispatch on restart.
        checkpoint_spawn_ids = job.spawn_ids
        if (
            actual_cents <= projected_cents
            and result.spawn_id
            and result.spawn_id not in checkpoint_spawn_ids
        ):
            checkpoint_spawn_ids += (result.spawn_id,)
        checkpoint = replace(
            job,
            status="failed",
            spent_usd=job.spent_usd + actual_cents / 100,
            spawn_ids=checkpoint_spawn_ids,
            notes=(
                (job.notes + " | " if job.notes else "")
                + "paid_step_checkpoint_pending_ledger_settlement"
            ),
        )
        put_job_state(checkpoint, store=store)

    try:
        result, balance = ledger.guarded_call(
            job.job_id,
            _WORKER_ROLE,
            projected_cents,
            dispatch,
            before_settle=checkpoint_before_settle,
        )
    except BudgetCeilingExceeded as exc:
        halted = replace(
            _sync_spend(job, ledger),
            status="budget_halted",
            notes=(
                (job.notes + " | " if job.notes else "")
                + f"budget_halt_preflight: requested {exc.requested_cents} cents; "
                f"only {exc.remaining_cents} cents remained; step not executed"
            ),
        )
        return put_job_state(halted, store=store)
    except BaseException:
        exception_balance = ledger.balance(job.job_id)
        if exception_balance.held_cents:
            outcome_note = (
                f"open hold {exception_balance.held_cents} cents retained for "
                "provider reconciliation"
            )
        else:
            outcome_note = f"conservative charge {projected_cents} cents recorded"
        failed = replace(
            job,
            spent_usd=exception_balance.spent_cents / 100,
            status="failed",
            notes=(
                (job.notes + " | " if job.notes else "")
                + f"step_exception: provider outcome unknown; {outcome_note}"
            ),
        )
        put_job_state(failed, store=store)
        raise

    job = replace(
        job,
        spent_usd=balance.spent_cents / 100,
    )
    actual_cents = _usd_to_cents(float(result.spent_usd), ceiling=False, field="step spent_usd")
    if actual_cents > projected_cents:
        job = replace(
            job,
            status="failed",
            notes=(
                (job.notes + " | " if job.notes else "")
                + f"reservation_overrun: true provider spend {actual_cents} "
                f"cents exceeded its {projected_cents}-cent hold"
            ),
        )
    else:
        spawn_ids = job.spawn_ids
        if result.spawn_id and result.spawn_id not in spawn_ids:
            spawn_ids += (result.spawn_id,)
        job = replace(
            job,
            spawn_ids=spawn_ids,
            elapsed_ms=max(0, clock.now_ms() - (job.started_at_ms or clock.now_ms())),
        )
        if result.done:
            job = replace(job, status="complete")
        elif job.elapsed_ms >= _duration_ms(job):
            job = replace(job, status="timed_out")
        if on_spawn is None:
            return put_job_state(job, store=store)

        # Spend has already settled. Persist a terminal fail-closed checkpoint
        # before invoking the projection callback. A process death anywhere in
        # the callback window therefore cannot make the paid step eligible for
        # automatic redispatch. Only callback success publishes the intended
        # running/complete state.
        intended_job = job
        callback_pending = replace(
            intended_job,
            status="failed",
            notes=(
                (intended_job.notes + " | " if intended_job.notes else "")
                + "on_spawn_pending_after_paid_checkpoint"
            ),
        )
        put_job_state(callback_pending, store=store)
        try:
            on_spawn(intended_job, result)
        except BaseException:
            failed = replace(
                callback_pending,
                notes=(callback_pending.notes + " | on_spawn_failed_after_durable_checkpoint"),
            )
            put_job_state(failed, store=store)
            raise
        return put_job_state(intended_job, store=store)
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
    """Drive iterations until terminal status or max_steps."""
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
        notes = job.notes + " | max_steps" if job.notes else "max_steps"
        return put_job_state(replace(job, status="failed", notes=notes), store=store)
    return job


def get_or_raise(job_id: str, *, store: JobStore) -> MidnightOilJob:
    row = store.get_job(job_id)
    if row is None:
        raise KeyError(job_id)
    return _job_from_row(row)
