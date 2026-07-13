"""Tests for the model-cost-quality-frontier axis (Pareto efficiency per task).

Exercises: Pareto dominance, all five verdict states (unknown/single_candidate/
fully_efficient/single_survivor/partial_frontier), incomparable models on the frontier,
ties-on-both-axes (no domination), free-model (cost 0) domination, auditable dominators,
cheapest/highest-quality extremes, value_spread + zero-floor None, the dominated-count
partition invariant, validation, purity/immutability/determinism. Fixtures use bare
quality/cost pairs so dominance is hand-verifiable.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.model_cost_quality_frontier import (
    ModelCostQualityFrontierError,
    ModelTaskCostQuality,
    measure_model_cost_quality_frontier,
)


def _scores(*triples: tuple[str, float, float]) -> list[ModelTaskCostQuality]:
    return [
        ModelTaskCostQuality(model_id=m, quality_score=q, cost_per_call=c)
        for m, q, c in triples
    ]


# --- honesty: unknown + single_candidate ----------------------------------


def test_unknown_no_models() -> None:
    report = measure_model_cost_quality_frontier([], "task-A")
    assert report.model_count == 0
    assert report.frontier_size == 0
    assert report.frontier_share is None
    assert report.dominated_count == 0
    assert report.frontier_models == ()
    assert report.cheapest_frontier_model is None
    assert report.highest_quality_frontier_model is None
    assert report.value_spread is None
    assert report.verdict == "unknown"


def test_single_candidate_one_model() -> None:
    report = measure_model_cost_quality_frontier(_scores(("M1", 0.8, 0.5)), "task-A")
    assert report.model_count == 1
    assert report.frontier_size == 1
    assert report.frontier_share == pytest.approx(1.0)
    assert report.dominated_count == 0
    assert report.verdict == "single_candidate"
    assert report.cheapest_frontier_model == "M1"
    assert report.highest_quality_frontier_model == "M1"
    assert report.value_spread is None  # 1 member -> None


# --- core: fully_efficient (incomparable) ----------------------------------


def test_two_incomparable_fully_efficient() -> None:
    # M1 cheaper-lower-q, M2 pricier-higher-q -> neither dominates -> both on frontier
    report = measure_model_cost_quality_frontier(
        _scores(("M1", 0.8, 0.5), ("M2", 0.9, 1.0)), "task-A"
    )
    assert report.frontier_size == 2
    assert report.frontier_share == pytest.approx(1.0)
    assert report.dominated_count == 0
    assert report.dominated_models == ()
    assert report.verdict == "fully_efficient"
    assert report.cheapest_frontier_model == "M1"
    assert report.highest_quality_frontier_model == "M2"
    assert report.value_spread == pytest.approx(2.0)  # 1.0 / 0.5


def test_three_incomparable_all_efficient() -> None:
    # each trades off uniquely: low-q/cheap, mid, high-q/pricy
    report = measure_model_cost_quality_frontier(
        _scores(("M1", 0.7, 0.1), ("M2", 0.8, 0.5), ("M3", 0.9, 1.0)), "task-A"
    )
    assert report.frontier_size == 3
    assert report.verdict == "fully_efficient"
    assert report.dominated_count == 0


# --- core: single_survivor (one dominates all) -----------------------------


def test_single_survivor_one_dominates_all() -> None:
    # M1 higher quality AND cheaper than M2 -> M1 dominates M2
    report = measure_model_cost_quality_frontier(
        _scores(("M1", 0.9, 0.5), ("M2", 0.8, 1.0)), "task-A"
    )
    assert report.frontier_size == 1
    assert report.dominated_count == 1
    assert report.verdict == "single_survivor"
    assert report.frontier_models[0].model_id == "M1"
    assert report.dominated_models[0].model_id == "M2"
    assert report.dominated_models[0].dominating_model_ids == ("M1",)


def test_single_survivor_three_models() -> None:
    # M1 best quality AND cheapest -> dominates M2 and M3
    report = measure_model_cost_quality_frontier(
        _scores(("M1", 0.95, 0.1), ("M2", 0.8, 0.5), ("M3", 0.7, 0.3)), "task-A"
    )
    assert report.frontier_size == 1
    assert report.dominated_count == 2
    assert report.verdict == "single_survivor"
    assert {d.model_id for d in report.dominated_models} == {"M2", "M3"}
    for d in report.dominated_models:
        assert d.dominating_model_ids == ("M1",)


# --- core: partial_frontier -----------------------------------------------


def test_partial_frontier_one_dominated() -> None:
    # M1(0.9,0.5) dominates M2(0.9,1.0) [same q, cheaper]; M1 and M3(0.7,0.3) incomparable
    report = measure_model_cost_quality_frontier(
        _scores(("M1", 0.9, 0.5), ("M2", 0.9, 1.0), ("M3", 0.7, 0.3)), "task-A"
    )
    assert report.frontier_size == 2
    assert report.dominated_count == 1
    assert report.verdict == "partial_frontier"
    frontier_ids = {fm.model_id for fm in report.frontier_models}
    assert frontier_ids == {"M1", "M3"}
    assert report.dominated_models[0].model_id == "M2"
    assert report.dominated_models[0].dominating_model_ids == ("M1",)


def test_partial_frontier_multiple_dominators() -> None:
    # M1(0.9,0.5) and M2(0.85,0.3) both dominate M3(0.8,0.6); M1 and M2 incomparable
    report = measure_model_cost_quality_frontier(
        _scores(("M1", 0.9, 0.5), ("M2", 0.85, 0.3), ("M3", 0.8, 0.6)), "task-A"
    )
    # M1: q0.9 c0.5 ; M2: q0.85 c0.3 ; M3: q0.8 c0.6
    # M1 vs M3: M1 higher q, cheaper -> dominates M3
    # M2 vs M3: M2 higher q, cheaper -> dominates M3
    # M1 vs M2: M1 higher q but higher cost -> incomparable
    assert report.frontier_size == 2
    assert report.dominated_count == 1
    dom = report.dominated_models[0]
    assert dom.model_id == "M3"
    assert set(dom.dominating_model_ids) == {"M1", "M2"}


# --- ties on both axes (no spurious domination) ----------------------------


def test_identical_models_neither_dominates() -> None:
    # identical (q,c) -> strict edge on NEITHER -> both on frontier
    report = measure_model_cost_quality_frontier(
        _scores(("M1", 0.8, 0.5), ("M2", 0.8, 0.5)), "task-A"
    )
    assert report.frontier_size == 2
    assert report.dominated_count == 0
    assert report.verdict == "fully_efficient"


def test_same_cost_different_quality_dominates() -> None:
    # M1(0.9,0.5) vs M2(0.8,0.5): same cost, M1 higher q -> M1 dominates M2
    report = measure_model_cost_quality_frontier(
        _scores(("M1", 0.9, 0.5), ("M2", 0.8, 0.5)), "task-A"
    )
    assert report.frontier_size == 1
    assert report.dominated_models[0].model_id == "M2"


# --- free model (cost 0) --------------------------------------------------


def test_free_model_dominates_same_quality() -> None:
    # M1(0.8, 0.0) dominates M2(0.8, 0.5) [same q, cheaper]
    report = measure_model_cost_quality_frontier(
        _scores(("M1", 0.8, 0.0), ("M2", 0.8, 0.5)), "task-A"
    )
    assert report.frontier_size == 1
    assert report.frontier_models[0].model_id == "M1"
    assert report.value_spread is None  # min_cost 0.0 -> None


def test_free_model_incomparable_with_higher_quality() -> None:
    # M1(0.8, 0.0) and M2(0.9, 0.5): M1 cheaper-lower-q, M2 pricier-higher-q -> both frontier
    report = measure_model_cost_quality_frontier(
        _scores(("M1", 0.8, 0.0), ("M2", 0.9, 0.5)), "task-A"
    )
    assert report.frontier_size == 2
    assert report.verdict == "fully_efficient"
    assert report.value_spread is None  # min_cost 0.0 -> None despite 2 members


# --- frontier sorting + extremes ------------------------------------------


def test_frontier_sorted_by_quality_desc() -> None:
    report = measure_model_cost_quality_frontier(
        _scores(("Lo", 0.7, 0.1), ("Mid", 0.8, 0.4), ("Hi", 0.9, 1.0)), "task-A"
    )
    qualities = [fm.quality_score for fm in report.frontier_models]
    assert qualities == sorted(qualities, reverse=True)
    assert report.highest_quality_frontier_model == "Hi"
    assert report.cheapest_frontier_model == "Lo"


def test_partition_invariant_dominated_plus_frontier() -> None:
    # dominated_count + frontier_size == model_count always
    report = measure_model_cost_quality_frontier(
        _scores(("M1", 0.9, 0.5), ("M2", 0.8, 1.0), ("M3", 0.95, 2.0), ("M4", 0.6, 0.05)),
        "task-A",
    )
    assert report.dominated_count + report.frontier_size == report.model_count


# --- validation ------------------------------------------------------------


def test_empty_task_id_rejected() -> None:
    with pytest.raises(ModelCostQualityFrontierError):
        measure_model_cost_quality_frontier(_scores(("M1", 0.8, 0.5)), "  ")


@pytest.mark.parametrize("bad_q", [-0.01, 1.01])
def test_quality_out_of_range_rejected(bad_q: float) -> None:
    with pytest.raises(ModelCostQualityFrontierError):
        measure_model_cost_quality_frontier(_scores(("M1", bad_q, 0.5)), "task-A")


def test_negative_cost_rejected() -> None:
    with pytest.raises(ModelCostQualityFrontierError):
        measure_model_cost_quality_frontier(_scores(("M1", 0.8, -0.01)), "task-A")


def test_empty_model_id_rejected() -> None:
    with pytest.raises(ModelCostQualityFrontierError):
        measure_model_cost_quality_frontier(
            [ModelTaskCostQuality(model_id=" ", quality_score=0.8, cost_per_call=0.5)],
            "task-A",
        )


# --- purity / immutability / determinism -----------------------------------


def test_report_is_frozen() -> None:
    report = measure_model_cost_quality_frontier(_scores(("M1", 0.8, 0.5)), "task-A")
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.frontier_size = 99  # type: ignore[misc]


def test_deterministic_repeated_calls() -> None:
    scored = _scores(("M1", 0.9, 0.5), ("M2", 0.8, 1.0), ("M3", 0.95, 2.0))
    first = measure_model_cost_quality_frontier(scored, "task-A")
    second = measure_model_cost_quality_frontier(scored, "task-A")
    assert first == second


def test_authority_is_advisory() -> None:
    report = measure_model_cost_quality_frontier(_scores(("M1", 0.8, 0.5)), "task-A")
    assert report.authority == "advisory"


def test_single_candidate_distinct_from_unknown() -> None:
    """Binding honesty invariant: single_candidate (1.0) never collapses with unknown (None)."""
    solo = measure_model_cost_quality_frontier(_scores(("M1", 0.8, 0.5)), "task-A")
    empty = measure_model_cost_quality_frontier([], "task-A")
    assert solo.frontier_share == pytest.approx(1.0)
    assert solo.verdict == "single_candidate"
    assert empty.frontier_share is None
    assert empty.verdict == "unknown"


def test_task_id_stripped_and_carried() -> None:
    report = measure_model_cost_quality_frontier(_scores(("M1", 0.8, 0.5)), "  task-X  ")
    assert report.task_id == "task-X"
