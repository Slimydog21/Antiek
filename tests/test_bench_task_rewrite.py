"""Tests for substrate/antiek_bench/task_rewrite.py — the self-rewriting structure loop."""

from __future__ import annotations

import pytest

from substrate.antiek_bench.task_rewrite import (
    PlatformSurfaceSignal,
    RewriteThresholds,
    TaskEvidence,
    TaskRewriteError,
    TaskRewriteProposal,
    can_retire,
    propose_task_rewrite,
)


def _ev(task_id: str, family: str, runs: int, success: int, scores=()) -> TaskEvidence:
    return TaskEvidence(
        task_id=task_id, family=family, n_runs=runs, n_success=success, scores=tuple(scores)
    )


# ---------------------------------------------------------------------------
# EMIT — new platform surface (never invented without a signal)
# ---------------------------------------------------------------------------


def test_emit_from_surface_signal():
    reg = {"reasoning::q1": "reasoning"}
    sig = PlatformSurfaceSignal(
        family="reading_comprehension",
        proposed_task_id="reading_comprehension::passage1",
        rationale="platform gained a reading mode",
    )
    p = propose_task_rewrite(registry_ids=reg, week_evidence=[], surface_signals=[sig])
    emits = [d for d in p.diffs if d.kind == "emit"]
    assert len(emits) == 1
    assert emits[0].task_id == "reading_comprehension::passage1"
    assert emits[0].family == "reading_comprehension"
    assert p.benchmark_version_to == 2


def test_emit_skipped_if_task_already_exists():
    reg = {"reasoning::q1": "reasoning"}
    sig = PlatformSurfaceSignal(
        family="reasoning", proposed_task_id="reasoning::q1", rationale="dup"
    )
    p = propose_task_rewrite(registry_ids=reg, week_evidence=[], surface_signals=[sig])
    assert not any(d.kind == "emit" for d in p.diffs)
    assert any("already in registry" in n for n in p.notes)


def test_no_emit_without_signal():
    reg = {"reasoning::q1": "reasoning"}
    p = propose_task_rewrite(
        registry_ids=reg,
        week_evidence=[_ev("reasoning::q1", "reasoning", 3, 1, (0.4, 0.5, 0.6))],
    )
    assert not any(d.kind == "emit" for d in p.diffs)


def test_emit_rejects_empty_family_or_id():
    with pytest.raises(TaskRewriteError):
        propose_task_rewrite(
            registry_ids={},
            week_evidence=[],
            surface_signals=[PlatformSurfaceSignal(family="", proposed_task_id="x::y", rationale="r")],
        )


# ---------------------------------------------------------------------------
# GRADUATE — saturated task (no longer differentiating; NOT silently dropped)
# ---------------------------------------------------------------------------


def test_graduate_when_saturated():
    reg = {"reasoning::q1": "reasoning"}
    ev = [_ev("reasoning::q1", "reasoning", 4, 4, (1.0, 1.0, 1.0, 1.0))]
    p = propose_task_rewrite(registry_ids=reg, week_evidence=ev)
    grads = [d for d in p.diffs if d.kind == "graduate"]
    assert len(grads) == 1
    assert "saturated" in grads[0].rationale


def test_graduate_threshold_respected():
    reg = {"reasoning::q1": "reasoning"}
    # 3/4 = 75% success, below default graduate threshold 1.0
    ev = [_ev("reasoning::q1", "reasoning", 4, 3, (0.75, 0.75, 0.75, 0.75))]
    p = propose_task_rewrite(registry_ids=reg, week_evidence=ev)
    assert not any(d.kind == "graduate" for d in p.diffs)


# ---------------------------------------------------------------------------
# REVISE — high variance (task ambiguous, not model bad)
# ---------------------------------------------------------------------------


def test_revise_on_high_variance():
    reg = {"code::fizz": "code"}
    ev = [_ev("code::fizz", "code", 4, 2, (0.0, 1.0, 0.0, 1.0))]
    p = propose_task_rewrite(registry_ids=reg, week_evidence=ev)
    rev = [d for d in p.diffs if d.kind == "revise"]
    assert len(rev) == 1
    assert "variance" in rev[0].rationale


def test_no_revise_when_low_variance():
    reg = {"code::fizz": "code"}
    ev = [_ev("code::fizz", "code", 4, 2, (0.5, 0.5, 0.5, 0.5))]
    p = propose_task_rewrite(registry_ids=reg, week_evidence=ev)
    assert not any(d.kind == "revise" for d in p.diffs)


# ---------------------------------------------------------------------------
# RETIRE — the proposer never retires (destruction = operator authority);
# can_retire is the coverage guard the authorized applier calls.
# ---------------------------------------------------------------------------


def test_proposer_never_emits_retire():
    # even fully-saturated multi-task families: proposer graduates, never retires
    reg = {"reasoning::q1": "reasoning", "reasoning::q2": "reasoning"}
    ev = [
        _ev("reasoning::q1", "reasoning", 4, 4, (1.0, 1.0, 1.0, 1.0)),
        _ev("reasoning::q2", "reasoning", 4, 4, (1.0, 1.0, 1.0, 1.0)),
    ]
    p = propose_task_rewrite(registry_ids=reg, week_evidence=ev)
    assert all(d.kind != "retire" for d in p.diffs)
    assert all(d.kind == "graduate" for d in p.diffs)


def test_can_retire_refuses_last_task_in_family():
    reg = {"reasoning::q1": "reasoning"}  # only task in family
    allowed, reason = can_retire("reasoning::q1", reg)
    assert allowed is False
    assert "last task" in reason


def test_can_retire_allows_when_family_has_coverage():
    reg = {"reasoning::q1": "reasoning", "reasoning::q2": "reasoning"}
    allowed, reason = can_retire("reasoning::q1", reg)
    assert allowed is True
    assert "retains 1" in reason


def test_can_retire_unknown_task():
    allowed, reason = can_retire("nope::1", {"r::1": "r"})
    assert allowed is False
    assert "not in registry" in reason


# ---------------------------------------------------------------------------
# No evidence → no diff (honest silence)
# ---------------------------------------------------------------------------


def test_no_diff_with_insufficient_runs():
    reg = {"reasoning::q1": "reasoning"}
    ev = [_ev("reasoning::q1", "reasoning", 2, 2, (1.0, 1.0))]  # < min_runs (3)
    p = propose_task_rewrite(registry_ids=reg, week_evidence=ev)
    assert not p.diffs
    assert any("insufficient evidence" in n for n in p.notes)


def test_no_diff_when_task_has_zero_runs():
    reg = {"reasoning::q1": "reasoning"}
    ev = [_ev("reasoning::q1", "reasoning", 0, 0)]
    p = propose_task_rewrite(registry_ids=reg, week_evidence=ev)
    assert not p.diffs


def test_no_diff_when_task_not_in_evidence():
    reg = {"reasoning::q1": "reasoning", "code::c1": "code"}
    p = propose_task_rewrite(registry_ids=reg, week_evidence=[])
    assert not p.diffs


# ---------------------------------------------------------------------------
# Version honesty — bumps iff non-empty, stable iff empty
# ---------------------------------------------------------------------------


def test_empty_proposal_keeps_version():
    reg = {"reasoning::q1": "reasoning"}
    p = propose_task_rewrite(registry_ids=reg, week_evidence=[])
    assert p.benchmark_version_from == 1
    assert p.benchmark_version_to == 1
    assert p.has_changes is False


def test_non_empty_proposal_bumps_version():
    reg = {"reasoning::q1": "reasoning"}
    sig = PlatformSurfaceSignal(
        family="writing", proposed_task_id="writing::w1", rationale="new"
    )
    p = propose_task_rewrite(registry_ids=reg, week_evidence=[], surface_signals=[sig])
    assert p.benchmark_version_to == 2


def test_version_carries_forward():
    p = propose_task_rewrite(
        registry_ids={"r::1": "r"},
        week_evidence=[],
        current_version=7,
    )
    assert p.benchmark_version_from == 7
    assert p.benchmark_version_to == 7


# ---------------------------------------------------------------------------
# impossible inputs rejected
# ---------------------------------------------------------------------------


def test_negative_runs_rejected():
    with pytest.raises(TaskRewriteError):
        propose_task_rewrite(
            registry_ids={"r::1": "r"},
            week_evidence=[_ev("r::1", "r", -1, 0)],
        )


def test_success_exceeds_runs_rejected():
    with pytest.raises(TaskRewriteError):
        propose_task_rewrite(
            registry_ids={"r::1": "r"},
            week_evidence=[_ev("r::1", "r", 2, 3)],
        )


def test_bad_threshold_rejected():
    with pytest.raises(TaskRewriteError):
        RewriteThresholds(min_runs_for_evidence=0)
    with pytest.raises(TaskRewriteError):
        RewriteThresholds(graduate_success_rate=1.5)
    with pytest.raises(TaskRewriteError):
        RewriteThresholds(revise_variance=-0.1)
    with pytest.raises(TaskRewriteError):
        RewriteThresholds(min_runs_for_evidence=0)


def test_bad_version_rejected():
    with pytest.raises(TaskRewriteError):
        propose_task_rewrite(registry_ids={}, week_evidence=[], current_version=0)


# ---------------------------------------------------------------------------
# families_affected + determinism + purity
# ---------------------------------------------------------------------------


def test_families_affected_collected():
    reg = {"r::1": "reasoning", "c::1": "code"}
    sigs = [
        PlatformSurfaceSignal(family="writing", proposed_task_id="writing::w1", rationale="x"),
    ]
    ev = [_ev("c::1", "code", 4, 4, (1, 1, 1, 1))]
    p = propose_task_rewrite(registry_ids=reg, week_evidence=ev, surface_signals=sigs)
    assert set(p.families_affected) == {"writing", "code"}


def test_pure_idempotent():
    reg = {"r::1": "reasoning"}
    ev = [_ev("r::1", "reasoning", 4, 4, (1, 1, 1, 1))]
    sigs = [PlatformSurfaceSignal(family="w", proposed_task_id="w::1", rationale="x")]
    a = propose_task_rewrite(registry_ids=reg, week_evidence=ev, surface_signals=sigs)
    b = propose_task_rewrite(registry_ids=reg, week_evidence=ev, surface_signals=sigs)
    assert a == b


def test_diff_ordering_deterministic():
    # multiple emits → sorted by appearance; graduates by sorted task_id
    reg = {"b::1": "fam_b", "a::1": "fam_a"}
    sigs = [
        PlatformSurfaceSignal(family="fam_c", proposed_task_id="c::1", rationale="x"),
        PlatformSurfaceSignal(family="fam_d", proposed_task_id="d::1", rationale="y"),
    ]
    ev = [_ev("a::1", "fam_a", 3, 3, (1, 1, 1)), _ev("b::1", "fam_b", 3, 3, (1, 1, 1))]
    p = propose_task_rewrite(registry_ids=reg, week_evidence=ev, surface_signals=sigs)
    kinds = [d.kind for d in p.diffs]
    # emits first (c::1, d::1), then graduates sorted by task_id (a::1, b::1)
    assert kinds == ["emit", "emit", "graduate", "graduate"]
    assert [d.task_id for d in p.diffs] == ["c::1", "d::1", "a::1", "b::1"]


def test_proposal_is_frozen_value():
    p = propose_task_rewrite(registry_ids={"r::1": "r"}, week_evidence=[])
    assert isinstance(p, TaskRewriteProposal)
    assert isinstance(p.diffs, tuple)
    assert isinstance(p.notes, tuple)
