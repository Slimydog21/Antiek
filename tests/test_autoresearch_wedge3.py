"""Tests for substrate/autoresearch/ — Sprint 30+ Wedge 3 sweep."""

from __future__ import annotations

import pytest

from substrate.autoresearch import (
    COHORT_MIN_OUTCOMES,
    CohortWindow,
    ConfigProposal,
    OperatorVerdict,
    OperatorVerdictKind,
    ProposalLedger,
    SweepAxes,
    SweepCandidate,
    SweepInput,
    rank_candidates,
    run_sweep,
)


def _cohort(n: int) -> CohortWindow:
    return CohortWindow(
        cohort_id="coh-1",
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-31T23:59:59Z",
        graded_outcomes_count=n,
    )


def _axes() -> SweepAxes:
    return SweepAxes(
        context_pack_compositions=("dense", "sparse"),
        dispatch_tier_routes=("tier1-only", "balanced"),
        scoring_function_name="held_out_outcome_score",
    )


# ── Cohort-size gate ─────────────────────────────────────────────


def test_cohort_too_small_aborts_sweep():
    """A cohort with < 500 graded outcomes returns the
    cohort_too_small status without scoring any candidates."""
    inp = SweepInput(
        cohort=_cohort(COHORT_MIN_OUTCOMES - 1),
        baseline_config={"context_pack_composition": "default"},
        axes=_axes(),
        cohort_outcomes=None,
        scoring_function=lambda _cfg, _outcomes: pytest.fail(
            "scoring function should not be called when cohort is too small",
        ),
    )
    result = run_sweep(inp)
    assert result.status == "cohort_too_small"
    assert result.ranked_candidates == ()
    assert result.proposal is None


def test_cohort_exactly_at_minimum_runs_sweep():
    inp = SweepInput(
        cohort=_cohort(COHORT_MIN_OUTCOMES),
        baseline_config={
            "context_pack_composition": "default",
            "dispatch_tier_route": "default",
        },
        axes=_axes(),
        cohort_outcomes=None,
        scoring_function=lambda cfg, _o: 0.5,
    )
    result = run_sweep(inp)
    # All candidates score 0.5; baseline scores 0.5; no improvement.
    assert result.status == "no_improvement"


# ── Candidate enumeration + ranking ──────────────────────────────


def test_sweep_enumerates_cartesian_product():
    captured: list[dict] = []

    def scoring(cfg: dict, _outcomes: object) -> float:
        captured.append(dict(cfg))
        return 0.5

    inp = SweepInput(
        cohort=_cohort(500),
        baseline_config={"context_pack_composition": "default"},
        axes=_axes(),
        cohort_outcomes=None,
        scoring_function=scoring,
    )
    run_sweep(inp)
    # baseline call + 2 compositions × 2 routes = 4 candidates.
    assert len(captured) == 1 + 4


def test_rank_candidates_orders_by_score_desc():
    cs = [
        SweepCandidate(config={"a": 1}, score=0.3, delta_against_baseline={}),
        SweepCandidate(config={"a": 2}, score=0.7, delta_against_baseline={}),
        SweepCandidate(config={"a": 3}, score=0.5, delta_against_baseline={}),
    ]
    ranked = rank_candidates(cs)
    assert [c.score for c in ranked] == [0.7, 0.5, 0.3]


def test_top_candidate_proposal_carries_score_delta():
    def scoring(cfg: dict, _o: object) -> float:
        # Prefer sparse + balanced.
        if (
            cfg.get("context_pack_composition") == "sparse"
            and cfg.get("dispatch_tier_route") == "balanced"
        ):
            return 0.9
        return 0.4

    inp = SweepInput(
        cohort=_cohort(500),
        baseline_config={
            "context_pack_composition": "default",
            "dispatch_tier_route": "default",
        },
        axes=_axes(),
        cohort_outcomes=None,
        scoring_function=scoring,
    )
    result = run_sweep(inp)
    assert result.status == "ok"
    assert result.proposal is not None
    p = result.proposal
    assert p.score == 0.9
    assert p.baseline_score == 0.4
    assert p.score_improvement == pytest.approx(0.5)
    assert p.proposed_delta["context_pack_composition"] == "sparse"
    assert p.proposed_delta["dispatch_tier_route"] == "balanced"


def test_no_improvement_status_when_baseline_is_best():
    inp = SweepInput(
        cohort=_cohort(500),
        baseline_config={
            "context_pack_composition": "default",
            "dispatch_tier_route": "default",
        },
        axes=_axes(),
        cohort_outcomes=None,
        # baseline=0.9, all candidates=0.3
        scoring_function=lambda cfg, _o: 0.9 if cfg.get("context_pack_composition") == "default" and cfg.get("dispatch_tier_route") == "default" else 0.3,
    )
    result = run_sweep(inp)
    # Baseline scores 0.9; best candidate scores 0.3 (or 0.9 if it
    # matched baseline by coincidence — but enumeration overrides
    # both axes, so candidates won't match the default exactly).
    assert result.status == "no_improvement"
    assert result.proposal is None


# ── Empty axes (no-op sweep) ──────────────────────────────────────


def test_empty_axes_runs_only_baseline():
    captured: list[dict] = []

    def scoring(cfg: dict, _o: object) -> float:
        captured.append(dict(cfg))
        return 0.5

    inp = SweepInput(
        cohort=_cohort(500),
        baseline_config={
            "context_pack_composition": "default",
            "dispatch_tier_route": "default",
        },
        axes=SweepAxes(
            context_pack_compositions=(),
            dispatch_tier_routes=(),
            scoring_function_name="trivial",
        ),
        cohort_outcomes=None,
        scoring_function=scoring,
    )
    run_sweep(inp)
    # baseline + 1 candidate (which equals baseline) = 2 calls.
    assert len(captured) == 2


# ── Proposal ledger discipline ────────────────────────────────────


def test_proposal_ledger_round_trip():
    ledger = ProposalLedger()
    proposal = ConfigProposal(
        baseline_config={"a": 1},
        proposed_delta={"a": 2},
        score=0.8,
        baseline_score=0.5,
    )
    ledger.record_proposal(proposal)
    assert proposal.proposal_id in ledger.proposals

    verdict = OperatorVerdict(
        proposal_id=proposal.proposal_id,
        kind=OperatorVerdictKind.ACCEPT,
        operator_id="__operator__",
        rationale="held-out cohort improvement is decisive",
    )
    ledger.record_verdict(verdict)
    assert ledger.verdict_for(proposal.proposal_id) is verdict

    accepted = ledger.accepted_proposals()
    assert len(accepted) == 1
    assert accepted[0].proposal_id == proposal.proposal_id


def test_proposal_ledger_rejects_unknown_proposal_id():
    ledger = ProposalLedger()
    with pytest.raises(KeyError):
        ledger.record_verdict(OperatorVerdict(
            proposal_id="nonexistent",
            kind=OperatorVerdictKind.ACCEPT,
        ))


def test_rejected_proposals_dont_appear_as_accepted():
    ledger = ProposalLedger()
    p1 = ConfigProposal(proposed_delta={"a": 1}, score=0.7, baseline_score=0.5)
    p2 = ConfigProposal(proposed_delta={"a": 2}, score=0.8, baseline_score=0.5)
    ledger.record_proposal(p1)
    ledger.record_proposal(p2)
    ledger.record_verdict(OperatorVerdict(
        proposal_id=p1.proposal_id, kind=OperatorVerdictKind.ACCEPT,
    ))
    ledger.record_verdict(OperatorVerdict(
        proposal_id=p2.proposal_id, kind=OperatorVerdictKind.REJECT,
    ))
    accepted = ledger.accepted_proposals()
    assert len(accepted) == 1
    assert accepted[0].proposal_id == p1.proposal_id


def test_modify_verdict_counts_as_accepted_with_modified_delta():
    ledger = ProposalLedger()
    p = ConfigProposal(proposed_delta={"a": 1}, score=0.7, baseline_score=0.5)
    ledger.record_proposal(p)
    ledger.record_verdict(OperatorVerdict(
        proposal_id=p.proposal_id,
        kind=OperatorVerdictKind.MODIFY,
        modified_delta={"a": 1, "extra_safety_flag": True},
        rationale="accept with an extra safety flag",
    ))
    accepted = ledger.accepted_proposals()
    assert len(accepted) == 1
    v = ledger.verdict_for(p.proposal_id)
    assert v is not None
    assert v.modified_delta == {"a": 1, "extra_safety_flag": True}
