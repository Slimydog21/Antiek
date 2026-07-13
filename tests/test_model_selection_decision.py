"""Tests for the model-selection decision-tree composition layer (asks #8/#9/#10/#11).

Pure composition — no dispatch, no mutation. Verifies the spec's 8 acceptance criteria.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.model_selection.decision import (
    BenchScore,
    ModelEntry,
    ModelFitSummary,
    ModelSelectionError,
    UsageActuals,
    compose_selection_decision,
)

T = "deep_research"


def _models(*ids: str) -> list[ModelEntry]:
    return [ModelEntry(model_id=m, display_name=m, provider="p") for m in ids]


def _scores(*pairs: tuple[str, float], task: str = T) -> list[BenchScore]:
    return [BenchScore(model_id=m, task_id=task, score=s) for m, s in pairs]


# --- recommendation (order-preserving, stable ties) [criterion 4] -----------


def test_ranking_desc_by_score() -> None:
    decision = compose_selection_decision(
        T, _models("A", "B", "C"), _scores(("A", 0.9), ("B", 0.5), ("C", 0.8)),
        UsageActuals(used_cents=0, limit_cents=1000),
    )
    ranks = [(r.model_id, r.rank, r.score) for r in decision.recommendation]
    assert ranks == [("A", 1, 0.9), ("C", 2, 0.8), ("B", 3, 0.5)]


def test_ties_preserve_input_order_stable() -> None:
    # A, B, C all score 0.9 -> stable sort keeps input order A, B, C.
    decision = compose_selection_decision(
        T, _models("A", "B", "C"), _scores(("A", 0.9), ("B", 0.9), ("C", 0.9)),
        UsageActuals(used_cents=0, limit_cents=1000),
    )
    ranks = [r.model_id for r in decision.recommendation]
    assert ranks == ["A", "B", "C"]
    assert decision.recommendation[0].rank == 1
    assert decision.recommendation[1].rank == 2


def test_unranked_models_have_no_score() -> None:
    decision = compose_selection_decision(
        T, _models("A", "B", "X"), _scores(("A", 0.9), ("B", 0.5)),  # X unbenchmarked
        UsageActuals(used_cents=0, limit_cents=1000),
    )
    assert "X" in decision.unranked_models
    assert len(decision.recommendation) == 2  # X excluded from ranking, NOT removed


def test_filters_scores_to_task() -> None:
    scores = [
        BenchScore("A", T, 0.9),
        BenchScore("B", T, 0.5),
        BenchScore("A", "summarize", 0.3),  # other task — ignored
    ]
    decision = compose_selection_decision(
        T, _models("A", "B"), scores, UsageActuals(used_cents=0, limit_cents=1000),
    )
    assert decision.recommendation[0].model_id == "A"
    assert decision.recommendation[0].score == 0.9


# --- budget bar [criterion 2] ----------------------------------------------


def test_budget_bar_ratio() -> None:
    decision = compose_selection_decision(
        T, _models("A"), _scores(("A", 0.9)), UsageActuals(used_cents=300, limit_cents=1000),
    )
    assert decision.budget_bar.ratio == pytest.approx(0.3)
    assert decision.budget_bar.over_limit is False


def test_budget_bar_ratio_none_when_limit_zero_unconfigured() -> None:
    decision = compose_selection_decision(
        T, _models("A"), _scores(("A", 0.9)), UsageActuals(used_cents=300, limit_cents=0),
    )
    assert decision.budget_bar.limit_cents == 0
    assert decision.budget_bar.ratio is None  # defer, never 0.0
    assert decision.budget_bar.over_limit is False  # no ceiling to be over


def test_budget_bar_over_limit_when_used_exceeds() -> None:
    decision = compose_selection_decision(
        T, _models("A"), _scores(("A", 0.9)), UsageActuals(used_cents=1200, limit_cents=1000),
    )
    assert decision.budget_bar.over_limit is True
    assert decision.budget_bar.ratio == pytest.approx(1.2)  # honest, unclamped


# --- projection [criterion 3, 5] -------------------------------------------


def test_projection_none_until_projected_cents_provided() -> None:
    decision = compose_selection_decision(
        T, _models("A"), _scores(("A", 0.9)), UsageActuals(used_cents=0, limit_cents=1000),
    )
    assert decision.projection is None  # defer — no model/token estimate yet


def test_projection_would_exceed_true() -> None:
    decision = compose_selection_decision(
        T, _models("A"), _scores(("A", 0.9)), UsageActuals(used_cents=900, limit_cents=1000),
        projected_cents=200,
    )
    assert decision.projection is not None
    assert decision.projection.projected_cents == 200
    assert decision.projection.post_projection_ratio == pytest.approx(1.1)
    assert decision.projection.would_exceed is True  # 900 + 200 > 1000


def test_projection_would_exceed_false_within_budget() -> None:
    decision = compose_selection_decision(
        T, _models("A"), _scores(("A", 0.9)), UsageActuals(used_cents=500, limit_cents=1000),
        projected_cents=200,
    )
    assert decision.projection is not None
    assert decision.projection.post_projection_ratio == pytest.approx(0.7)
    assert decision.projection.would_exceed is False


def test_projection_would_exceed_boundary_is_a_hit() -> None:
    # 800 + 200 == 1000 exactly -> NOT exceeding (> not >=).
    decision = compose_selection_decision(
        T, _models("A"), _scores(("A", 0.9)), UsageActuals(used_cents=800, limit_cents=1000),
        projected_cents=200,
    )
    assert decision.projection is not None
    assert decision.projection.would_exceed is False


def test_projection_no_phony_warning_when_limit_zero() -> None:
    # No configured ceiling -> cannot exceed it; ratio None (signals unconfigured).
    decision = compose_selection_decision(
        T, _models("A"), _scores(("A", 0.9)), UsageActuals(used_cents=300, limit_cents=0),
        projected_cents=200,
    )
    assert decision.projection is not None
    assert decision.projection.would_exceed is False
    assert decision.projection.post_projection_ratio is None


def test_projection_free_prompt_zero_cost() -> None:
    decision = compose_selection_decision(
        T, _models("A"), _scores(("A", 0.9)), UsageActuals(used_cents=500, limit_cents=1000),
        projected_cents=0,
    )
    assert decision.projection is not None
    assert decision.projection.would_exceed is False  # used already 500, +0 not over


def test_projection_free_prompt_but_already_over() -> None:
    decision = compose_selection_decision(
        T, _models("A"), _scores(("A", 0.9)), UsageActuals(used_cents=1100, limit_cents=1000),
        projected_cents=0,
    )
    assert decision.projection is not None
    assert decision.projection.would_exceed is True  # 1100 + 0 > 1000 (already over)


# --- advisory authority [criterion 7] + fit feedback [criterion 6] ---------


def test_authority_is_advisory() -> None:
    decision = compose_selection_decision(
        T, _models("A"), _scores(("A", 0.9)), UsageActuals(used_cents=0, limit_cents=1000),
    )
    assert decision.authority == "advisory"


def test_fit_feedback_attached_does_not_block() -> None:
    # A prior selection was suboptimal — attached as info, does not remove A.
    decision = compose_selection_decision(
        T, _models("A", "B"), _scores(("A", 0.9), ("B", 0.5)),
        UsageActuals(used_cents=0, limit_cents=1000),
        fit_feedback=ModelFitSummary(chosen_model="A", verdict="suboptimal_fit"),
    )
    assert decision.fit_feedback is not None
    assert decision.fit_feedback.verdict == "suboptimal_fit"
    # A still appears in the recommendation (feedback informs, never blocks).
    assert any(r.model_id == "A" for r in decision.recommendation)


def test_fit_feedback_none_by_default() -> None:
    decision = compose_selection_decision(
        T, _models("A"), _scores(("A", 0.9)), UsageActuals(used_cents=0, limit_cents=1000),
    )
    assert decision.fit_feedback is None


# --- validation [criterion 8 / honesty] ------------------------------------


def test_empty_task_id_raises() -> None:
    with pytest.raises(ModelSelectionError, match="task_id"):
        compose_selection_decision(
            "  ", _models("A"), _scores(("A", 0.9)), UsageActuals(0, 1000),
        )


def test_duplicate_model_id_raises() -> None:
    models = [ModelEntry("A", "A", "p"), ModelEntry("A", "A2", "p")]
    with pytest.raises(ModelSelectionError, match="duplicate model_id"):
        compose_selection_decision(T, models, _scores(("A", 0.9)), UsageActuals(0, 1000))


def test_score_out_of_range_raises() -> None:
    with pytest.raises(ModelSelectionError, match="must be in \\[0,1\\]"):
        compose_selection_decision(T, _models("A"), _scores(("A", 1.5)), UsageActuals(0, 1000))


def test_duplicate_score_for_model_task_raises() -> None:
    scores = [BenchScore("A", T, 0.9), BenchScore("A", T, 0.8), BenchScore("B", T, 0.5)]
    with pytest.raises(ModelSelectionError, match="duplicate score"):
        compose_selection_decision(T, _models("A", "B"), scores, UsageActuals(0, 1000))


def test_negative_used_cents_raises() -> None:
    with pytest.raises(ModelSelectionError, match="used_cents"):
        compose_selection_decision(T, _models("A"), _scores(("A", 0.9)), UsageActuals(-1, 1000))


def test_negative_limit_cents_raises() -> None:
    with pytest.raises(ModelSelectionError, match="limit_cents"):
        compose_selection_decision(T, _models("A"), _scores(("A", 0.9)), UsageActuals(0, -1))


def test_negative_projected_cents_raises() -> None:
    with pytest.raises(ModelSelectionError, match="projected_cents"):
        compose_selection_decision(
            T, _models("A"), _scores(("A", 0.9)), UsageActuals(0, 1000), projected_cents=-5,
        )


def test_empty_model_id_in_entry_raises() -> None:
    models = [ModelEntry("  ", "x", "p")]
    with pytest.raises(ModelSelectionError, match="model_id"):
        compose_selection_decision(T, models, _scores(("A", 0.9)), UsageActuals(0, 1000))


# --- purity / determinism [criterion 1] ------------------------------------


def test_decision_is_frozen_and_advisory() -> None:
    decision = compose_selection_decision(
        T, _models("A"), _scores(("A", 0.9)), UsageActuals(0, 1000),
    )
    assert dataclasses.is_dataclass(decision)
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.authority = "binding"  # type: ignore[misc]


def test_deterministic_same_inputs_same_decision() -> None:
    args = (
        T, _models("A", "B", "C"), _scores(("A", 0.9), ("B", 0.5), ("C", 0.8)),
        UsageActuals(used_cents=400, limit_cents=1000),
    )
    first = compose_selection_decision(*args, projected_cents=200)
    second = compose_selection_decision(*args, projected_cents=200)
    assert first == second


def test_notes_carry_provenance() -> None:
    decision = compose_selection_decision(
        T, _models("A"), _scores(("A", 0.9)), UsageActuals(0, 1000),
    )
    joined = " ".join(decision.notes)
    assert "model-selection decision-tree composition" in joined
    assert "advisory" in joined


def test_empty_models_yields_empty_recommendation() -> None:
    decision = compose_selection_decision(
        T, [], _scores(("A", 0.9)), UsageActuals(0, 1000),
    )
    assert decision.recommendation == ()
    assert decision.unranked_models == ()
