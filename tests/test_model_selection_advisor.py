"""Tests for the model-selection advisor (asks #8/#9/#10 — the decision tree).

Each load-bearing invariant in the module docstring is a named test. Run with:

    .venv/bin/python -m pytest tests/test_model_selection_advisor.py -q \
        --noconftest --override-ini="addopts=" -p no:cacheprovider
"""

from __future__ import annotations

import copy

import pytest

from substrate.model_selection.advisor import (
    BudgetAffordability,
    CostBand,
    ModelBenchScore,
    ModelEntry,
    ModelRecommendation,
    ModelSelectionError,
    OperatorConstraints,
    RankedModel,
    recommend_model,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _rec(recs: list[RankedModel], model_id: str) -> RankedModel:
    return next(r for r in recs if r.model_id == model_id)


def _priced(low: float, high: float | None = None) -> CostBand:
    return CostBand(low=low, high=high if high is not None else low)


def _unpriced() -> CostBand:
    return CostBand(low=None, high=None, pricing_known=False)


# --------------------------------------------------------------------------- #
# Invariant 1: unscored model never ranked above a scored one
# --------------------------------------------------------------------------- #


def test_unscored_ranks_below_scored():
    rec = recommend_model(
        task_family="synthesis",
        inventory=[ModelEntry("a"), ModelEntry("b"), ModelEntry("c")],
        bench_scores={
            "a": ModelBenchScore("a", 0.9),
            "b": ModelBenchScore("b", None),  # unscored
            "c": ModelBenchScore("c", 0.4),
        },
        prompt_cost={"a": _priced(1), "b": _priced(1), "c": _priced(1)},
        budget=BudgetAffordability(within_budget=True),
    )
    ids = [r.model_id for r in rec.ranked]
    assert ids == ["a", "c", "b"]  # scored desc, unscored last
    assert _rec(rec.ranked, "b").scored is False
    assert _rec(rec.ranked, "b").bench_score is None
    assert _rec(rec.ranked, "b").score_rank is None


def test_unscored_never_fabricated_as_zero_score():
    rec = recommend_model(
        task_family="fam",
        inventory=[ModelEntry("only")],
        bench_scores={"only": ModelBenchScore("only", None)},
        prompt_cost={"only": _priced(1)},
        budget=BudgetAffordability(within_budget=True),
    )
    r = rec.ranked[0]
    assert r.bench_score is None
    assert r.scored is False
    assert "unbenchmarked" in r.rationale


# --------------------------------------------------------------------------- #
# Invariant 2: unpriced model cost is None, never 0
# --------------------------------------------------------------------------- #


def test_unpriced_model_cost_is_none():
    rec = recommend_model(
        task_family="fam",
        inventory=[ModelEntry("a"), ModelEntry("b")],
        bench_scores={"a": ModelBenchScore("a", 0.8), "b": ModelBenchScore("b", 0.8)},
        prompt_cost={"a": _priced(1), "b": _unpriced()},
        budget=BudgetAffordability(within_budget=True),
    )
    a = _rec(rec.ranked, "a")
    b = _rec(rec.ranked, "b")
    assert a.per_prompt_cost is not None and a.per_prompt_cost.low == 1
    # Unpriced model keeps its CostBand with pricing_known=False (auditable:
    # distinguishable from absent-from-map), never coerced to a 0.0 numeric.
    assert b.per_prompt_cost is not None
    assert b.per_prompt_cost.pricing_known is False
    assert b.per_prompt_cost.low is None
    assert "unknown" in b.rationale


# --------------------------------------------------------------------------- #
# Invariant 3: unknown budget never fabricates a verdict
# --------------------------------------------------------------------------- #


def test_unknown_budget_yields_unknown_affordability_for_all():
    rec = recommend_model(
        task_family="fam",
        inventory=[ModelEntry("a"), ModelEntry("b")],
        bench_scores={"a": ModelBenchScore("a", 0.8), "b": ModelBenchScore("b", 0.7)},
        prompt_cost={"a": _priced(1), "b": _priced(2)},
        budget=BudgetAffordability(within_budget=None),
    )
    assert all(r.affordability == "unknown" for r in rec.ranked)
    assert any("within_budget is unknown" in n for n in rec.notes)


def test_unaffordable_budget_marks_all_unaffordable():
    rec = recommend_model(
        task_family="fam",
        inventory=[ModelEntry("a")],
        bench_scores={"a": ModelBenchScore("a", 0.9)},
        prompt_cost={"a": _priced(1)},
        budget=BudgetAffordability(within_budget=False),
    )
    assert rec.ranked[0].affordability == "unaffordable"


# --------------------------------------------------------------------------- #
# Invariant 4: excluded model never in ranked output; surfaced with reason
# --------------------------------------------------------------------------- #


def test_excluded_model_not_ranked_but_surfaced():
    rec = recommend_model(
        task_family="fam",
        inventory=[ModelEntry("a"), ModelEntry("b"), ModelEntry("x")],
        bench_scores={
            "a": ModelBenchScore("a", 0.5),
            "b": ModelBenchScore("b", 0.6),
            "x": ModelBenchScore("x", 0.99),  # would be best
        },
        prompt_cost={"a": _priced(1), "b": _priced(1), "x": _priced(1)},
        budget=BudgetAffordability(within_budget=True),
        constraints=OperatorConstraints(excluded=frozenset({"x"})),
    )
    ids = [r.model_id for r in rec.ranked]
    assert "x" not in ids
    assert ids == ["b", "a"]
    assert len(rec.excluded) == 1
    assert rec.excluded[0].model_id == "x"
    assert rec.excluded[0].reason == "operator-excluded"
    assert rec.excluded[0].bench_score == 0.99


# --------------------------------------------------------------------------- #
# Invariant 5: preferred pin honored as rank 1, honestly
# --------------------------------------------------------------------------- #


def test_preferred_pin_forces_rank_one():
    rec = recommend_model(
        task_family="fam",
        inventory=[ModelEntry("a"), ModelEntry("b"), ModelEntry("pin")],
        bench_scores={
            "a": ModelBenchScore("a", 0.9),
            "b": ModelBenchScore("b", 0.8),
            "pin": ModelBenchScore("pin", 0.3),  # lowest score
        },
        prompt_cost={"a": _priced(1), "b": _priced(1), "pin": _priced(5)},
        budget=BudgetAffordability(within_budget=False),
        constraints=OperatorConstraints(preferred="pin"),
    )
    assert rec.ranked[0].model_id == "pin"
    assert rec.ranked[0].preferred_override is True
    # honesty: score/cost/affordability still shown despite the pin
    assert rec.ranked[0].bench_score == 0.3
    assert rec.ranked[0].per_prompt_cost is not None
    assert rec.ranked[0].affordability == "unaffordable"
    assert "operator preferred-pin" in rec.ranked[0].rationale


def test_preferred_pin_not_in_candidates_noted():
    rec = recommend_model(
        task_family="fam",
        inventory=[ModelEntry("a")],
        bench_scores={"a": ModelBenchScore("a", 0.9)},
        prompt_cost={"a": _priced(1)},
        budget=BudgetAffordability(within_budget=True),
        constraints=OperatorConstraints(preferred="ghost"),
    )
    assert rec.ranked[0].model_id == "a"
    assert any("not in candidates" in n for n in rec.notes)


# --------------------------------------------------------------------------- #
# Invariant 6: no bench signal → cost-only ranking, flagged
# --------------------------------------------------------------------------- #


def test_no_scores_falls_back_to_cost_ranking_flagged():
    rec = recommend_model(
        task_family="fam",
        inventory=[ModelEntry("cheap"), ModelEntry("pricey")],
        bench_scores={},  # no scores at all
        prompt_cost={"cheap": _priced(1), "pricey": _priced(5)},
        budget=BudgetAffordability(within_budget=True),
    )
    assert rec.evidence_quality == "no_bench_signal"
    assert [r.model_id for r in rec.ranked] == ["cheap", "pricey"]
    assert any("no_bench_signal" in n for n in rec.notes)
    assert all(r.scored is False for r in rec.ranked)


def test_full_evidence_when_at_least_one_scored():
    rec = recommend_model(
        task_family="fam",
        inventory=[ModelEntry("a"), ModelEntry("b")],
        bench_scores={"a": ModelBenchScore("a", 0.9)},  # b unscored
        prompt_cost={"a": _priced(1), "b": _priced(1)},
        budget=BudgetAffordability(within_budget=True),
    )
    assert rec.evidence_quality == "scored"


# --------------------------------------------------------------------------- #
# Invariant 7: ties named, not arbitrarily broken
# --------------------------------------------------------------------------- #


def test_score_and_cost_tie_names_all_in_top():
    rec = recommend_model(
        task_family="fam",
        inventory=[ModelEntry("aaa"), ModelEntry("zzz")],
        bench_scores={"aaa": ModelBenchScore("aaa", 0.8), "zzz": ModelBenchScore("zzz", 0.8)},
        prompt_cost={"aaa": _priced(1), "zzz": _priced(1)},
        budget=BudgetAffordability(within_budget=True),
    )
    assert len(rec.top) == 2
    top_ids = {r.model_id for r in rec.top}
    assert top_ids == {"aaa", "zzz"}
    assert any("co-equal" in n for n in rec.notes)


def test_score_tie_cost_differs_picks_cheaper():
    rec = recommend_model(
        task_family="fam",
        inventory=[ModelEntry("a"), ModelEntry("b")],
        bench_scores={"a": ModelBenchScore("a", 0.8), "b": ModelBenchScore("b", 0.8)},
        prompt_cost={"a": _priced(2), "b": _priced(1)},
        budget=BudgetAffordability(within_budget=True),
    )
    assert rec.ranked[0].model_id == "b"  # cheaper wins the tie
    assert len(rec.top) == 1


def test_single_winner_top_has_one():
    rec = recommend_model(
        task_family="fam",
        inventory=[ModelEntry("a"), ModelEntry("b")],
        bench_scores={"a": ModelBenchScore("a", 0.9), "b": ModelBenchScore("b", 0.5)},
        prompt_cost={"a": _priced(1), "b": _priced(1)},
        budget=BudgetAffordability(within_budget=True),
    )
    assert len(rec.top) == 1
    assert rec.top[0].model_id == "a"


# --------------------------------------------------------------------------- #
# Invariant 8: every ranked model fully auditable
# --------------------------------------------------------------------------- #


def test_ranked_model_has_all_audit_fields():
    rec = recommend_model(
        task_family="synthesis",
        inventory=[ModelEntry("a"), ModelEntry("b")],
        bench_scores={"a": ModelBenchScore("a", 0.91, completed_runs=10), "b": ModelBenchScore("b", None)},
        prompt_cost={"a": _priced(0.5, 2.0), "b": _unpriced()},
        budget=BudgetAffordability(within_budget=True, remaining_usd=42.0),
    )
    a = _rec(rec.ranked, "a")
    assert isinstance(a, RankedModel)
    assert a.rank == 1
    assert a.bench_score == 0.91
    assert a.scored is True
    assert a.score_rank == 1
    assert a.per_prompt_cost is not None and a.per_prompt_cost.high == 2.0
    assert a.affordability == "affordable"
    assert "bench score" in a.rationale and "score rank 1" in a.rationale


# --------------------------------------------------------------------------- #
# Invariant 9: deterministic + pure
# --------------------------------------------------------------------------- #


def test_identical_inputs_produce_identical_recommendations():
    inv = [ModelEntry("a"), ModelEntry("b")]
    scores = {"a": ModelBenchScore("a", 0.8), "b": ModelBenchScore("b", 0.7)}
    costs = {"a": _priced(1), "b": _priced(1)}
    budget = BudgetAffordability(within_budget=True)
    r1 = recommend_model(task_family="fam", inventory=inv, bench_scores=scores, prompt_cost=costs, budget=budget)
    r2 = recommend_model(task_family="fam", inventory=copy.deepcopy(inv), bench_scores=scores, prompt_cost=costs, budget=budget)
    assert r1 == r2


def test_deterministic_order_with_score_desc_cost_asc_id_asc():
    rec = recommend_model(
        task_family="fam",
        inventory=[ModelEntry("z"), ModelEntry("a"), ModelEntry("m")],
        bench_scores={"z": ModelBenchScore("z", 0.9), "a": ModelBenchScore("a", 0.9), "m": ModelBenchScore("m", 0.5)},
        prompt_cost={"z": _priced(2), "a": _priced(1), "m": _priced(1)},
        budget=BudgetAffordability(within_budget=True),
    )
    # a and z tie on score; a cheaper → a first. m lower score → last.
    assert [r.model_id for r in rec.ranked] == ["a", "z", "m"]


# --------------------------------------------------------------------------- #
# Invariant 10: advisory only (frozen value, never mutates)
# --------------------------------------------------------------------------- #


def test_recommendation_is_frozen_and_advisory():
    rec = recommend_model(
        task_family="fam",
        inventory=[ModelEntry("a")],
        bench_scores={"a": ModelBenchScore("a", 0.9)},
        prompt_cost={"a": _priced(1)},
        budget=BudgetAffordability(within_budget=True),
    )
    assert isinstance(rec, ModelRecommendation)
    assert all("advisory" in n for n in rec.notes[:1])
    with pytest.raises(AttributeError):
        rec.ranked = []  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# max_cost ceiling
# --------------------------------------------------------------------------- #


def test_max_cost_ceiling_filters_priced_over_ceiling():
    rec = recommend_model(
        task_family="fam",
        inventory=[ModelEntry("a"), ModelEntry("b"), ModelEntry("c")],
        bench_scores={"a": ModelBenchScore("a", 0.5), "b": ModelBenchScore("b", 0.6), "c": ModelBenchScore("c", 0.7)},
        prompt_cost={"a": _priced(1), "b": _priced(3), "c": _priced(5)},
        budget=BudgetAffordability(within_budget=True),
        constraints=OperatorConstraints(max_cost=2.0),
    )
    ids = [r.model_id for r in rec.ranked]
    assert ids == ["a"]  # b(3) and c(5) over ceiling
    assert set(rec.over_cost_ceiling) == {"b", "c"}


def test_max_cost_ceiling_keeps_unpriced_models():
    rec = recommend_model(
        task_family="fam",
        inventory=[ModelEntry("priced"), ModelEntry("unpriced")],
        bench_scores={"priced": ModelBenchScore("priced", 0.5), "unpriced": ModelBenchScore("unpriced", 0.9)},
        prompt_cost={"priced": _priced(10), "unpriced": _unpriced()},
        budget=BudgetAffordability(within_budget=True),
        constraints=OperatorConstraints(max_cost=2.0),
    )
    # priced over ceiling filtered; unpriced kept (cannot verify against ceiling)
    ids = [r.model_id for r in rec.ranked]
    assert ids == ["unpriced"]
    assert rec.over_cost_ceiling == ("priced",)


# --------------------------------------------------------------------------- #
# Edge cases + validation
# --------------------------------------------------------------------------- #


def test_empty_inventory_yields_empty_recommendation():
    rec = recommend_model(
        task_family="fam",
        inventory=[],
        bench_scores={},
        prompt_cost={},
        budget=BudgetAffordability(within_budget=True),
    )
    assert rec.has_candidates is False
    assert rec.ranked == [] and rec.top == []


def test_all_excluded_yields_empty_ranked():
    rec = recommend_model(
        task_family="fam",
        inventory=[ModelEntry("a"), ModelEntry("b")],
        bench_scores={"a": ModelBenchScore("a", 0.9), "b": ModelBenchScore("b", 0.8)},
        prompt_cost={"a": _priced(1), "b": _priced(1)},
        budget=BudgetAffordability(within_budget=True),
        constraints=OperatorConstraints(excluded=frozenset({"a", "b"})),
    )
    assert rec.ranked == []
    assert len(rec.excluded) == 2


def test_empty_task_family_rejected():
    with pytest.raises(ModelSelectionError):
        recommend_model(
            task_family="  ",
            inventory=[ModelEntry("a")],
            bench_scores={},
            prompt_cost={},
            budget=BudgetAffordability(within_budget=True),
        )


def test_empty_model_id_rejected():
    with pytest.raises(ModelSelectionError):
        recommend_model(
            task_family="fam",
            inventory=[ModelEntry("")],
            bench_scores={},
            prompt_cost={},
            budget=BudgetAffordability(within_budget=True),
        )


def test_negative_epsilon_rejected():
    with pytest.raises(ModelSelectionError):
        recommend_model(
            task_family="fam",
            inventory=[ModelEntry("a")],
            bench_scores={},
            prompt_cost={},
            budget=BudgetAffordability(within_budget=True),
            epsilon=-0.1,
        )


def test_missing_bench_score_treated_as_unscored():
    # model in inventory but absent from bench_scores → unbenchmarked, not error
    rec = recommend_model(
        task_family="fam",
        inventory=[ModelEntry("a"), ModelEntry("b")],
        bench_scores={"a": ModelBenchScore("a", 0.9)},  # b absent
        prompt_cost={"a": _priced(1), "b": _priced(1)},
        budget=BudgetAffordability(within_budget=True),
    )
    b = _rec(rec.ranked, "b")
    assert b.scored is False
    assert b.bench_score is None


def test_task_family_stripped():
    rec = recommend_model(
        task_family="  synthesis  ",
        inventory=[ModelEntry("a")],
        bench_scores={"a": ModelBenchScore("a", 0.9)},
        prompt_cost={"a": _priced(1)},
        budget=BudgetAffordability(within_budget=True),
    )
    assert rec.task_family == "synthesis"


def test_ranks_are_one_based_and_contiguous():
    rec = recommend_model(
        task_family="fam",
        inventory=[ModelEntry("a"), ModelEntry("b"), ModelEntry("c")],
        bench_scores={"a": ModelBenchScore("a", 0.9), "b": ModelBenchScore("b", 0.5), "c": ModelBenchScore("c", 0.7)},
        prompt_cost={"a": _priced(1), "b": _priced(1), "c": _priced(1)},
        budget=BudgetAffordability(within_budget=True),
    )
    assert [r.rank for r in rec.ranked] == [1, 2, 3]


def test_end_to_end_fusion_of_bench_cost_budget_constraints():
    rec = recommend_model(
        task_family="deep-research",
        inventory=[ModelEntry("alpha"), ModelEntry("beta"), ModelEntry("gamma"), ModelEntry("delta")],
        bench_scores={
            "alpha": ModelBenchScore("alpha", 0.95, completed_runs=20),
            "beta": ModelBenchScore("beta", 0.88, completed_runs=15),
            "gamma": ModelBenchScore("gamma", None),  # unbenchmarked
            "delta": ModelBenchScore("delta", 0.40, completed_runs=8),
        },
        prompt_cost={"alpha": _priced(2, 4), "beta": _priced(1, 2), "gamma": _unpriced(), "delta": _priced(0.1)},
        budget=BudgetAffordability(within_budget=True, remaining_usd=100.0),
        constraints=OperatorConstraints(excluded=frozenset({"delta"}), max_cost=5.0),
    )
    # delta excluded; alpha best score → rank 1; beta 2; gamma unscored last.
    ids = [r.model_id for r in rec.ranked]
    assert ids == ["alpha", "beta", "gamma"]
    assert rec.evidence_quality == "scored"
    assert len(rec.top) == 1 and rec.top[0].model_id == "alpha"
    assert {e.model_id for e in rec.excluded} == {"delta"}
    assert rec.ranked[0].affordability == "affordable"
