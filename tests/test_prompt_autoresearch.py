"""Prompt-autoresearch tests (Sprint 19, integration_autoresearch.md Wedge 1)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tools.prompt_autoresearch import (
    BudgetCap,
    BudgetExceeded,
    CompositeScore,
    PromptAutoresearchRunner,
    PromptMutation,
    PromptMutationOutcome,
    composite_score,
    deterministic_voice_style_score,
    grounding_preserved_rate,
    sector_vocab_overlap,
)
from tools.prompt_autoresearch.runner import ProductionEnvironmentRefusal, make_id


# ── Score components ────────────────────────────────────────────────


def test_voice_style_score_penalizes_padding():
    clean = "Error rates dropped below 10⁻³ at the 100Q scale."
    padded = "It is important to note that error rates dropped. Furthermore, this matters."
    assert deterministic_voice_style_score(clean) > deterministic_voice_style_score(padded)


def test_voice_style_score_penalizes_em_dash_excess():
    """Per master-spec §5.4: ≤2 em-dashes per thesis (≈1k chars)."""
    # Same length (~1000 chars) so the per-1000-chars normalization
    # compares fairly. Sparse: 1 em-dash. Spammy: 20 em-dashes.
    body = "x" * 990
    sparse = body + " — fine"
    spammy = body + " — — — — — — — — — — — — — — — — — — — —"
    assert deterministic_voice_style_score(sparse) > deterministic_voice_style_score(spammy)


def test_sector_vocab_overlap_basic():
    terms = ["sidelobe", "neutral atom", "decoherence"]
    text = "The sidelobe suppression and decoherence properties matter."
    score = sector_vocab_overlap(text, terms)
    assert score == 2 / 3  # 2 of 3 terms appear


def test_sector_vocab_overlap_empty_terms_returns_one():
    """With no corpus terms to compare against, the score should
    default to 1 (no penalty)."""
    assert sector_vocab_overlap("any text", []) == 1.0


def test_grounding_preserved_rate():
    text = "Per [chunk-A], the result holds. Per [chunk-C], the limit binds."
    assert grounding_preserved_rate(text, ["chunk-A", "chunk-B", "chunk-C"]) == 2 / 3


def test_composite_score_combines_correctly():
    text = "Concise synthesis citing chunk-A and discussing sidelobe phenomena."
    cs = composite_score(
        text,
        rubric_score=0.8,
        corpus_terms=["sidelobe"],
        expected_claim_ids=["chunk-A"],
    )
    # weights: 0.4 * rubric + 0.3 * vs + 0.2 * sv + 0.1 * gr
    # rubric=0.8, vs~=1.0 (no padding, no em-dashes), sv=1.0, gr=1.0
    assert 0.4 * 0.8 + 0.3 + 0.2 + 0.1 == pytest.approx(cs.total)


# ── Budget ──────────────────────────────────────────────────────────


def test_budget_records_iteration_cost():
    bc = BudgetCap(total_cap_usd=Decimal("1.00"), per_iteration_cap_usd=Decimal("0.20"))
    bc.record_iteration_cost(Decimal("0.05"))
    assert bc.spent_total_usd == Decimal("0.05")
    assert bc.iteration_count == 1


def test_budget_raises_on_per_iteration_cap_breach():
    bc = BudgetCap(per_iteration_cap_usd=Decimal("0.10"))
    with pytest.raises(BudgetExceeded):
        bc.record_iteration_cost(Decimal("0.50"))


def test_budget_raises_on_total_cap_breach():
    bc = BudgetCap(
        total_cap_usd=Decimal("0.10"),
        per_iteration_cap_usd=Decimal("1.00"),
    )
    bc.record_iteration_cost(Decimal("0.08"))
    with pytest.raises(BudgetExceeded):
        bc.record_iteration_cost(Decimal("0.05"))


# ── Runner ──────────────────────────────────────────────────────────


def test_runner_refuses_production_env(monkeypatch):
    """Per master-spec §14.2: prompt autoresearch is local-only."""
    monkeypatch.setenv("ANTIEK_ENV", "production")
    runner = PromptAutoresearchRunner(role="synthesizer")
    mutation = PromptMutation(
        mutation_id=make_id(),
        role="synthesizer",
        parent_baseline_id=None,
        proposed_prompt="Test prompt",
        rationale="test",
    )
    with pytest.raises(ProductionEnvironmentRefusal):
        runner.run_iteration(
            mutation,
            execute_fn=lambda p: ("text", Decimal("0.01")),
            corpus_terms=[],
            expected_claim_ids=[],
            rubric_judge_fn=lambda t: 1.0,
        )


def test_runner_accepts_when_delta_exceeds_epsilon(monkeypatch):
    monkeypatch.delenv("ANTIEK_ENV", raising=False)
    runner = PromptAutoresearchRunner(
        role="synthesizer",
        epsilon=0.05,
        baseline_total_score=0.5,
    )
    mutation = PromptMutation(
        mutation_id=make_id(),
        role="synthesizer",
        parent_baseline_id=None,
        proposed_prompt="Improved prompt",
        rationale="strip padding",
    )
    outcome = runner.run_iteration(
        mutation,
        execute_fn=lambda p: ("Concise synthesis citing chunk-A.", Decimal("0.02")),
        corpus_terms=["concise"],
        expected_claim_ids=["chunk-A"],
        rubric_judge_fn=lambda t: 0.95,
    )
    assert outcome.accepted is True
    assert outcome.candidate_score > outcome.baseline_score + runner.epsilon
    # Baseline should have advanced.
    assert runner.baseline_total_score == outcome.candidate_score


def test_runner_rejects_when_delta_below_epsilon(monkeypatch):
    monkeypatch.delenv("ANTIEK_ENV", raising=False)
    runner = PromptAutoresearchRunner(
        role="synthesizer",
        epsilon=0.50,  # high bar
        baseline_total_score=0.5,
    )
    mutation = PromptMutation(
        mutation_id=make_id(),
        role="synthesizer",
        parent_baseline_id=None,
        proposed_prompt="Marginal prompt",
        rationale="tiny tweak",
    )
    outcome = runner.run_iteration(
        mutation,
        execute_fn=lambda p: ("text", Decimal("0.01")),
        corpus_terms=[],
        expected_claim_ids=[],
        rubric_judge_fn=lambda t: 0.55,
    )
    assert outcome.accepted is False
    # Baseline did NOT advance.
    assert runner.baseline_total_score == 0.5


def test_runner_records_budget_breach_as_rejection(monkeypatch):
    monkeypatch.delenv("ANTIEK_ENV", raising=False)
    runner = PromptAutoresearchRunner(
        role="synthesizer",
        budget=BudgetCap(per_iteration_cap_usd=Decimal("0.10")),
    )
    mutation = PromptMutation(
        mutation_id=make_id(),
        role="synthesizer",
        parent_baseline_id=None,
        proposed_prompt="Expensive prompt",
        rationale="tries something costly",
    )
    outcome = runner.run_iteration(
        mutation,
        execute_fn=lambda p: ("text", Decimal("0.50")),  # over cap
        corpus_terms=[],
        expected_claim_ids=[],
        rubric_judge_fn=lambda t: 1.0,
    )
    assert outcome.accepted is False
    assert "budget exceeded" in outcome.notes
