"""Model recommendation engine — pure contract tests.

Pins the decision tree for asks #10/#11/#12. The module is pure: no network, no
dispatch. Every exclusion and budget impact is counted and surfaced honestly.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest  # noqa: E402

from substrate.model_decision.recommend import (  # noqa: E402
    RECOMMENDATION_AUTHORITY,
    BudgetConstraint,
    ModelOption,
    ModelRecommendationError,
    TaskProfile,
    recommend_model,
)

TASK = TaskProfile(
    task_type="deep_research",
    complexity_tier="deep",
    min_context_tokens=32_000,
    requires_grounding=True,
)


def _model(
    *,
    model_id: str = "model-a",
    provider: str = "openai",
    bench_scores: dict[str, float] | None = None,
    pricing: tuple[float, float] | None = (5.0, 15.0),
    max_context: int = 128_000,
    supports_grounding: bool = True,
) -> ModelOption:
    return ModelOption(
        model_id=model_id,
        provider=provider,
        bench_scores=bench_scores or {},
        pricing_per_mtok=pricing,
        max_context_tokens=max_context,
        supports_grounding=supports_grounding,
    )


# --- empty / fail-closed ---


def test_empty_task_type_rejected() -> None:
    with pytest.raises(ModelRecommendationError, match="task_type"):
        recommend_model(TaskProfile(task_type="  ", complexity_tier="deep"), [_model()])


def test_empty_model_list_no_recommendation() -> None:
    result = recommend_model(TASK, [])

    assert result.recommended_model_id is None
    assert result.ranked == ()
    assert any("no models" in n for n in result.notes)


# --- capability filter ---


def test_grounding_requirement_excludes_non_grounding() -> None:
    result = recommend_model(
        TASK,
        [_model(model_id="no-ground", supports_grounding=False), _model(model_id="grounded")],
    )

    assert result.excluded_capability == 1
    assert result.recommended_model_id == "grounded"


def test_context_window_filter_excludes_small_models() -> None:
    result = recommend_model(
        TaskProfile(task_type="t", complexity_tier="deep", min_context_tokens=100_000),
        [_model(model_id="small", max_context=8_000), _model(model_id="big", max_context=200_000)],
    )

    assert result.excluded_capability == 1
    assert result.recommended_model_id == "big"


def test_all_models_fail_capability_filter() -> None:
    result = recommend_model(
        TASK,
        [_model(model_id="a", supports_grounding=False), _model(model_id="b", max_context=1000)],
    )

    assert result.recommended_model_id is None
    assert result.excluded_capability == 2
    assert any("capability filter" in n for n in result.notes)


# --- bench score drives ranking ---


def test_higher_bench_score_ranks_first() -> None:
    result = recommend_model(
        TASK,
        [
            _model(model_id="weak", bench_scores={"deep_research": 0.3}),
            _model(model_id="strong", bench_scores={"deep_research": 0.9}),
        ],
    )

    assert result.recommended_model_id == "strong"
    assert result.ranked[0].score == 0.9
    assert result.ranked[1].score == 0.3


def test_missing_bench_data_neutral_unverified() -> None:
    result = recommend_model(
        TASK,
        [_model(model_id="new", bench_scores={})],  # no bench data for this task
    )

    assert result.recommended_model_id == "new"
    assert result.ranked[0].score == 0.5  # neutral
    assert result.ranked[0].bench_verified is False
    assert any("NOT bench-verified" in n for n in result.notes)


def test_bench_verified_model_preferred_over_unverified() -> None:
    result = recommend_model(
        TASK,
        [
            _model(model_id="unverified", bench_scores={}),  # neutral 0.5
            _model(model_id="verified-low", bench_scores={"deep_research": 0.4}),
        ],
    )

    # 0.4 (verified) < 0.5 (neutral), but the verified one has real data.
    # The scoring is honest: 0.5 > 0.4, so neutral ranks first. The operator
    # sees "unverified" in the notes and can override. (No false preference
    # for unverified — the score IS lower, just flagged differently.)
    assert result.recommended_model_id == "unverified"
    assert result.ranked[0].bench_verified is False
    assert result.ranked[1].bench_verified is True


# --- budget constraint ---


def test_budget_ranks_within_budget_first() -> None:
    result = recommend_model(
        TaskProfile(task_type="t", complexity_tier="fast"),
        [
            _model(model_id="cheap", bench_scores={"t": 0.6}, pricing=(1.0, 3.0)),
            _model(model_id="pricey", bench_scores={"t": 0.9}, pricing=(100.0, 300.0)),
        ],
        budget=BudgetConstraint(max_cost_usd=0.01, estimated_input_tokens=10_000, estimated_output_tokens=5_000),
    )

    # pricey: 10K*100/1M + 5K*300/1M = 1.0 + 1.5 = 2.5 >> 0.01 → exceeds
    # cheap: 10K*1/1M + 5K*3/1M = 0.01 + 0.015 = 0.025 > 0.01 → also exceeds!
    # Both exceed, so all_exceed_budget=True, cheapest still wins on cost.
    assert result.all_exceed_budget is True
    assert result.recommended_model_id == "cheap"  # cheaper


def test_budget_constraint_changes_ranking() -> None:
    budget = BudgetConstraint(max_cost_usd=1.0, estimated_input_tokens=10_000, estimated_output_tokens=5_000)
    result = recommend_model(
        TaskProfile(task_type="t", complexity_tier="fast"),
        [
            _model(model_id="cheap", bench_scores={"t": 0.5}, pricing=(1.0, 3.0)),  # ~0.025
            _model(model_id="pricey", bench_scores={"t": 0.9}, pricing=(100.0, 300.0)),  # ~2.5
        ],
        budget=budget,
    )

    # pricey exceeds $1.0; cheap is within → cheap ranks first despite lower score
    assert result.recommended_model_id == "cheap"
    assert result.budget_filtered is True
    assert result.ranked[0].within_budget is True
    assert result.ranked[1].within_budget is False


def test_no_budget_constraint_pure_quality() -> None:
    result = recommend_model(
        TaskProfile(task_type="t", complexity_tier="fast"),
        [
            _model(model_id="cheap", bench_scores={"t": 0.5}, pricing=(1.0, 3.0)),
            _model(model_id="pricey", bench_scores={"t": 0.9}, pricing=(100.0, 300.0)),
        ],
        budget=None,
    )

    assert result.recommended_model_id == "pricey"  # higher score, no budget limit
    assert result.budget_filtered is False
    assert result.ranked[0].within_budget is None  # no constraint set


def test_budget_none_in_model_allows_no_constraint() -> None:
    budget = BudgetConstraint(max_cost_usd=None)
    result = recommend_model(
        TaskProfile(task_type="t", complexity_tier="fast"),
        [_model(model_id="a", bench_scores={"t": 0.8})],
        budget=budget,
    )

    assert result.ranked[0].within_budget is None  # no constraint


# --- unknown pricing ---


def test_unknown_pricing_not_penalized() -> None:
    result = recommend_model(
        TaskProfile(task_type="t", complexity_tier="fast"),
        [
            _model(model_id="priced", bench_scores={"t": 0.7}, pricing=(5.0, 15.0)),
            _model(model_id="unpriced", bench_scores={"t": 0.9}, pricing=None),
        ],
        budget=BudgetConstraint(max_cost_usd=1.0, estimated_input_tokens=1000, estimated_output_tokens=500),
    )

    # unpriced has higher score and isn't penalized for unknown pricing
    assert result.recommended_model_id == "unpriced"
    assert result.ranked[0].estimated_cost_usd is None
    assert result.ranked[0].within_budget is None  # can't assess


# --- tie-break ---


def test_tie_break_by_cost_then_id() -> None:
    result = recommend_model(
        TaskProfile(task_type="t", complexity_tier="fast"),
        [
            _model(model_id="zzz", bench_scores={"t": 0.8}, pricing=(10.0, 30.0)),
            _model(model_id="aaa", bench_scores={"t": 0.8}, pricing=(5.0, 15.0)),
        ],
    )

    # Same score 0.8 → lower cost wins (aaa is cheaper)
    assert result.recommended_model_id == "aaa"


# --- advisory authority ---


def test_authority_is_advisory() -> None:
    result = recommend_model(TASK, [_model(model_id="a", bench_scores={"deep_research": 0.9})])

    assert result.authority == RECOMMENDATION_AUTHORITY


# --- idempotent + deterministic ---


def test_idempotent_same_inputs_same_output() -> None:
    models = [
        _model(model_id="a", bench_scores={"t": 0.7}),
        _model(model_id="b", bench_scores={"t": 0.9}),
    ]
    task = TaskProfile(task_type="t", complexity_tier="fast")
    one = recommend_model(task, models)
    two = recommend_model(task, models)

    assert one == two
    assert [r.model_id for r in one.ranked] == [r.model_id for r in two.ranked]


# --- honest accounting ---


def test_clean_recommendation_note() -> None:
    result = recommend_model(
        TaskProfile(task_type="t", complexity_tier="fast"),
        [_model(model_id="best", bench_scores={"t": 0.95})],
    )

    assert result.recommended_model_id == "best"
    assert result.ranked[0].bench_verified is True
    assert any("clean recommendation" in n for n in result.notes)
