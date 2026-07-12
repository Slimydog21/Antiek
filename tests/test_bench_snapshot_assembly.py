"""Tests for the bench snapshot assembler (ask #11 glue)."""

from __future__ import annotations

import pytest

from substrate.antiek_bench.snapshot_assembly import (
    RunView,
    SnapshotAssemblyError,
    WeeklyBenchSnapshot,
    assemble_weekly_snapshot,
)


def _v(task, model, score, n=1) -> RunView:
    return RunView(task_id=task, model_id=model, score=score, n_runs=n)


# --------------------------------------------------------------------------- #
# Invariant #1 — mean from completed runs only; pending counted separately.
# --------------------------------------------------------------------------- #
def test_mean_excludes_pending_runs():
    snap = assemble_weekly_snapshot(
        week_id="W01",
        generated_at_label="t0",
        run_views=[
            _v("exact-01", "model-a", 0.8),
            _v("exact-01", "model-a", None),  # pending
        ],
    )
    fam = snap.task_families[0]
    score = [m for m in fam.models if m.model_id == "model-a"][0]
    assert score.mean_score == pytest.approx(0.8)  # NOT 0.4 (None not averaged as 0)
    assert score.completed_runs == 1
    assert score.pending_runs == 1


def test_multiple_completed_runs_averaged():
    snap = assemble_weekly_snapshot(
        week_id="W01",
        generated_at_label="t0",
        run_views=[
            _v("exact-01", "model-a", 0.6),
            _v("exact-01", "model-a", 0.8),
        ],
    )
    score = snap.task_families[0].models[0]
    assert score.mean_score == pytest.approx(0.7)
    assert score.completed_runs == 2


# --------------------------------------------------------------------------- #
# Invariant #2 — zero completed runs → mean_score None (never fabricated 0).
# --------------------------------------------------------------------------- #
def test_zero_completed_runs_yields_none_mean():
    snap = assemble_weekly_snapshot(
        week_id="W01",
        generated_at_label="t0",
        run_views=[_v("exact-01", "model-a", None)],
    )
    score = snap.task_families[0].models[0]
    assert score.mean_score is None
    assert score.completed_runs == 0
    assert score.pending_runs == 1
    assert "bench-unverified" in " ".join(snap.honesty_notes)


# --------------------------------------------------------------------------- #
# Invariant #3 — incomplete flag is OR of all families; override AND-ed (never relaxed).
# --------------------------------------------------------------------------- #
def test_incomplete_flag_when_any_pending():
    snap = assemble_weekly_snapshot(
        week_id="W01",
        generated_at_label="t0",
        run_views=[
            _v("exact-01", "model-a", 0.8),
            _v("rubric-01", "model-b", None),
        ],
        family_resolver=lambda t: "exact" if t.startswith("exact") else "rubric",
    )
    assert snap.incomplete is True
    assert any("pending" in n for n in snap.honesty_notes)


def test_complete_flag_when_all_scored():
    snap = assemble_weekly_snapshot(
        week_id="W01",
        generated_at_label="t0",
        run_views=[_v("exact-01", "model-a", 0.8)],
    )
    assert snap.incomplete is False


def test_incomplete_override_never_relaxed():
    # all scored (would be complete) but override marks incomplete -> stays incomplete
    snap = assemble_weekly_snapshot(
        week_id="W01",
        generated_at_label="t0",
        run_views=[_v("exact-01", "model-a", 0.8)],
        incomplete_override=True,
    )
    assert snap.incomplete is True


def test_complete_override_cannot_relax_pending():
    # has pending (incomplete) but override tries False -> still incomplete
    snap = assemble_weekly_snapshot(
        week_id="W01",
        generated_at_label="t0",
        run_views=[_v("exact-01", "model-a", None)],
        incomplete_override=False,
    )
    assert snap.incomplete is True


# --------------------------------------------------------------------------- #
# Invariant #4 — overall ranking aggregates completed family-means; no fabricated breadth penalty.
# --------------------------------------------------------------------------- #
def test_overall_ranking_aggregates_family_means():
    snap = assemble_weekly_snapshot(
        week_id="W01",
        generated_at_label="t0",
        run_views=[
            _v("exact-01", "model-a", 0.8),
            _v("rubric-01", "model-a", 0.6),  # model-a in 2 families -> mean 0.7
            _v("exact-01", "model-b", 0.9),   # model-b in 1 family -> 0.9
        ],
        family_resolver=lambda t: "exact" if t.startswith("exact") else "rubric",
    )
    overall = {m.model_id: m.mean_score for m in snap.overall_ranking}
    assert overall["model-a"] == pytest.approx(0.7)
    assert overall["model-b"] == pytest.approx(0.9)


def test_model_missing_from_family_not_penalized_in_overall():
    # model-a scored only in exact (0.8); model-b scored only in rubric (0.9).
    # Neither is penalized for the family they're absent from.
    snap = assemble_weekly_snapshot(
        week_id="W01",
        generated_at_label="t0",
        run_views=[
            _v("exact-01", "model-a", 0.8),
            _v("rubric-01", "model-b", 0.9),
        ],
        family_resolver=lambda t: "exact" if t.startswith("exact") else "rubric",
    )
    overall = {m.model_id: m.mean_score for m in snap.overall_ranking}
    assert overall["model-a"] == pytest.approx(0.8)  # not dragged by missing rubric
    assert overall["model-b"] == pytest.approx(0.9)


def test_model_with_no_completed_runs_excluded_from_overall():
    snap = assemble_weekly_snapshot(
        week_id="W01",
        generated_at_label="t0",
        run_views=[
            _v("exact-01", "model-a", 0.8),
            _v("exact-01", "model-b", None),  # no completed runs
        ],
    )
    overall_ids = {m.model_id for m in snap.overall_ranking}
    assert "model-a" in overall_ids
    assert "model-b" not in overall_ids


# --------------------------------------------------------------------------- #
# Invariant #5 — ranking stable (ties preserve input order).
# --------------------------------------------------------------------------- #
def test_ranking_within_family_completed_desc_none_last():
    snap = assemble_weekly_snapshot(
        week_id="W01",
        generated_at_label="t0",
        run_views=[
            _v("t", "low", 0.4),
            _v("t", "high", 0.9),
            _v("t", "mid", 0.6),
            _v("t", "pending", None),
        ],
    )
    order = [m.model_id for m in snap.task_families[0].models]
    assert order == ["high", "mid", "low", "pending"]


def test_ties_preserve_input_order():
    snap = assemble_weekly_snapshot(
        week_id="W01",
        generated_at_label="t0",
        run_views=[
            _v("t", "first", 0.8),
            _v("t", "second", 0.8),
            _v("t", "third", 0.8),
        ],
    )
    order = [m.model_id for m in snap.task_families[0].models]
    assert order == ["first", "second", "third"]  # stable, no arbitrary reorder


# --------------------------------------------------------------------------- #
# Family resolver injection + fail-closed.
# --------------------------------------------------------------------------- #
def test_family_resolver_groups_tasks():
    snap = assemble_weekly_snapshot(
        week_id="W01",
        generated_at_label="t0",
        run_views=[
            _v("exact-01", "m", 0.8),
            _v("exact-02", "m", 0.6),  # same family, different task
        ],
        family_resolver=lambda t: t.rsplit("-", 1)[0],  # exact-01 -> exact
    )
    assert len(snap.task_families) == 1
    assert snap.task_families[0].task_family == "exact"
    assert snap.task_families[0].models[0].mean_score == pytest.approx(0.7)


def test_empty_family_resolver_result_rejected():
    with pytest.raises(SnapshotAssemblyError, match="empty family"):
        assemble_weekly_snapshot(
            week_id="W01",
            generated_at_label="t0",
            run_views=[_v("t", "m", 0.8)],
            family_resolver=lambda t: "",
        )


def test_resolver_exception_wrapped():
    def bad(_):
        raise RuntimeError("boom")

    with pytest.raises(SnapshotAssemblyError, match="family_resolver raised"):
        assemble_weekly_snapshot(
            week_id="W01",
            generated_at_label="t0",
            run_views=[_v("t", "m", 0.8)],
            family_resolver=bad,
        )


def test_blank_week_id_rejected():
    with pytest.raises(SnapshotAssemblyError, match="week_id"):
        assemble_weekly_snapshot(week_id="  ", generated_at_label="t0", run_views=[])


# --------------------------------------------------------------------------- #
# Empty input + provenance.
# --------------------------------------------------------------------------- #
def test_empty_views_yields_empty_snapshot():
    snap = assemble_weekly_snapshot(
        week_id="W01", generated_at_label="t0", run_views=[]
    )
    assert snap.task_families == ()
    assert snap.overall_ranking == ()
    assert snap.source_record_count == 0
    assert snap.incomplete is False


def test_source_record_count_is_view_count():
    snap = assemble_weekly_snapshot(
        week_id="W01",
        generated_at_label="t0",
        run_views=[_v("t", "m", 0.8), _v("t", "m2", 0.6)],
    )
    assert snap.source_record_count == 2


# --------------------------------------------------------------------------- #
# Determinism + purity.
# --------------------------------------------------------------------------- #
def test_deterministic_snapshot():
    args = dict(
        week_id="W01",
        generated_at_label="t0",
        run_views=[_v("t", "a", 0.8), _v("t", "b", 0.6)],
    )
    s1 = assemble_weekly_snapshot(**args)
    s2 = assemble_weekly_snapshot(**args)
    assert s1 == s2


def test_purity_no_io_imports():
    import inspect

    from substrate.antiek_bench import snapshot_assembly as mod

    src = inspect.getsource(mod)
    for forbidden in ("import os", "import time", "import asyncio", "open(", "datetime.now", "requests"):
        assert forbidden not in src, f"purity breach: {forbidden!r}"


# --------------------------------------------------------------------------- #
# Boundary types frozen.
# --------------------------------------------------------------------------- #
def test_boundary_types_frozen():
    import dataclasses

    from substrate.antiek_bench.snapshot_assembly import (
        ModelScore,
        RunView,
        TaskFamilyResult,
    )

    for cls in (RunView, ModelScore, TaskFamilyResult, WeeklyBenchSnapshot):
        assert dataclasses.is_dataclass(cls)
