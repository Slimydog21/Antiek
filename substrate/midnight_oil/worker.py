"""Budget-guarded worker loop for Midnight Oil jobs."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, InvalidOperation
from typing import Protocol

from .budget_ledger import BudgetCeilingExceeded, BudgetLedger
from .job import (
    JobStore,
    MidnightOilJob,
    MidnightOilStepEvidence,
    _job_from_row,
    put_job_state,
)
from .job_store import OperationState, OwnerJobStore
from .operation_queue import OperationQueue, provider_idempotency_key

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
    route_receipt: dict[str, object] | None = None
    source_receipts: tuple[dict[str, str], ...] = ()
    done: bool = False


_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)\b(?:api[_-]?key|authorization)\s*[:=]\s*[^\s<]+"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{8,}=*"),
)


def _redact_evidence_text(value: object, *, limit: int) -> str:
    text = str(value or "")[:limit]
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def _step_evidence(
    result: WorkerStepResult,
    *,
    step_key: str,
) -> MidnightOilStepEvidence:
    route: dict[str, object] | None = None
    if result.route_receipt is not None:
        route = {
            str(key)[:128]: (
                _redact_evidence_text(value, limit=2048)
                if isinstance(value, str)
                else value
            )
            for key, value in result.route_receipt.items()
            if isinstance(value, (str, int, float, bool)) or value is None
        }
    sources = tuple(
        {
            str(key)[:128]: _redact_evidence_text(value, limit=2048)
            for key, value in receipt.items()
        }
        for receipt in result.source_receipts[:100]
    )
    return MidnightOilStepEvidence(
        step_key=step_key,
        spawn_id=(None if result.spawn_id is None else str(result.spawn_id)[:512]),
        output_text=_redact_evidence_text(result.output_text, limit=200_000),
        insights=tuple(
            _redact_evidence_text(value, limit=20_000) for value in result.insights[:100]
        ),
        questions=tuple(
            _redact_evidence_text(value, limit=20_000) for value in result.questions[:100]
        ),
        route_receipt=route,
        source_receipts=sources,
    )


StepFn = Callable[[MidnightOilJob], WorkerStepResult]
ProjectFn = Callable[[MidnightOilJob], float]


@dataclass(frozen=True)
class WorkerLease:
    operation_id: str
    owner_user_id: str
    job_id: str
    worker_id: str
    step_index: int
    lease_generation: int

    def idempotency_key(self, step_index: int) -> str:
        return provider_idempotency_key(self.operation_id, step_index)


def lease_authorized_operation(
    *,
    operation_id: str,
    owner_user_id: str,
    job_id: str,
    owner_jobs: OwnerJobStore,
    operation_queue: OperationQueue,
    jobs: JobStore,
    worker_id: str,
    now_ms: int,
    lease_expires_at_ms: int,
) -> WorkerLease:
    """Recheck immutable authority, owner-CAS, then acquire one queue lease."""
    authority = owner_jobs.get_job(owner_user_id=owner_user_id, job_id=job_id)
    queued = operation_queue.get(operation_id)
    legacy_row = jobs.get_job(job_id)
    if authority is None or queued is None or legacy_row is None:
        raise ValueError("durable operation is incomplete")
    if authority.operation_id != operation_id or (
        queued.owner_user_id,
        queued.job_id,
    ) != (owner_user_id, job_id):
        raise ValueError("operation identity conflicts with durable authority")
    payload = authority.payload
    durable_goals = payload.get("goals")
    immutable_matches = (
        isinstance(durable_goals, list)
        and all(type(goal) is str for goal in durable_goals)
        and tuple(legacy_row.get("goals") or ()) == tuple(durable_goals)
        and legacy_row.get("duration_minutes") == payload.get("duration_minutes")
        and legacy_row.get("model_id") == payload.get("model_id")
        and legacy_row.get("research_tier") == payload.get("research_tier")
        and legacy_row.get("fanout_depth") == payload.get("fanout_depth")
        and legacy_row.get("asset_id") == payload.get("asset_id")
    )
    if not immutable_matches or authority.approved_ceiling_cents is None:
        raise ValueError("job configuration requires reconciliation")
    expected_usd = authority.approved_ceiling_cents / 100
    existing_ceiling = legacy_row.get("approved_ceiling_usd")
    if existing_ceiling is not None and _usd_to_cents(
        float(existing_ceiling), ceiling=True, field="approved_ceiling_usd"
    ) != authority.approved_ceiling_cents:
        raise ValueError("legacy ceiling conflicts with durable authority")
    if authority.operation_state is OperationState.QUEUED:
        transitioned = owner_jobs.compare_and_set(
            owner_user_id=owner_user_id,
            job_id=job_id,
            expected_version=authority.state_version,
            expected_state=OperationState.QUEUED,
            operation_id=operation_id,
            next_state=OperationState.RUNNING,
            dispatch_started_at_ms=now_ms,
        )
        authority = transitioned.job or authority
    repair_key = provider_idempotency_key(operation_id, queued.next_step_index)
    terminal_repair = (
        authority.operation_state
        in {
            OperationState.COMPLETE,
            OperationState.FAILED,
            OperationState.BUDGET_HALTED,
            OperationState.TIMED_OUT,
        }
        and repair_key in tuple(legacy_row.get("completed_step_keys") or ())
    )
    if authority.operation_state is not OperationState.RUNNING and not terminal_repair:
        raise ValueError("operation is not dispatchable")
    # Project authority before exposing the dispatchable lease. A crash after
    # this idempotent write but before lease can be recovered without dispatch.
    updated = dict(legacy_row)
    updated["approved_ceiling_usd"] = expected_usd
    if updated.get("status") in {"awaiting_approval", "draft"}:
        updated["status"] = "approved"
    jobs.put_job(updated)
    leased, won = operation_queue.lease(
        operation_id=operation_id,
        worker_id=worker_id,
        leased_at_ms=now_ms,
        lease_expires_at_ms=lease_expires_at_ms,
    )
    if not won:
        raise ValueError("operation is already leased")
    if leased.state != "running":
        raise ValueError("operation lease did not persist")
    return WorkerLease(
        operation_id,
        owner_user_id,
        job_id,
        worker_id,
        leased.next_step_index,
        leased.lease_generation,
    )


IdempotentStepFn = Callable[[MidnightOilJob, str], WorkerStepResult]


def _run_leased_worker_iteration_fenced(
    lease: WorkerLease,
    *,
    operation_queue: OperationQueue,
    owner_jobs: OwnerJobStore,
    store: JobStore,
    step_fn: IdempotentStepFn,
    project_fn: ProjectFn,
    clock: Clock,
    on_spawn: Callable[[MidnightOilJob, WorkerStepResult], None] | None = None,
) -> MidnightOilJob:
    """Propagate the durable provider key and checkpoint step progression."""
    key = lease.idempotency_key(lease.step_index)
    dispatched = False

    def dispatch(current: MidnightOilJob) -> WorkerStepResult:
        nonlocal dispatched
        dispatched = True
        return step_fn(current, key)

    existing = get_or_raise(lease.job_id, store=store)
    if key in existing.returned_step_keys and key not in existing.completed_step_keys:
        authority = owner_jobs.get_job(
            owner_user_id=lease.owner_user_id, job_id=lease.job_id
        )
        if authority is not None and authority.operation_state is OperationState.RUNNING:
            owner_jobs.compare_and_set(
                owner_user_id=lease.owner_user_id,
                job_id=lease.job_id,
                expected_version=authority.state_version,
                expected_state=OperationState.RUNNING,
                operation_id=lease.operation_id,
                next_state=OperationState.FAILED_RECONCILE,
                completed_at_ms=clock.now_ms(),
            )
        raise RuntimeError("provider-returned step requires settlement reconciliation")
    if key in existing.completed_step_keys:
        job = existing
    else:
        job = run_worker_iteration(
            lease.job_id,
            store=store,
            step_fn=dispatch,
            project_fn=project_fn,
            clock=clock,
            on_spawn=on_spawn,
            step_identity=key,
        )
    terminal_states = {
        "complete": OperationState.COMPLETE,
        "failed": OperationState.FAILED,
        "budget_halted": OperationState.BUDGET_HALTED,
        "timed_out": OperationState.TIMED_OUT,
    }
    terminal = terminal_states.get(job.status)
    if terminal is OperationState.FAILED:
        try:
            if BudgetLedger(store.budget_db_path()).balance(job.job_id).held_cents > 0:
                terminal = OperationState.FAILED_RECONCILE
        except Exception:
            terminal = OperationState.FAILED_RECONCILE
    if terminal is not None:
        authority = owner_jobs.get_job(
            owner_user_id=lease.owner_user_id, job_id=lease.job_id
        )
        if authority is None or authority.operation_id != lease.operation_id:
            raise RuntimeError("terminal authority requires reconciliation")
        if authority.operation_state is OperationState.RUNNING:
            changed = owner_jobs.compare_and_set(
                owner_user_id=lease.owner_user_id,
                job_id=lease.job_id,
                expected_version=authority.state_version,
                expected_state=OperationState.RUNNING,
                operation_id=lease.operation_id,
                next_state=terminal,
                completed_at_ms=clock.now_ms(),
            )
            if not changed.applied:
                raise RuntimeError("terminal authority requires reconciliation")
    return job


def run_leased_worker_iteration(
    lease: WorkerLease,
    *,
    operation_queue: OperationQueue,
    owner_jobs: OwnerJobStore,
    store: JobStore,
    step_fn: IdempotentStepFn,
    project_fn: ProjectFn,
    clock: Clock,
    on_spawn: Callable[[MidnightOilJob, WorkerStepResult], None] | None = None,
) -> MidnightOilJob:
    """Execute all paid side effects under the durable lease coordinator."""
    key = lease.idempotency_key(lease.step_index)

    def action() -> tuple[MidnightOilJob, bool]:
        result = _run_leased_worker_iteration_fenced(
            lease,
            operation_queue=operation_queue,
            owner_jobs=owner_jobs,
            store=store,
            step_fn=step_fn,
            project_fn=project_fn,
            clock=clock,
            on_spawn=on_spawn,
        )
        completed = key in get_or_raise(lease.job_id, store=store).completed_step_keys
        return result, completed

    return operation_queue.run_fenced(
        operation_id=lease.operation_id,
        worker_id=lease.worker_id,
        lease_generation=lease.lease_generation,
        now_ms=clock.now_ms(),
        expected_step_index=lease.step_index,
        action=action,
    )


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
    step_identity: str | None = None,
    authority_guard: Callable[[], None] | None = None,
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

    def guard() -> None:
        if authority_guard is not None:
            authority_guard()

    guard()

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
        guard()
        return put_job_state(failed, store=store)
    now = clock.now_ms()
    if job.started_at_ms is None:
        job = replace(job, status="running", started_at_ms=now, elapsed_ms=0)
    else:
        job = replace(job, status="running", elapsed_ms=max(0, now - job.started_at_ms))
    if job.elapsed_ms >= _duration_ms(job):
        guard()
        return put_job_state(replace(job, status="timed_out"), store=store)

    projected_cents = _usd_to_cents(
        float(project_fn(job)), ceiling=False, field="project_fn result"
    )
    if projected_cents <= 0:
        raise ValueError(
            "project_fn result must be positive; a provider dispatch cannot be declared free"
        )

    def dispatch() -> tuple[WorkerStepResult, int]:
        guard()
        result = step_fn(job)
        actual_cents = _usd_to_cents(float(result.spent_usd), ceiling=False, field="step spent_usd")
        return result, actual_cents

    returned_evidence: MidnightOilStepEvidence | None = None

    def checkpoint_before_settle(result: WorkerStepResult, actual_cents: int) -> None:
        nonlocal returned_evidence
        guard()
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
        evidence_key = step_identity or f"unkeyed-step-{len(job.step_evidence)}"
        returned_evidence = _step_evidence(result, step_key=evidence_key)
        checkpoint_evidence = tuple(
            item for item in job.step_evidence if item.step_key != evidence_key
        ) + (returned_evidence,)
        checkpoint = replace(
            job,
            status="failed",
            spent_usd=job.spent_usd + actual_cents / 100,
            spawn_ids=checkpoint_spawn_ids,
            notes=(
                (job.notes + " | " if job.notes else "")
                + "paid_step_checkpoint_pending_ledger_settlement"
            ),
            returned_step_keys=(
                job.returned_step_keys
                if step_identity is None or step_identity in job.returned_step_keys
                else (*job.returned_step_keys, step_identity)
            ),
            step_evidence=checkpoint_evidence,
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
        guard()
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
        guard()
        put_job_state(failed, store=store)
        raise

    guard()
    job = replace(
        job,
        spent_usd=balance.spent_cents / 100,
        step_evidence=(
            job.step_evidence
            if returned_evidence is None
            else tuple(
                item
                for item in job.step_evidence
                if item.step_key != returned_evidence.step_key
            )
            + (returned_evidence,)
        ),
        completed_step_keys=(
            job.completed_step_keys
            if step_identity is None or step_identity in job.completed_step_keys
            else (*job.completed_step_keys, step_identity)
        ),
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
            guard()
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
        guard()
        put_job_state(callback_pending, store=store)
        try:
            on_spawn(intended_job, result)
        except BaseException:
            failed = replace(
                callback_pending,
                notes=(callback_pending.notes + " | on_spawn_failed_after_durable_checkpoint"),
            )
            guard()
            put_job_state(failed, store=store)
            raise
        guard()
        return put_job_state(intended_job, store=store)
    guard()
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
