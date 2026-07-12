"""Tests for the diff-aware weight composition substrate (ask #11 recursion glue).

Each load-bearing invariant in the module docstring is a named test. Run with:

    .venv/bin/python -m pytest tests/test_bench_weight_signal_composition.py -q \
        --noconftest --override-ini="addopts=" -p no:cacheprovider
"""

from __future__ import annotations

import copy

import pytest

from substrate.antiek_bench.weight_signal_composition import (
    _IMPROVED,
    _NEITHER,
    _NO_SIGNAL,
    _REGRESSED,
    DiffAwareWeightProposal,
    FamilyDirectionSignal,
    FamilyWeightRecord,
    ModelDelta,
    WeightCompositionError,
    aggregate_family_directions,
    compose_diff_aware_weights,
)

# --------------------------------------------------------------------------- #
# FamilyDirectionSignal.net_direction
# --------------------------------------------------------------------------- #


def test_net_direction_regressed_when_more_regressions():
    sig = FamilyDirectionSignal("fam", n_improved=1, n_regressed=3)
    assert sig.net_direction == _REGRESSED


def test_net_direction_improved_when_more_improvements():
    sig = FamilyDirectionSignal("fam", n_improved=4, n_regressed=1)
    assert sig.net_direction == _IMPROVED


def test_net_direction_neither_on_strict_tie():
    sig = FamilyDirectionSignal("fam", n_improved=2, n_regressed=2, n_unchanged=1)
    assert sig.net_direction == _NEITHER


def test_net_direction_no_signal_when_only_unknowns():
    sig = FamilyDirectionSignal("fam", n_unknown=2, n_new=1, n_dropped=1)
    assert sig.net_direction == _NO_SIGNAL


def test_net_direction_no_signal_when_empty():
    assert FamilyDirectionSignal("fam").net_direction == _NO_SIGNAL


def test_n_comparable_excludes_unknown_new_dropped():
    sig = FamilyDirectionSignal(
        "fam", n_improved=1, n_regressed=2, n_unchanged=3, n_unknown=4, n_new=5, n_dropped=6
    )
    assert sig.n_comparable == 6  # 1 + 2 + 3 only


# --------------------------------------------------------------------------- #
# aggregate_family_directions
# --------------------------------------------------------------------------- #


def test_aggregate_counts_each_direction_once():
    deltas = [
        ModelDelta("reading", _IMPROVED),
        ModelDelta("reading", _REGRESSED),
        ModelDelta("reading", _REGRESSED),
        ModelDelta("reading", "unchanged"),
        ModelDelta("reading", "unknown"),
        ModelDelta("graph", "new"),
        ModelDelta("graph", "dropped"),
    ]
    signals = aggregate_family_directions(deltas)
    assert [s.task_family for s in signals] == ["graph", "reading"]
    reading = next(s for s in signals if s.task_family == "reading")
    assert (reading.n_improved, reading.n_regressed, reading.n_unchanged) == (1, 2, 1)
    assert reading.n_unknown == 1
    graph = next(s for s in signals if s.task_family == "graph")
    assert graph.n_new == 1 and graph.n_dropped == 1
    assert graph.net_direction == _NO_SIGNAL


def test_aggregate_deterministic_sorted_order():
    deltas = [
        ModelDelta("zeta", _REGRESSED),
        ModelDelta("alpha", _IMPROVED),
        ModelDelta("mid", _REGRESSED),
    ]
    out1 = aggregate_family_directions(deltas)
    out2 = aggregate_family_directions(copy.deepcopy(deltas))
    assert out1 == out2
    assert [s.task_family for s in out1] == ["alpha", "mid", "zeta"]


def test_aggregate_rejects_unknown_direction():
    with pytest.raises(WeightCompositionError):
        aggregate_family_directions([ModelDelta("fam", "skyrocketed")])


def test_aggregate_rejects_empty_family_name():
    with pytest.raises(WeightCompositionError):
        aggregate_family_directions([ModelDelta("  ", _REGRESSED)])


# --------------------------------------------------------------------------- #
# Invariant 5: empty usage → incomplete, no invented weights
# --------------------------------------------------------------------------- #


def test_empty_usage_is_incomplete_with_no_weights():
    proposal = compose_diff_aware_weights(
        signals=[FamilyDirectionSignal("fam", n_regressed=3)],
        usage_mass={},
        week_id="2026-W28",
    )
    assert proposal.incomplete is True
    assert proposal.has_weights is False
    assert proposal.family_weights == []
    assert proposal.authority == "advisory"
    assert any("incomplete" in n for n in proposal.notes)


def test_non_numeric_usage_mass_ignored_not_invented():
    proposal = compose_diff_aware_weights(
        signals=[FamilyDirectionSignal("fam", n_regressed=1)],
        usage_mass={"fam": "lots"},  # type: ignore[dict-item]
    )
    assert proposal.incomplete is True
    assert proposal.family_weights == []
    assert any("non-numeric" in n for n in proposal.notes)


# --------------------------------------------------------------------------- #
# Invariant 6: weights sum to exactly 1.0 when non-empty
# --------------------------------------------------------------------------- #


def test_weights_sum_to_exactly_one():
    proposal = compose_diff_aware_weights(
        signals=[
            FamilyDirectionSignal("a", n_regressed=3),
            FamilyDirectionSignal("b", n_improved=2),
            FamilyDirectionSignal("c"),
        ],
        usage_mass={"a": 4.0, "b": 2.0, "c": 1.0},
        regression_boost=1.5,
    )
    total = sum(r.weight for r in proposal.family_weights)
    assert abs(total - 1.0) < 1e-9, f"sum={total}"


def test_single_family_weight_is_exactly_one():
    proposal = compose_diff_aware_weights(
        signals=[FamilyDirectionSignal("solo", n_regressed=2)],
        usage_mass={"solo": 3.0},
    )
    assert len(proposal.family_weights) == 1
    assert proposal.family_weights[0].weight == 1.0


# --------------------------------------------------------------------------- #
# Invariant 1 + 2: no diff signal → no boost; only net-regressed boosts
# --------------------------------------------------------------------------- #


def test_regressed_family_mass_doubles_with_default_boost():
    # Two families with EQUAL base mass; one regressed, one not.
    proposal = compose_diff_aware_weights(
        signals=[
            FamilyDirectionSignal("reg", n_regressed=2),
            FamilyDirectionSignal("flat"),
        ],
        usage_mass={"reg": 1.0, "flat": 1.0},
        regression_boost=1.0,  # → reg raw mass = 2.0, flat = 1.0
    )
    rec = {r.task_family: r for r in proposal.family_weights}
    assert rec["reg"].boosted is True
    assert rec["flat"].boosted is False
    assert rec["reg"].factor_applied == 2.0
    assert rec["flat"].factor_applied == 1.0
    # reg gets 2/3, flat gets 1/3
    assert abs(rec["reg"].weight - (2.0 / 3.0)) < 1e-8
    assert abs(rec["flat"].weight - (1.0 / 3.0)) < 1e-8


def test_improved_family_is_not_down_weighted_below_base_share():
    # Equal base mass; one improved, one plain. Improved must NOT be boosted, and
    # since nothing is boosted its share equals the plain one (1/2 each).
    proposal = compose_diff_aware_weights(
        signals=[
            FamilyDirectionSignal("imp", n_improved=3),
            FamilyDirectionSignal("plain"),
        ],
        usage_mass={"imp": 1.0, "plain": 1.0},
    )
    rec = {r.task_family: r for r in proposal.family_weights}
    assert rec["imp"].boosted is False
    assert rec["imp"].net_direction == _IMPROVED
    assert abs(rec["imp"].weight - 0.5) < 1e-9
    assert abs(rec["plain"].weight - 0.5) < 1e-9


def test_tie_is_not_boosted():
    proposal = compose_diff_aware_weights(
        signals=[FamilyDirectionSignal("tie", n_improved=2, n_regressed=2)],
        usage_mass={"tie": 1.0, "other": 1.0},
    )
    rec = {r.task_family: r for r in proposal.family_weights}
    assert rec["tie"].boosted is False
    assert rec["tie"].net_direction == _NEITHER


def test_strict_inequality_one_regressed_vs_one_improved_is_neither():
    # 1 regressed, 1 improved → tie → neither → no boost
    proposal = compose_diff_aware_weights(
        signals=[FamilyDirectionSignal("fam", n_improved=1, n_regressed=1)],
        usage_mass={"fam": 1.0, "other": 1.0},
    )
    rec = {r.task_family: r for r in proposal.family_weights}
    assert rec["fam"].boosted is False


# --------------------------------------------------------------------------- #
# Invariant 3: boost is multiplicative and auditable
# --------------------------------------------------------------------------- #


def test_audit_trail_carries_base_factor_and_direction():
    proposal = compose_diff_aware_weights(
        signals=[FamilyDirectionSignal("reg", n_regressed=4, n_improved=1)],
        usage_mass={"reg": 3.0},
        regression_boost=2.0,
    )
    rec = proposal.family_weights[0]
    assert rec.base_mass == 3.0
    assert rec.factor_applied == 3.0  # 1 + 2.0
    assert rec.boosted is True
    assert rec.net_direction == _REGRESSED
    assert rec.n_regressed == 4 and rec.n_improved == 1
    assert rec.weight == 1.0  # only family
    assert "up-weighted" in rec.rationale


def test_boost_zero_identifies_regressed_but_does_not_change_mass():
    proposal = compose_diff_aware_weights(
        signals=[
            FamilyDirectionSignal("reg", n_regressed=2),
            FamilyDirectionSignal("plain"),
        ],
        usage_mass={"reg": 1.0, "plain": 1.0},
        regression_boost=0.0,
    )
    rec = {r.task_family: r for r in proposal.family_weights}
    assert rec["reg"].net_direction == _REGRESSED
    assert rec["reg"].boosted is False
    assert rec["reg"].factor_applied == 1.0
    # equal shares, no boost
    assert abs(rec["reg"].weight - 0.5) < 1e-9


# --------------------------------------------------------------------------- #
# Invariant 4: unknowns never produce a boost
# --------------------------------------------------------------------------- #


def test_only_unknown_new_dropped_deltas_yield_no_signal_and_no_boost():
    deltas = [
        ModelDelta("fam", "unknown"),
        ModelDelta("fam", "new"),
        ModelDelta("fam", "dropped"),
        ModelDelta("fam", "unchanged"),
    ]
    signals = aggregate_family_directions(deltas)
    assert signals[0].net_direction == _NEITHER  # unchanged is comparable
    proposal = compose_diff_aware_weights(
        signals=signals, usage_mass={"fam": 1.0, "other": 1.0}
    )
    assert proposal.family_weights[0].boosted is False


def test_unknowns_do_not_outweigh_a_single_regression():
    # 1 regressed + many unknowns must still count as net regressed.
    deltas = [ModelDelta("fam", _REGRESSED)] + [
        ModelDelta("fam", "unknown") for _ in range(5)
    ]
    signals = aggregate_family_directions(deltas)
    assert signals[0].net_direction == _REGRESSED


# --------------------------------------------------------------------------- #
# Invariant 7: min_weight floor preserved
# --------------------------------------------------------------------------- #


def test_min_weight_floor_prevents_silent_zeroing():
    # reg gets a huge boost; flat would be ~0 without a floor.
    proposal = compose_diff_aware_weights(
        signals=[
            FamilyDirectionSignal("reg", n_regressed=5),
            FamilyDirectionSignal("flat"),
        ],
        usage_mass={"reg": 1.0, "flat": 1.0},
        regression_boost=1000.0,
        min_weight=0.1,
    )
    rec = {r.task_family: r for r in proposal.family_weights}
    assert rec["flat"].weight >= 0.1 - 1e-9
    total = rec["reg"].weight + rec["flat"].weight
    assert abs(total - 1.0) < 1e-9


def test_min_weight_infeasible_is_ignored():
    # 3 families × min_weight 0.5 = 1.5 > 1.0 → floor not applied (can't fit)
    proposal = compose_diff_aware_weights(
        signals=[FamilyDirectionSignal("a"), FamilyDirectionSignal("b"), FamilyDirectionSignal("c")],
        usage_mass={"a": 1.0, "b": 1.0, "c": 1.0},
        min_weight=0.5,
    )
    weights = {r.task_family: r.weight for r in proposal.family_weights}
    # Without a feasible floor, equal base mass → 1/3 each (within 8-decimal
    # rounding, so a 1e-7 tolerance — not 1e-9).
    for w in weights.values():
        assert abs(w - (1.0 / 3.0)) < 1e-7


# --------------------------------------------------------------------------- #
# Invariant 8: deterministic + pure
# --------------------------------------------------------------------------- #


def test_identical_inputs_produce_identical_proposals():
    signals = [
        FamilyDirectionSignal("a", n_regressed=2),
        FamilyDirectionSignal("b", n_improved=1),
    ]
    usage = {"a": 2.0, "b": 1.0}
    p1 = compose_diff_aware_weights(signals=signals, usage_mass=usage, regression_boost=1.3)
    p2 = compose_diff_aware_weights(signals=signals, usage_mass=usage, regression_boost=1.3)
    assert p1 == p2


# --------------------------------------------------------------------------- #
# Invariant 9: no family invented from one side alone
# --------------------------------------------------------------------------- #


def test_diff_family_without_usage_mass_is_not_weighted():
    proposal = compose_diff_aware_weights(
        signals=[FamilyDirectionSignal("only_in_diff", n_regressed=3)],
        usage_mass={"has_usage": 1.0},
    )
    families = {r.task_family for r in proposal.family_weights}
    assert families == {"has_usage"}
    assert proposal.unweighted_diff_families == ("only_in_diff",)
    assert any("no usage mass" in n for n in proposal.notes)


def test_usage_family_without_diff_signal_gets_no_boost_and_is_noted():
    proposal = compose_diff_aware_weights(
        signals=[FamilyDirectionSignal("in_both", n_regressed=2)],
        usage_mass={"in_both": 1.0, "usage_only": 1.0},
    )
    rec = {r.task_family: r for r in proposal.family_weights}
    assert rec["usage_only"].boosted is False
    assert rec["usage_only"].net_direction == _NO_SIGNAL
    assert any("no directional signal" in n for n in proposal.notes)


def test_boosted_families_tuple_is_sorted_and_complete():
    proposal = compose_diff_aware_weights(
        signals=[
            FamilyDirectionSignal("zeta", n_regressed=2),
            FamilyDirectionSignal("alpha", n_regressed=2),
            FamilyDirectionSignal("beta", n_improved=2),
        ],
        usage_mass={"zeta": 1.0, "alpha": 1.0, "beta": 1.0},
    )
    assert proposal.boosted_families == ("alpha", "zeta")


# --------------------------------------------------------------------------- #
# Invariant 10: regression_boost >= 0 (and min_weight >= 0) validated
# --------------------------------------------------------------------------- #


def test_negative_regression_boost_rejected():
    with pytest.raises(WeightCompositionError):
        compose_diff_aware_weights(
            signals=[FamilyDirectionSignal("fam", n_regressed=1)],
            usage_mass={"fam": 1.0},
            regression_boost=-0.1,
        )


def test_negative_min_weight_rejected():
    with pytest.raises(WeightCompositionError):
        compose_diff_aware_weights(
            signals=[FamilyDirectionSignal("fam")],
            usage_mass={"fam": 1.0},
            min_weight=-0.01,
        )


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #


def test_all_zero_base_mass_falls_back_to_uniform():
    proposal = compose_diff_aware_weights(
        signals=[FamilyDirectionSignal("a", n_regressed=2), FamilyDirectionSignal("b")],
        usage_mass={"a": 0.0, "b": 0.0},
    )
    weights = {r.task_family: r.weight for r in proposal.family_weights}
    assert abs(weights["a"] - 0.5) < 1e-9
    assert abs(weights["b"] - 0.5) < 1e-9
    assert any("uniform" in n for n in proposal.notes)


def test_blank_family_keys_in_usage_are_skipped():
    proposal = compose_diff_aware_weights(
        signals=[FamilyDirectionSignal("real", n_regressed=1)],
        usage_mass={"": 5.0, "  ": 5.0, "real": 1.0},
    )
    assert {r.task_family for r in proposal.family_weights} == {"real"}


def test_week_id_stripped_and_carried():
    proposal = compose_diff_aware_weights(
        signals=[FamilyDirectionSignal("fam")], usage_mass={"fam": 1.0}, week_id="  2026-W28  "
    )
    assert proposal.week_id == "2026-W28"


def test_largest_remainder_makes_sum_exact_with_many_families():
    proposal = compose_diff_aware_weights(
        signals=[FamilyDirectionSignal(f"f{i}") for i in range(7)],
        usage_mass={f"f{i}": float(i + 1) for i in range(7)},
    )
    total = sum(r.weight for r in proposal.family_weights)
    assert abs(total - 1.0) < 1e-9


def test_default_authority_is_advisory_and_notes_present():
    proposal = compose_diff_aware_weights(
        signals=[FamilyDirectionSignal("fam")], usage_mass={"fam": 1.0}
    )
    assert proposal.authority == "advisory"
    assert any("advisory" in n for n in proposal.notes)


def test_has_weights_property_reflects_population():
    empty = compose_diff_aware_weights(signals=[], usage_mass={})
    assert empty.has_weights is False
    full = compose_diff_aware_weights(
        signals=[FamilyDirectionSignal("fam")], usage_mass={"fam": 1.0}
    )
    assert full.has_weights is True


def test_records_are_frozen_dataclass_instances():
    proposal = compose_diff_aware_weights(
        signals=[FamilyDirectionSignal("fam")], usage_mass={"fam": 1.0}
    )
    rec = proposal.family_weights[0]
    assert isinstance(rec, FamilyWeightRecord)
    with pytest.raises(AttributeError):  # FrozenInstanceError is an AttributeError
        rec.weight = 0.5  # type: ignore[misc]  # frozen


def test_end_to_end_aggregate_then_compose():
    # The realistic path: model deltas → aggregate → compose.
    deltas = [
        ModelDelta("reading", _REGRESSED),
        ModelDelta("reading", _REGRESSED),
        ModelDelta("reading", _IMPROVED),
        ModelDelta("writing", _IMPROVED),
        ModelDelta("writing", _IMPROVED),
        ModelDelta("graph", "unknown"),
    ]
    signals = aggregate_family_directions(deltas)
    proposal = compose_diff_aware_weights(
        signals=signals,
        usage_mass={"reading": 3.0, "writing": 2.0, "graph": 1.0},
        regression_boost=1.0,
        min_weight=0.1,
    )
    rec = {r.task_family: r for r in proposal.family_weights}
    assert rec["reading"].boosted is True
    assert rec["writing"].boosted is False
    assert rec["writing"].net_direction == _IMPROVED
    assert rec["graph"].boosted is False
    total = sum(r.weight for r in proposal.family_weights)
    assert abs(total - 1.0) < 1e-9
    assert isinstance(proposal, DiffAwareWeightProposal)
