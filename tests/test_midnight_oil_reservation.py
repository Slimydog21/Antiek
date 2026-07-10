from dataclasses import replace

import pytest

from substrate.midnight_oil.job import (
    InMemoryJobStore,
    _job_from_row,
    _job_to_row,
    approve_job,
    create_job,
    put_job_state,
)
from substrate.midnight_oil.reservation import project_step_cost, reserve_step
from substrate.midnight_oil.worker import FakeClock, WorkerStepResult, run_worker_iteration


def approved(*, ceiling: float = 1.0, tier: str = "deep"):
    store = InMemoryJobStore()
    job = create_job(["goal"], 60, store=store, research_tier=tier)
    return store, approve_job(job.job_id, ceiling, store=store, force_below=True)


def test_preflight_halt_never_calls_step():
    store, job = approved(ceiling=0.1)
    calls = []

    def step(current):
        calls.append(current)
        return WorkerStepResult(spent_usd=0.1)

    result = run_worker_iteration(
        job.job_id, store=store, step_fn=step, clock=FakeClock(), project_fn=lambda _: 0.2
    )
    assert result.status == "budget_halted"
    assert calls == []


def test_reservation_is_persisted_before_step_raises():
    store, job = approved()

    def step(current):
        assert store.get_job(current.job_id)["reserved_usd"] == pytest.approx(0.2)
        raise RuntimeError("crash")

    with pytest.raises(RuntimeError, match="crash"):
        run_worker_iteration(
            job.job_id, store=store, step_fn=step, clock=FakeClock(), project_fn=lambda _: 0.2
        )


def test_settle_releases_projection_delta():
    store, job = approved()
    result = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=lambda _: WorkerStepResult(spent_usd=0.1),
        clock=FakeClock(),
        project_fn=lambda _: 0.2,
    )
    assert result.spent_usd == pytest.approx(0.1)
    assert result.reserved_usd == 0.0


def test_over_projection_records_full_actual_then_next_iteration_halts():
    store, job = approved(ceiling=0.5)
    first = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=lambda _: WorkerStepResult(spent_usd=0.6),
        clock=FakeClock(),
        project_fn=lambda _: 0.2,
    )
    assert first.spent_usd == pytest.approx(0.6)
    assert "settle_over_projection" in first.notes
    calls = []
    second = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=lambda current: calls.append(current) or WorkerStepResult(0.1),
        clock=FakeClock(),
    )
    assert second.status == "budget_halted"
    assert calls == []


def test_orphaned_reservation_is_absorbed_not_released():
    store, job = approved(ceiling=0.5)
    put_job_state(replace(job, reserved_usd=0.5), store=store)
    result = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=lambda _: pytest.fail("step must not run"),
        clock=FakeClock(),
    )
    assert result.spent_usd == pytest.approx(0.5)
    assert result.reserved_usd == 0.0
    assert "orphaned_reservation_absorbed" in result.notes


def test_orphan_absorbed_even_when_recovery_times_out():
    # Crash mid-step, then recover AFTER the duration expired: the terminal
    # timed_out job must still charge the orphaned reservation conservatively.
    store, job = approved(ceiling=1.0)
    put_job_state(
        replace(job, status="running", started_at_ms=0, reserved_usd=0.3),
        store=store,
    )
    clock = FakeClock()
    clock.advance(job.duration_minutes * 60_000 + 1)
    result = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=lambda _: pytest.fail("step must not run"),
        clock=clock,
    )
    assert result.status == "timed_out"
    assert result.spent_usd == pytest.approx(0.3)
    assert result.reserved_usd == 0.0
    assert "orphaned_reservation_absorbed" in result.notes


def test_legacy_row_defaults_reservation_to_zero():
    _, job = approved()
    row = _job_to_row(job)
    del row["reserved_usd"]
    restored = _job_from_row(row)
    assert restored.reserved_usd == 0.0
    assert _job_from_row(_job_to_row(restored)).reserved_usd == 0.0


def test_reserve_step_rejects_nonpositive_projection():
    store, job = approved()
    for bad in (0.0, -0.1):
        with pytest.raises(ValueError, match="must be positive"):
            reserve_step(job, bad, store=store)


def test_recovery_absorbs_orphan_then_continues_when_budget_remains():
    # Crash mid-step with budget left: recovery charges the orphan AND the
    # run keeps working — absorption is accounting, not a death sentence.
    store, job = approved(ceiling=1.0)
    put_job_state(
        replace(job, status="running", started_at_ms=0, reserved_usd=0.1),
        store=store,
    )
    result = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=lambda _: WorkerStepResult(spent_usd=0.1),
        clock=FakeClock(),
        project_fn=lambda _: 0.2,
    )
    assert result.status == "running"
    assert "orphaned_reservation_absorbed" in result.notes
    assert result.spent_usd == pytest.approx(0.2)  # 0.1 orphan + 0.1 actual
    assert result.reserved_usd == 0.0


def test_projection_uses_tier_fanout_and_unknown_model_fallback():
    _, deep = approved(tier="deep")
    fast = replace(deep, research_tier="fast")
    wrestle = replace(deep, research_tier="wrestle")
    assert project_step_cost(wrestle) > project_step_cost(deep) > project_step_cost(fast)
    assert project_step_cost(replace(deep, fanout_depth=6)) == pytest.approx(
        project_step_cost(deep) * 2
    )
    assert project_step_cost(replace(deep, model_id="unknown")) > 0
