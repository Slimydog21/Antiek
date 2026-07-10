"""Real-path tests for Midnight Oil job/ceiling/approve/worker/deposit.

Drives shipped functions only. Injectable clock and step_fn — no network.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from substrate.engagement_spine import (  # noqa: E402
    FileEngagementStore,
    list_twin_notes,
)
from substrate.midnight_oil import (  # noqa: E402
    approve_job,
    create_job,
    deposit_job_results,
    get_job,
    recommend_price_ceiling,
    run_worker_iteration,
    run_worker_loop,
)
from substrate.midnight_oil.ceiling import (  # noqa: E402
    SAFETY_FACTOR,
    TOKENS_PER_MINUTE,
    ModelPricing,
)
from substrate.midnight_oil.job import InMemoryJobStore  # noqa: E402
from substrate.midnight_oil.worker import FakeClock, WorkerStepResult  # noqa: E402


def test_recommend_price_ceiling_hand_calculated():
    # 60 min, default rates 1+3 = 4 USD/1M, depth 3, safety 1.25, deep 1.0×
    # raw = 60 * 4000 * 4 / 1e6 * 3 * 1.25 * 1.0
    expected = round(
        60 * TOKENS_PER_MINUTE * 4.0 / 1_000_000.0 * 3 * SAFETY_FACTOR, 2
    )
    got = recommend_price_ceiling(60, model_id="default", fanout_depth=3)
    assert got == expected
    assert got == pytest.approx(3.6, abs=1e-6)


def test_recommend_price_ceiling_custom_pricing():
    pricing = ModelPricing("custom", input_usd_per_1m=2.0, output_usd_per_1m=2.0)
    # 30 * 4000 * 4 / 1e6 * 2 * 1.25 * 1.0 = 1.2
    got = recommend_price_ceiling(30, fanout_depth=2, pricing=pricing)
    assert got == pytest.approx(1.2, abs=1e-6)


def test_recommend_price_ceiling_scales_by_research_tier():
    """Residual (jl): fast 0.5×, deep 1.0×, wrestle 2.0× on same duration/model."""
    deep = recommend_price_ceiling(60, model_id="default", fanout_depth=3)
    assert deep == pytest.approx(3.6, abs=1e-6)
    fast = recommend_price_ceiling(
        60, model_id="default", fanout_depth=3, research_tier="fast"
    )
    wrestle = recommend_price_ceiling(
        60, model_id="default", fanout_depth=3, research_tier="wrestle"
    )
    assert fast == pytest.approx(1.8, abs=1e-6)
    assert wrestle == pytest.approx(7.2, abs=1e-6)
    assert fast < deep < wrestle


def test_recommend_rejects_zero_duration():
    with pytest.raises(ValueError, match="duration_minutes"):
        recommend_price_ceiling(0)


def test_create_job_requires_goals_and_returns_ceiling():
    store = InMemoryJobStore()
    with pytest.raises(ValueError, match="goal"):
        create_job([], 30, store=store)
    job = create_job(
        ["What is the state of retrieval-augmented generation?"],
        60,
        store=store,
        model_id="glm-5.2",
    )
    assert job.status == "awaiting_approval"
    assert job.recommended_price_ceiling_usd > 0
    assert job.approved_ceiling_usd is None
    assert job.job_id.startswith("moil_")
    assert "retrieval" in job.goals[0]
    # Default research tier is deep when omitted.
    assert job.research_tier == "deep"


def test_create_job_records_wrestle_research_tier(gs_residual=None):
    """Residual (gs): autonomous jobs store curated research_tier."""
    store = InMemoryJobStore()
    job = create_job(
        ["Multi-hop long-horizon synthesis"],
        90,
        store=store,
        model_id="glm-5.2",
        research_tier="wrestle",
    )
    assert job.research_tier == "wrestle"
    got = get_job(job.job_id, store=store)
    assert got is not None
    assert got.research_tier == "wrestle"
    # Unknown tiers normalize to deep (honest fallback).
    job2 = create_job(["x"], 10, store=store, research_tier="not-a-tier")
    assert job2.research_tier == "deep"


def test_create_job_wrestle_ceiling_higher_than_deep():
    """Residual (jl): create_job ceiling scales with research_tier."""
    store = InMemoryJobStore()
    deep = create_job(["q"], 60, store=store, model_id="default", research_tier="deep")
    wrestle = create_job(
        ["q2"], 60, store=store, model_id="default", research_tier="wrestle"
    )
    fast = create_job(["q3"], 60, store=store, model_id="default", research_tier="fast")
    assert deep.recommended_price_ceiling_usd == pytest.approx(3.6, abs=1e-6)
    assert wrestle.recommended_price_ceiling_usd == pytest.approx(7.2, abs=1e-6)
    assert fast.recommended_price_ceiling_usd == pytest.approx(1.8, abs=1e-6)


def test_approve_gate_requires_explicit_ceiling():
    store = InMemoryJobStore()
    job = create_job(["goal A"], 60, store=store, model_id="default")
    with pytest.raises(ValueError, match="below recommended"):
        approve_job(job.job_id, job.recommended_price_ceiling_usd * 0.5, store=store)
    approved = approve_job(
        job.job_id, job.recommended_price_ceiling_usd, store=store
    )
    assert approved.status == "approved"
    assert approved.approved_ceiling_usd == job.recommended_price_ceiling_usd


def test_approve_force_below_records_warning():
    store = InMemoryJobStore()
    job = create_job(["goal A"], 60, store=store)
    approved = approve_job(
        job.job_id,
        0.01,
        store=store,
        force_below=True,
    )
    assert approved.status == "approved"
    assert approved.force_below_recommended is True
    assert "force_below" in approved.notes


def test_worker_rejects_unapproved():
    store = InMemoryJobStore()
    job = create_job(["g"], 10, store=store)
    clock = FakeClock(0)

    def step(_j):
        return WorkerStepResult(spent_usd=0.1, done=True)

    with pytest.raises(ValueError, match="approve"):
        run_worker_iteration(
            job.job_id,
            store=store,
            step_fn=step,
            project_fn=lambda _j: 0.1,
            clock=clock,
        )


def test_worker_budget_hard_halt():
    """Reserve-before-spend: an unaffordable step is never executed."""
    store = InMemoryJobStore()
    job = create_job(["g1", "g2"], 60, store=store, model_id="default")
    # Approve a tight ceiling
    approve_job(job.job_id, 1.0, store=store, force_below=True)
    clock = FakeClock(0)
    calls = {"n": 0}

    def step(_j):
        calls["n"] += 1
        return WorkerStepResult(
            spent_usd=0.6,
            spawn_id=f"spn_fake_{calls['n']}",
            output_text="partial",
            insights=("i1",),
            questions=("q1",),
            done=False,
        )

    project = lambda _j: 0.6  # noqa: E731

    j1 = run_worker_iteration(
        job.job_id, store=store, step_fn=step, project_fn=project, clock=clock
    )
    assert j1.status == "running"
    assert j1.spent_usd == pytest.approx(0.6)
    from substrate.midnight_oil.budget_ledger import BudgetLedger

    assert BudgetLedger(store.budget_db_path()).balance(job.job_id).held_cents == 0
    # Second step projects 0.6 more → would exceed 1.0 → halted BEFORE the
    # step runs: no charge, no step execution.
    j2 = run_worker_iteration(
        job.job_id, store=store, step_fn=step, project_fn=project, clock=clock
    )
    assert j2.status == "budget_halted"
    assert j2.spent_usd == pytest.approx(0.6)
    assert calls["n"] == 1  # prevention: the unaffordable step never ran
    assert "budget_halt_preflight" in j2.notes


def test_worker_timeout_with_fake_clock():
    store = InMemoryJobStore()
    job = create_job(["g"], 1, store=store)  # 1 minute
    approve_job(job.job_id, job.recommended_price_ceiling_usd, store=store)
    clock = FakeClock(0)

    def step(_j):
        return WorkerStepResult(spent_usd=0.01, done=False)

    j = run_worker_loop(
        job.job_id,
        store=store,
        step_fn=step,
        project_fn=lambda _j: 0.01,
        clock=clock,
        max_steps=5,
        advance_ms_per_step=60_000,
    )
    assert j.status == "timed_out"
    assert j.spent_usd > 0


def test_deposit_html_and_twins_idempotent(tmp_path):
    job_store = InMemoryJobStore()
    eng = FileEngagementStore(tmp_path / "engagement")
    job = create_job(
        ["Compare vector indexes for RAG"],
        30,
        store=job_store,
        model_id="glm-5.2",
    )
    approve_job(job.job_id, job.recommended_price_ceiling_usd, store=job_store)
    # Mark complete so deposit is meaningful
    from dataclasses import replace

    from substrate.midnight_oil.job import get_job, put_job_state

    j = get_job(job.job_id, store=job_store)
    assert j is not None
    put_job_state(replace(j, status="complete"), store=job_store)

    steps = [
        WorkerStepResult(
            spent_usd=0.5,
            output_text="HNSW vs IVF: latency/recall tradeoffs.",
            insights=("HNSW dominates low-latency recall",),
            questions=("When does diskANN win?",),
        )
    ]
    d1 = deposit_job_results(
        job.job_id,
        job_store=job_store,
        engagement_store=eng,
        step_outputs=steps,
        draft_combined=True,
    )
    assert d1.twin_count >= 1
    assert d1.html
    assert "<" in d1.html
    assert "pdf" not in d1.html.lower() or "html" in d1.html.lower()
    assert "HNSW" in d1.html or "vector" in d1.html.lower() or "Midnight" in d1.html

    twins_before = list_twin_notes(d1.asset_id, store=eng)
    d2 = deposit_job_results(
        job.job_id,
        job_store=job_store,
        engagement_store=eng,
        step_outputs=steps,
        draft_combined=True,
    )
    twins_after = list_twin_notes(d2.asset_id, store=eng)
    # Idempotent note_ids — count must not grow unboundedly
    assert len(twins_after) == len(twins_before)
    assert d2.html


def test_end_to_end_create_approve_run_deposit(tmp_path):
    job_store = InMemoryJobStore()
    eng = FileEngagementStore(tmp_path / "e")
    job = create_job(["Study arxiv RAG surveys"], 5, store=job_store)
    rec = job.recommended_price_ceiling_usd
    approve_job(job.job_id, rec, store=job_store)
    clock = FakeClock(0)
    steps_log: list[WorkerStepResult] = []

    def step(_j):
        r = WorkerStepResult(
            spent_usd=0.05,
            spawn_id=None,
            output_text="Survey notes on dense retrieval.",
            insights=("Dense retrieval needs hybrid BM25",),
            questions=("How to evaluate long-context RAG?",),
            done=True,
        )
        steps_log.append(r)
        return r

    final = run_worker_loop(
        job.job_id,
        store=job_store,
        step_fn=step,
        project_fn=lambda _j: 0.05,
        clock=clock,
        max_steps=3,
        advance_ms_per_step=1_000,
    )
    assert final.status == "complete"
    deposit = deposit_job_results(
        job.job_id,
        job_store=job_store,
        engagement_store=eng,
        step_outputs=steps_log,
    )
    assert deposit.twin_count >= 1
    assert "html" in deposit.html.lower() or "<p" in deposit.html or "<div" in deposit.html


def test_worker_spawn_id_then_deposit_no_keyerror(tmp_path):
    """Regression: step_fn returns non-None spawn_id; deposit must materialize it.

    Prior bug: worker only recorded id on job; deposit complete_spawn KeyError'd
    (or merge KeyError'd) because engagement_spine had no row for that id.
    """
    job_store = InMemoryJobStore()
    eng = FileEngagementStore(tmp_path / "eng-worker-id")
    job = create_job(["Chase worker-id spawn path"], 10, store=job_store)
    approve_job(job.job_id, job.recommended_price_ceiling_usd, store=job_store)
    clock = FakeClock(0)
    worker_spawn = "spn_worker_fixed_regression_1"
    steps_log: list[WorkerStepResult] = []

    def step(_j):
        r = WorkerStepResult(
            spent_usd=0.2,
            spawn_id=worker_spawn,
            output_text="Worker analysis with pre-allocated spawn id.",
            insights=("Worker insight about retrieval",),
            questions=("What is the next open question?",),
            done=True,
        )
        steps_log.append(r)
        return r

    final = run_worker_loop(
        job.job_id,
        store=job_store,
        step_fn=step,
        project_fn=lambda _j: 0.2,
        clock=clock,
        max_steps=3,
        advance_ms_per_step=1_000,
    )
    assert final.status == "complete"
    assert final.spawn_ids == (worker_spawn,)

    # Deposit with step_outputs that carry the worker id (real integration path).
    deposit = deposit_job_results(
        job.job_id,
        job_store=job_store,
        engagement_store=eng,
        step_outputs=steps_log,
    )
    assert worker_spawn in deposit.spawn_ids
    assert deposit.twin_count >= 1
    assert deposit.html and len(deposit.html) > 40
    assert "Worker" in deposit.html or "retrieval" in deposit.html.lower() or "<" in deposit.html

    # Deposit with *only* job.spawn_ids (no step_outputs) also works.
    eng2 = FileEngagementStore(tmp_path / "eng-job-ids-only")
    deposit2 = deposit_job_results(
        job.job_id,
        job_store=job_store,
        engagement_store=eng2,
        step_outputs=(),
    )
    assert worker_spawn in deposit2.spawn_ids
    assert deposit2.twin_count >= 1


def test_worker_dedups_repeated_spawn_id():
    """Regression: same spawn_id returned every step must not duplicate on job."""
    store = InMemoryJobStore()
    job = create_job(["g"], 60, store=store)
    approve_job(job.job_id, job.recommended_price_ceiling_usd, store=store)
    clock = FakeClock(0)
    n = {"i": 0}

    def step(_j):
        n["i"] += 1
        return WorkerStepResult(
            spent_usd=0.01,
            spawn_id="spn_worker_1",
            done=(n["i"] >= 3),
        )

    final = run_worker_loop(
        job.job_id,
        store=store,
        step_fn=step,
        project_fn=lambda _j: 0.01,
        clock=clock,
        max_steps=5,
        advance_ms_per_step=1_000,
    )
    assert final.status == "complete"
    assert final.spawn_ids == ("spn_worker_1",)
    assert final.spawn_ids.count("spn_worker_1") == 1

def test_tier_multiplier_contract_matches_closed_set():
    """Residual (jx): substrate TIER_MULTIPLIER contract for TS parity (jv).

    Client RESEARCH_TIER_CEILING_MULTIPLIER must stay: fast 0.5, deep 1.0, wrestle 2.0.
    """
    from substrate.midnight_oil.ceiling import TIER_MULTIPLIER, tier_multiplier

    assert set(TIER_MULTIPLIER) == {"fast", "deep", "wrestle"}
    assert TIER_MULTIPLIER["fast"] == 0.5
    assert TIER_MULTIPLIER["deep"] == 1.0
    assert TIER_MULTIPLIER["wrestle"] == 2.0
    assert tier_multiplier("fast") == 0.5
    assert tier_multiplier("wrestle") == 2.0
    assert tier_multiplier(None) == 1.0
    assert tier_multiplier("turbo") == 1.0  # normalize → deep
