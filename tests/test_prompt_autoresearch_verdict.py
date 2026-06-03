"""Autoresearch Wedge 1 ratify-or-reject verdict (§15.6, the Lutke-gap test)."""

from __future__ import annotations

from decimal import Decimal

from tools.prompt_autoresearch.runner import PromptMutationOutcome
from tools.prompt_autoresearch.score import CompositeScore
from tools.prompt_autoresearch.verdict import (
    MIN_MEAN_DELTA,
    MIN_MUTATIONS,
    compute_verdict,
    render_verdict_markdown,
)


def _mk_outcome(
    *,
    mutation_id: str,
    delta: float,
    accepted: bool,
    rubric: float = 0.85,
    voice_style: float = 0.85,
    sector_vocab: float = 0.85,
    grounding: float = 0.90,
) -> PromptMutationOutcome:
    return PromptMutationOutcome(
        mutation_id=mutation_id,
        accepted=accepted,
        baseline_score=0.70,
        candidate_score=0.70 + delta,
        delta=delta,
        epsilon_required=0.05,
        composite_breakdown=CompositeScore(
            rubric=rubric,
            voice_style=voice_style,
            sector_vocab=sector_vocab,
            grounding=grounding,
            total=0.70 + delta,
        ),
        cost_usd=Decimal("0.05"),
    )


def test_empty_outcomes_insufficient_data():
    v = compute_verdict("synthesizer", [])
    assert v.decision == "insufficient_data"
    assert v.iteration_count == 0


def test_below_min_mutations_insufficient_data():
    outs = [
        _mk_outcome(mutation_id=f"m-{i}", delta=0.10, accepted=True)
        for i in range(5)
    ]
    v = compute_verdict("synthesizer", outs)
    assert v.decision == "insufficient_data"
    assert "Only 5 mutations" in v.rationale


def test_ratify_when_acceptance_and_mean_delta_pass():
    # 20 mutations, all accepted, mean delta 0.10 — clean ratify
    outs = [
        _mk_outcome(mutation_id=f"m-{i}", delta=0.10, accepted=True)
        for i in range(MIN_MUTATIONS)
    ]
    v = compute_verdict("synthesizer", outs)
    assert v.decision == "ratify"
    assert v.acceptance_rate == 1.0
    assert v.mean_delta == 0.10
    assert v.sub_metric_regressions == []


def test_reject_when_acceptance_rate_below_floor():
    # 20 mutations, only 4 accepted (20%) — below 40% floor → reject
    outs = []
    for i in range(MIN_MUTATIONS):
        if i < 4:
            outs.append(_mk_outcome(mutation_id=f"m-{i}", delta=0.10, accepted=True))
        else:
            outs.append(_mk_outcome(mutation_id=f"m-{i}", delta=-0.05, accepted=False))
    v = compute_verdict("synthesizer", outs)
    assert v.decision == "reject"
    assert v.acceptance_rate == 4 / MIN_MUTATIONS
    assert "acceptance rate" in v.rationale


def test_reject_when_mean_delta_below_floor():
    # 20 mutations, 60% accepted but mean delta tiny → mean below floor
    outs = []
    for i in range(MIN_MUTATIONS):
        if i < 12:
            outs.append(_mk_outcome(mutation_id=f"m-{i}", delta=0.02, accepted=True))
        else:
            outs.append(_mk_outcome(mutation_id=f"m-{i}", delta=-0.05, accepted=False))
    v = compute_verdict("synthesizer", outs)
    assert v.decision == "reject"
    assert v.mean_delta < MIN_MEAN_DELTA


def test_reject_when_grounding_regression():
    """Composite score improvement masking grounding regression → REJECT."""
    outs = [
        _mk_outcome(
            mutation_id=f"m-{i}",
            delta=0.10,
            accepted=True,
            # Composite up but grounding tanked
            grounding=0.50,
        )
        for i in range(MIN_MUTATIONS)
    ]
    v = compute_verdict("synthesizer", outs)
    assert v.decision == "reject"
    assert len(v.sub_metric_regressions) > 0
    assert any("grounding" in r for r in v.sub_metric_regressions)


def test_reject_when_sector_vocab_diverges_from_rubric():
    """Sector-vocab lagging rubric by 0.10+ on accepted mutations → REJECT."""
    outs = [
        _mk_outcome(
            mutation_id=f"m-{i}",
            delta=0.10,
            accepted=True,
            rubric=0.90,
            sector_vocab=0.55,  # 0.35 below rubric
        )
        for i in range(MIN_MUTATIONS)
    ]
    v = compute_verdict("synthesizer", outs)
    assert v.decision == "reject"
    assert any("sector_vocab" in r for r in v.sub_metric_regressions)


def test_median_computed():
    outs = [
        _mk_outcome(mutation_id=f"m-{i}", delta=float(i) / 100, accepted=False)
        for i in range(MIN_MUTATIONS)
    ]
    v = compute_verdict("synthesizer", outs)
    # Deltas are 0.00..0.19; median of 20 values is mean of 9th and 10th
    assert abs(v.median_delta - 0.095) < 0.001


def test_renders_markdown_with_decision_and_metrics():
    outs = [
        _mk_outcome(mutation_id=f"m-{i}", delta=0.10, accepted=True)
        for i in range(MIN_MUTATIONS)
    ]
    v = compute_verdict("synthesizer", outs)
    md = render_verdict_markdown(v)
    assert "# Autoresearch Wedge 1 verdict — `synthesizer` (§15.6)" in md
    assert "**Decision:** `ratify`" in md
    assert "## Summary" in md
    assert "## Next steps" in md
    assert "Wedges 2-4 unlock" in md


def test_render_reject_includes_regression_list():
    outs = [
        _mk_outcome(mutation_id=f"m-{i}", delta=0.10, accepted=True, grounding=0.30)
        for i in range(MIN_MUTATIONS)
    ]
    v = compute_verdict("synthesizer", outs)
    md = render_verdict_markdown(v)
    assert "## Sub-metric regressions" in md
    assert "grounding" in md
