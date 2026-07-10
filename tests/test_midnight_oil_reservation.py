"""Reserve-before-spend budget enforcement for the Midnight Oil worker.

The approved price ceiling is a pre-commitment, not an accounting line:
a step's projected max cost is durably reserved BEFORE the step runs, an
unaffordable step never executes, and money that leaves anyway (projection
overrun) is recorded truthfully instead of being discarded.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.midnight_oil.job import (  # noqa: E402
    InMemoryJobStore,
    _job_from_row,
    approve_job,
    create_job,
)
from substrate.midnight_oil.worker import (  # noqa: E402
    FakeClock,
    WorkerStepResult,
    run_worker_iteration,
)


def _approved(store: InMemoryJobStore, ceiling: float = 1.0):
    job = create_job(["g1", "g2"], 60, store=store, model_id="default")
    approve_job(job.job_id, ceiling, store=store, force_below=True)
    return job


def test_reservation_is_persisted_before_step_runs():
    store = InMemoryJobStore()
    job = _approved(store)
    seen: list[float] = []

    def step(j):
        row = store.get_job(j.job_id)
        assert row is not None
        seen.append(float(row["reserved_usd"]))
        return WorkerStepResult(spent_usd=0.3, done=True)

    out = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=step,
        project_fn=lambda _j: 0.4,
        clock=FakeClock(0),
    )
    # The store row carried the reservation while the step was in flight...
    assert seen == [0.4]
    # ...and settlement cleared it, recording actual spend.
    assert out.reserved_usd is None
    assert out.spent_usd == pytest.approx(0.3)
    assert out.status == "complete"


def test_unaffordable_projection_prevents_step_execution():
    store = InMemoryJobStore()
    job = _approved(store, ceiling=1.0)
    calls = {"n": 0}

    def step(_j):
        calls["n"] += 1
        return WorkerStepResult(spent_usd=0.5, done=False)

    out = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=step,
        project_fn=lambda _j: 1.5,
        clock=FakeClock(0),
    )
    assert calls["n"] == 0
    assert out.status == "budget_halted"
    assert out.spent_usd == 0.0
    assert out.reserved_usd is None
    assert "budget_halt_preflight" in out.notes


def test_projection_exactly_filling_ceiling_is_allowed():
    store = InMemoryJobStore()
    job = _approved(store, ceiling=1.0)

    out = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=lambda _j: WorkerStepResult(spent_usd=1.0, done=True),
        project_fn=lambda _j: 1.0,
        clock=FakeClock(0),
    )
    assert out.status == "complete"
    assert out.spent_usd == pytest.approx(1.0)


def test_overrun_records_true_spend_and_fails():
    store = InMemoryJobStore()
    job = _approved(store, ceiling=1.0)

    out = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=lambda _j: WorkerStepResult(spent_usd=0.9, done=False),
        project_fn=lambda _j: 0.2,
        clock=FakeClock(0),
    )
    assert out.status == "failed"
    # The money left; the ledger says so — never "keep prior spend".
    assert out.spent_usd == pytest.approx(0.9)
    assert out.reserved_usd is None
    assert "reservation_overrun" in out.notes


def test_dangling_reservation_fails_closed():
    store = InMemoryJobStore()
    job = _approved(store)
    # Simulate a crash between reserve and settle: row carries a reservation.
    row = store.get_job(job.job_id)
    assert row is not None
    row["reserved_usd"] = 0.25
    row["status"] = "running"
    row["started_at_ms"] = 0
    store.put_job(row)
    calls = {"n": 0}

    def step(_j):
        calls["n"] += 1
        return WorkerStepResult(spent_usd=0.01, done=True)

    out = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=step,
        project_fn=lambda _j: 0.01,
        clock=FakeClock(1),
    )
    assert calls["n"] == 0
    assert out.status == "failed"
    assert "unsettled_reservation" in out.notes


def test_invalid_projection_raises():
    store = InMemoryJobStore()
    job = _approved(store)
    for bad in (float("nan"), float("inf"), -0.01):
        with pytest.raises(ValueError, match="project_fn"):
            run_worker_iteration(
                job.job_id,
                store=store,
                step_fn=lambda _j: WorkerStepResult(spent_usd=0.0, done=True),
                project_fn=lambda _j, b=bad: b,
                clock=FakeClock(0),
            )


def test_invalid_reported_spend_keeps_reservation_for_audit():
    store = InMemoryJobStore()
    job = _approved(store)

    out = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=lambda _j: WorkerStepResult(spent_usd=float("nan"), done=True),
        project_fn=lambda _j: 0.3,
        clock=FakeClock(0),
    )
    assert out.status == "failed"
    assert out.reserved_usd == pytest.approx(0.3)
    assert "invalid_step_spend" in out.notes


def test_legacy_row_without_reserved_usd_loads_clean():
    store = InMemoryJobStore()
    job = _approved(store)
    row = store.get_job(job.job_id)
    assert row is not None
    row.pop("reserved_usd", None)
    row.pop("reservation_token", None)
    loaded = _job_from_row(row)
    assert loaded.reserved_usd is None
    assert loaded.reservation_token is None


def test_zero_projection_still_marks_step_in_flight():
    """A crash during a zero-projected step must remain detectable."""
    store = InMemoryJobStore()
    job = _approved(store)
    seen: list[object] = []

    def step(j):
        row = store.get_job(j.job_id)
        assert row is not None
        seen.append(row["reserved_usd"])
        return WorkerStepResult(spent_usd=0.0, done=True)

    out = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=step,
        project_fn=lambda _j: 0.0,
        clock=FakeClock(0),
    )
    # In-flight marker was 0.0 (not None/absent) while the step ran.
    assert seen == [0.0]
    assert out.reserved_usd is None
    assert out.status == "complete"


def test_zero_reservation_dangling_fails_closed():
    store = InMemoryJobStore()
    job = _approved(store)
    row = store.get_job(job.job_id)
    assert row is not None
    row["reserved_usd"] = 0.0  # crashed zero-projection step
    row["status"] = "running"
    row["started_at_ms"] = 0
    store.put_job(row)

    out = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=lambda _j: WorkerStepResult(spent_usd=0.0, done=True),
        project_fn=lambda _j: 0.0,
        clock=FakeClock(1),
    )
    assert out.status == "failed"
    assert "unsettled_reservation" in out.notes


def test_lost_settlement_write_fails_closed_on_next_iteration():
    """If the settle write never lands, the reservation stays and the next
    iteration refuses to run instead of double-spending."""
    store = InMemoryJobStore()
    job = _approved(store)
    real_put = store.put_job
    state = {"drop_next_put": False}

    def flaky_put(row):
        if state["drop_next_put"]:
            state["drop_next_put"] = False
            return  # settlement write silently lost
        real_put(row)

    store.put_job = flaky_put  # type: ignore[method-assign]

    def step(_j):
        state["drop_next_put"] = True  # lose the write AFTER this step
        return WorkerStepResult(spent_usd=0.2, done=True)

    run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=step,
        project_fn=lambda _j: 0.2,
        clock=FakeClock(0),
    )
    # The settle write was dropped; the durable row still holds the
    # reservation, so the next iteration must fail closed.
    out = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=lambda _j: WorkerStepResult(spent_usd=0.1, done=True),
        project_fn=lambda _j: 0.1,
        clock=FakeClock(1),
    )
    assert out.status == "failed"
    assert "unsettled_reservation" in out.notes


def test_interleaved_concurrent_worker_detected_before_step():
    store = InMemoryJobStore()
    job = _approved(store)
    real_put = store.put_job

    def clobbering_put(row):
        real_put(row)
        if row.get("reservation_token"):
            stomped = dict(row)
            stomped["reservation_token"] = "other-worker"
            real_put(stomped)  # a second worker overwrites the claim

    store.put_job = clobbering_put  # type: ignore[method-assign]
    calls = {"n": 0}

    def step(_j):
        calls["n"] += 1
        return WorkerStepResult(spent_usd=0.1, done=True)

    with pytest.raises(RuntimeError, match="interference detected"):
        run_worker_iteration(
            job.job_id,
            store=store,
            step_fn=step,
            project_fn=lambda _j: 0.1,
            clock=FakeClock(0),
        )
    assert calls["n"] == 0  # the step never ran under a stolen claim


def test_settled_spend_never_exceeds_ceiling_without_epsilon():
    """Preflight is epsilon-free: a projection that exceeds the ceiling by
    any margin, however tiny, is refused before the step runs."""
    store = InMemoryJobStore()
    job = _approved(store, ceiling=1.0)
    calls = {"n": 0}

    def step(_j):
        calls["n"] += 1
        return WorkerStepResult(spent_usd=1.0, done=True)

    out = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=step,
        project_fn=lambda _j: 1.0 + 1e-13,
        clock=FakeClock(0),
    )
    assert calls["n"] == 0
    assert out.status == "budget_halted"
    assert out.spent_usd == 0.0


def test_invalid_spend_then_retry_stays_failed_and_keeps_reservation():
    """After invalid_step_spend the job is terminal; a retry must not run
    another step or clear the audit reservation."""
    store = InMemoryJobStore()
    job = _approved(store)

    first = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=lambda _j: WorkerStepResult(spent_usd=float("-1.0"), done=True),
        project_fn=lambda _j: 0.3,
        clock=FakeClock(0),
    )
    assert first.status == "failed"
    assert first.reserved_usd == pytest.approx(0.3)
    calls = {"n": 0}

    def step(_j):
        calls["n"] += 1
        return WorkerStepResult(spent_usd=0.01, done=True)

    retry = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=step,
        project_fn=lambda _j: 0.01,
        clock=FakeClock(1),
    )
    assert calls["n"] == 0
    assert retry.status == "failed"
    assert retry.reserved_usd == pytest.approx(0.3)


def test_token_preserving_interference_detected_before_step():
    """Even interference that keeps the token but mutates budget fields
    must stop the iteration before the step runs."""
    store = InMemoryJobStore()
    job = _approved(store, ceiling=1.0)
    real_put = store.put_job

    def sneaky_put(row):
        real_put(row)
        if row.get("reservation_token"):
            mutated = dict(row)
            mutated["spent_usd"] = 0.99  # token intact, budget state swapped
            real_put(mutated)

    store.put_job = sneaky_put  # type: ignore[method-assign]
    calls = {"n": 0}

    def step(_j):
        calls["n"] += 1
        return WorkerStepResult(spent_usd=0.5, done=True)

    with pytest.raises(RuntimeError, match="interference detected"):
        run_worker_iteration(
            job.job_id,
            store=store,
            step_fn=step,
            project_fn=lambda _j: 0.5,
            clock=FakeClock(0),
        )
    assert calls["n"] == 0


def test_step_exception_persists_failed_with_reservation_before_raising():
    store = InMemoryJobStore()
    job = _approved(store)

    def exploding_step(_j):
        raise ConnectionError("provider hung up mid-call")

    with pytest.raises(ConnectionError):
        run_worker_iteration(
            job.job_id,
            store=store,
            step_fn=exploding_step,
            project_fn=lambda _j: 0.3,
            clock=FakeClock(0),
        )
    row = store.get_job(job.job_id)
    assert row is not None
    # The fail-closed outcome is durable even if nobody ever retries.
    assert row["status"] == "failed"
    assert row["reserved_usd"] == pytest.approx(0.3)
    assert "step_exception" in row["notes"]
