"""Worker integration tests for the single durable budget authority."""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.midnight_oil.budget_ledger import (  # noqa: E402
    BudgetLedger,
    UnknownCallOutcome,
)
from substrate.midnight_oil.job import (  # noqa: E402
    InMemoryJobStore,
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
    return approve_job(job.job_id, ceiling, store=store, force_below=True)


def _balance(store: InMemoryJobStore, job_id: str):
    return BudgetLedger(store.budget_db_path()).balance(job_id)


def test_hold_is_durable_before_dispatch_and_settles_actual():
    store = InMemoryJobStore()
    job = _approved(store)
    seen: list[tuple[int, int]] = []

    def step(_job):
        balance = _balance(store, job.job_id)
        seen.append((balance.held_cents, balance.spent_cents))
        return WorkerStepResult(spent_usd=0.30, done=True)

    out = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=step,
        project_fn=lambda _job: 0.40,
        clock=FakeClock(),
    )
    assert seen == [(40, 0)]
    assert out.status == "complete"
    assert out.spent_usd == 0.30
    assert _balance(store, job.job_id).held_cents == 0


def test_unaffordable_projection_never_dispatches():
    store = InMemoryJobStore()
    job = _approved(store)
    calls = 0

    def step(_job):
        nonlocal calls
        calls += 1
        return WorkerStepResult(spent_usd=0.01)

    out = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=step,
        project_fn=lambda _job: 1.01,
        clock=FakeClock(),
    )
    assert calls == 0
    assert out.status == "budget_halted"
    assert _balance(store, job.job_id).spent_cents == 0


def test_restart_reads_spend_from_ledger_not_stale_job_row():
    store = InMemoryJobStore()
    job = _approved(store)
    ledger = BudgetLedger(store.budget_db_path())
    ledger.ensure_schema()
    ledger.reserve(job.job_id, 100, {"research": 100})
    ledger.debit(job.job_id, 65, role="research")
    row = store.get_job(job.job_id)
    assert row is not None
    row["spent_usd"] = 0.0
    store.put_job(row)

    out = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=lambda _job: WorkerStepResult(spent_usd=0.01),
        project_fn=lambda _job: 0.36,
        clock=FakeClock(),
    )
    assert out.status == "budget_halted"
    assert out.spent_usd == 0.65


def test_restart_with_open_ledger_hold_fails_without_redispatch():
    store = InMemoryJobStore()
    job = _approved(store)
    ledger = BudgetLedger(store.budget_db_path())
    ledger.ensure_schema()
    ledger.reserve(job.job_id, 100, {"research": 100})
    ledger.reserve_call(job.job_id, "research", 40)
    called = False

    def step(_job):
        nonlocal called
        called = True
        return WorkerStepResult(spent_usd=0.01)

    out = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=step,
        project_fn=lambda _job: 0.01,
        clock=FakeClock(),
    )
    assert called is False
    assert out.status == "failed"
    assert "unsettled_reservation" in out.notes
    assert ledger.balance(job.job_id).held_cents == 40


def test_unknown_provider_outcome_retains_projection_before_typed_reraise():
    store = InMemoryJobStore()
    job = _approved(store)

    def timeout(_job):
        raise TimeoutError("provider billed, response lost")

    with pytest.raises(UnknownCallOutcome) as caught:
        run_worker_iteration(
            job.job_id,
            store=store,
            step_fn=timeout,
            project_fn=lambda _job: 0.40,
            clock=FakeClock(),
        )
    assert isinstance(caught.value.provider_error, TimeoutError)
    row = store.get_job(job.job_id)
    assert row is not None
    assert row["status"] == "failed"
    assert row["spent_usd"] == 0.0
    assert _balance(store, job.job_id).spent_cents == 0
    assert _balance(store, job.job_id).held_cents == 40


def test_base_exception_retains_open_hold_without_false_charge_claim():
    store = InMemoryJobStore()
    job = _approved(store)

    class ProcessExit(BaseException):
        pass

    with pytest.raises(ProcessExit):
        run_worker_iteration(
            job.job_id,
            store=store,
            step_fn=lambda _job: (_ for _ in ()).throw(ProcessExit()),
            project_fn=lambda _job: 0.40,
            clock=FakeClock(),
        )
    row = store.get_job(job.job_id)
    assert row is not None
    assert row["status"] == "failed"
    assert "open hold 40 cents retained" in row["notes"]
    assert "charge 40 cents recorded" not in row["notes"]
    balance = _balance(store, job.job_id)
    assert balance.held_cents == 40
    assert balance.spent_cents == 0


def test_subcent_projection_and_actual_round_up():
    store = InMemoryJobStore()
    job = _approved(store)
    out = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=lambda _job: WorkerStepResult(spent_usd=0.0001, done=True),
        project_fn=lambda _job: 0.0001,
        clock=FakeClock(),
    )
    assert out.spent_usd == 0.01
    assert _balance(store, job.job_id).spent_cents == 1


def test_approval_rounds_down_and_cannot_expand_operator_limit():
    store = InMemoryJobStore()
    job = _approved(store, ceiling=1.009)
    run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=lambda _job: WorkerStepResult(spent_usd=1.0, done=True),
        project_fn=lambda _job: 1.0,
        clock=FakeClock(),
    )
    balance = _balance(store, job.job_id)
    assert balance.ceiling_cents == 100
    assert balance.spent_cents == 100


@pytest.mark.parametrize("bad", [0.0, -0.01, float("nan"), float("inf")])
def test_nonpositive_or_nonfinite_projection_never_dispatches(bad: float):
    store = InMemoryJobStore()
    job = _approved(store)
    called = False

    def step(_job):
        nonlocal called
        called = True
        return WorkerStepResult(spent_usd=0.0)

    with pytest.raises(ValueError, match="project_fn"):
        run_worker_iteration(
            job.job_id,
            store=store,
            step_fn=step,
            project_fn=lambda _job: bad,
            clock=FakeClock(),
        )
    assert called is False


def test_overrun_records_true_spend_and_fails_job():
    store = InMemoryJobStore()
    job = _approved(store)
    out = run_worker_iteration(
        job.job_id,
        store=store,
        step_fn=lambda _job: WorkerStepResult(
            spent_usd=0.90, spawn_id="spn_rejected_overrun"
        ),
        project_fn=lambda _job: 0.20,
        clock=FakeClock(),
    )
    assert out.status == "failed"
    assert out.spent_usd == 0.90
    assert "spn_rejected_overrun" not in out.spawn_ids
    # Projection overrun is auditable even when total spend remains below cap.
    import duckdb

    con = duckdb.connect(store.budget_db_path(), read_only=True)
    try:
        assert con.execute(
            "SELECT count(*) FROM midnight_oil_spend_ledger "
            "WHERE run_id = ? AND event = 'overshoot'",
            [job.job_id],
        ).fetchone() == (1,)
    finally:
        con.close()
