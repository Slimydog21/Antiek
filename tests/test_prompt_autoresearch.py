"""Prompt-autoresearch tests (Sprint 19, integration_autoresearch.md Wedge 1)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tools.prompt_autoresearch import (
    BudgetCap,
    BudgetExceeded,
    PromptAutoresearchRunner,
    PromptMutation,
    composite_score,
    deterministic_voice_style_score,
    grounding_preserved_rate,
    load_outcomes_json,
    sector_vocab_overlap,
    write_outcomes_json,
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
    assert pytest.approx(cs.total) == 0.4 * 0.8 + 0.3 + 0.2 + 0.1


def test_composite_score_rejects_out_of_range_rubric():
    with pytest.raises(ValueError, match="rubric_score must be a number in \\[0, 1\\]"):
        composite_score(
            "text",
            rubric_score=1.5,
            corpus_terms=[],
            expected_claim_ids=[],
        )


# ── Budget ──────────────────────────────────────────────────────────


def test_budget_records_iteration_cost():
    bc = BudgetCap(total_cap_usd=Decimal("1.00"), per_iteration_cap_usd=Decimal("0.20"))
    bc.record_iteration_cost(Decimal("0.05"))
    assert bc.spent_total_usd == Decimal("0.05")
    assert bc.iteration_count == 1


def test_budget_rejects_negative_caps_and_costs():
    try:
        BudgetCap(total_cap_usd=Decimal("-1.00"))
    except ValueError as exc:
        assert "total_cap_usd must be non-negative" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected negative total cap to be rejected")

    bc = BudgetCap()
    try:
        bc.will_breach(Decimal("-0.01"))
    except ValueError as exc:
        assert "projected_iteration_cost_usd must be non-negative" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected negative projected cost to be rejected")

    try:
        bc.record_iteration_cost(Decimal("-0.01"))
    except ValueError as exc:
        assert "cost_usd must be non-negative" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected negative iteration cost to be rejected")


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


def test_runner_requires_valid_acceptance_state():
    with pytest.raises(ValueError, match="epsilon must be a non-negative finite number"):
        PromptAutoresearchRunner(role="synthesizer", epsilon=-0.01)

    with pytest.raises(ValueError, match="baseline_total_score must be a number in \\[0, 1\\]"):
        PromptAutoresearchRunner(role="synthesizer", baseline_total_score=1.5)


def test_runner_rejects_cross_role_mutation_before_execution(monkeypatch):
    monkeypatch.delenv("ANTIEK_ENV", raising=False)
    runner = PromptAutoresearchRunner(role="synthesizer")
    mutation = PromptMutation(
        mutation_id=make_id(),
        role="decomposer",
        parent_baseline_id=None,
        proposed_prompt="Wrong role prompt",
        rationale="cross-role accident",
    )
    executed = False

    def execute_fn(prompt: str) -> tuple[str, Decimal]:
        nonlocal executed
        executed = True
        return prompt, Decimal("0.01")

    with pytest.raises(ValueError, match="does not match runner role"):
        runner.run_iteration(
            mutation,
            execute_fn=execute_fn,
            corpus_terms=[],
            expected_claim_ids=[],
            rubric_judge_fn=lambda t: 1.0,
        )

    assert executed is False
    assert runner.budget.iteration_count == 0
    assert runner.iterations == []


def test_prompt_mutation_requires_load_bearing_text_fields():
    with pytest.raises(ValueError, match="proposed_prompt must be a non-empty string"):
        PromptMutation(
            mutation_id=make_id(),
            role="synthesizer",
            parent_baseline_id=None,
            proposed_prompt="   ",
            rationale="missing candidate",
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
    assert outcome.mutation_rationale == "strip padding"
    assert outcome.parent_baseline_id is None
    assert outcome.proposed_at == mutation.proposed_at
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
    assert outcome.mutation_rationale == "tries something costly"
    assert outcome.parent_baseline_id is None
    assert outcome.proposed_at == mutation.proposed_at


def test_runner_budget_breach_outcome_round_trips_to_verdict_json(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTIEK_ENV", raising=False)
    runner = PromptAutoresearchRunner(
        role="synthesizer",
        budget=BudgetCap(per_iteration_cap_usd=Decimal("0.10")),
        baseline_total_score=0.50,
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
        execute_fn=lambda p: ("text", Decimal("0.50")),
        corpus_terms=[],
        expected_claim_ids=[],
        rubric_judge_fn=lambda t: 1.0,
    )

    assert outcome.accepted is False
    assert outcome.baseline_score == 0.50
    assert outcome.candidate_score == 0.50
    assert outcome.delta == 0.0
    assert runner.iterations == [outcome]
    assert runner.baseline_total_score == 0.50

    path = tmp_path / "outcomes.json"
    write_outcomes_json(path, role="synthesizer", outcomes=runner.iterations)

    role, loaded = load_outcomes_json(path)
    assert role == "synthesizer"
    assert len(loaded) == 1
    assert loaded[0].mutation_id == outcome.mutation_id
    assert loaded[0].accepted is False
    assert loaded[0].mutation_rationale == "tries something costly"
    assert loaded[0].proposed_at == mutation.proposed_at
