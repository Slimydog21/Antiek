"""Tests for substrate/merge_provenance_traceability.py — merge provenance quality."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.merge_provenance_traceability import (
    MergedInsight,
    measure_merge_provenance_traceability,
)

PARENTS = ("inst_a", "inst_b", "inst_c")


def _ins(parent: str | None, iid: str = "") -> MergedInsight:
    return MergedInsight(insight_id=iid or f"i_{parent}", parent_instance_id=parent)


# --- unknown ---------------------------------------------------------------


def test_unknown_no_insights() -> None:
    r = measure_merge_provenance_traceability([], PARENTS)
    assert r.verdict == "unknown"
    assert r.traceability_rate is None
    assert r.synthesis_rate is None
    assert r.no_op_parent_ids == tuple(sorted(PARENTS))
    assert any("no insights" in n for n in r.notes)


def test_unknown_no_declared_parents() -> None:
    r = measure_merge_provenance_traceability([_ins("inst_a")], [])
    assert r.verdict == "unknown"
    assert r.traceability_rate is None
    assert any("no declared parents" in n for n in r.notes)


def test_unknown_never_fabricates_generative() -> None:
    assert measure_merge_provenance_traceability([], PARENTS).verdict != "generative"


# --- misattributed (integrity failure) ------------------------------------


def test_misattributed_unresolvable_parent() -> None:
    r = measure_merge_provenance_traceability(
        [_ins("inst_a"), _ins("ghost")], PARENTS
    )
    assert r.verdict == "misattributed"
    assert r.misattributed_count == 1
    assert r.unresolved_claims[0].insight_id == "i_ghost"
    assert r.unresolved_claims[0].claimed_parent_id == "ghost"


def test_misattributed_dominates_provenance_lost() -> None:
    # All-unresolvable -> misattributed wins (not provenance_lost).
    r = measure_merge_provenance_traceability(
        [_ins("ghost1"), _ins("ghost2")], PARENTS
    )
    assert r.verdict == "misattributed"


def test_misattributed_audit_carries_claimed_id() -> None:
    r = measure_merge_provenance_traceability([_ins("x", "i9")], PARENTS)
    assert r.verdict == "misattributed"
    assert r.unresolved_claims == (
        type(r.unresolved_claims[0])(insight_id="i9", claimed_parent_id="x"),
    )


# --- provenance_lost (all synthesized) ------------------------------------


def test_provenance_lost_all_synthesized() -> None:
    r = measure_merge_provenance_traceability(
        [_ins(None, "s1"), _ins(None, "s2")], PARENTS
    )
    assert r.verdict == "provenance_lost"
    assert r.synthesized_count == 2
    assert r.traceable_count == 0
    assert r.synthesis_rate == pytest.approx(1.0)
    assert r.traceability_rate == pytest.approx(0.0)
    assert r.no_op_parent_ids == tuple(sorted(PARENTS))


def test_synthesized_alone_is_not_failure() -> None:
    # Keystne: a SINGLE synthesized insight amid traceable ones is generative, not
    # lost — synthesized is the merge's purpose, not a failure.
    r = measure_merge_provenance_traceability(
        [_ins("inst_a"), _ins(None, "synth")], PARENTS
    )
    assert r.verdict == "generative"
    assert r.synthesized_count == 1


# --- fully_traceable (pure inheritance) -----------------------------------


def test_fully_traceable_all_resolve() -> None:
    r = measure_merge_provenance_traceability(
        [_ins("inst_a"), _ins("inst_b"), _ins("inst_c")], PARENTS
    )
    assert r.verdict == "fully_traceable"
    assert r.synthesized_count == 0
    assert r.traceability_rate == pytest.approx(1.0)


def test_fully_traceable_distinct_from_unknown() -> None:
    assert measure_merge_provenance_traceability([], PARENTS).verdict == "unknown"
    assert (
        measure_merge_provenance_traceability([_ins("inst_a")], PARENTS).verdict
        == "fully_traceable"
    )


# --- generative (the healthy mix) -----------------------------------------


def test_generative_mix() -> None:
    r = measure_merge_provenance_traceability(
        [_ins("inst_a"), _ins("inst_b"), _ins(None, "synth1"), _ins(None, "synth2")],
        PARENTS,
    )
    assert r.verdict == "generative"
    assert r.traceable_count == 2
    assert r.synthesized_count == 2
    assert r.traceability_rate == pytest.approx(0.5)
    assert r.synthesis_rate == pytest.approx(0.5)


def test_generative_distinct_from_fully_traceable() -> None:
    # Adding one synthesized to a fully-traceable set flips to generative.
    base = [_ins("inst_a"), _ins("inst_b")]
    assert measure_merge_provenance_traceability(base, PARENTS).verdict == "fully_traceable"
    assert (
        measure_merge_provenance_traceability(base + [_ins(None, "s")], PARENTS).verdict
        == "generative"
    )


# --- no-op parents + contributor tracking ---------------------------------


def test_no_op_parents_surfaced() -> None:
    # Only inst_a contributes; inst_b, inst_c are no-ops.
    r = measure_merge_provenance_traceability(
        [_ins("inst_a"), _ins("inst_a")], PARENTS
    )
    assert r.contributing_parent_ids == ("inst_a",)
    assert r.no_op_parent_ids == ("inst_b", "inst_c")
    assert any("contributed nothing" in n for n in r.notes)


def test_contributing_parents_sorted() -> None:
    r = measure_merge_provenance_traceability(
        [_ins("inst_c"), _ins("inst_a"), _ins("inst_b")], PARENTS
    )
    assert r.contributing_parent_ids == ("inst_a", "inst_b", "inst_c")
    assert r.no_op_parent_ids == ()


# --- duplicate parent ids in declared set ---------------------------------


def test_duplicate_declared_parents_deduped() -> None:
    r = measure_merge_provenance_traceability(
        [_ins("inst_a")], ("inst_a", "inst_a", "inst_b")
    )
    assert r.verdict == "fully_traceable"
    assert r.no_op_parent_ids == ("inst_b",)


# --- rates -----------------------------------------------------------------


def test_rates_none_only_when_unknown() -> None:
    assert measure_merge_provenance_traceability([], PARENTS).traceability_rate is None
    assert (
        measure_merge_provenance_traceability([_ins(None)], PARENTS).traceability_rate
        == pytest.approx(0.0)
    )


def test_rates_sum_to_one() -> None:
    # traceable + synthesized + misattributed = total -> rates sum to <= 1.
    r = measure_merge_provenance_traceability(
        [_ins("inst_a"), _ins(None, "s"), _ins("ghost")], PARENTS
    )
    assert r.traceability_rate is not None and r.synthesis_rate is not None
    total_rate = r.traceability_rate + r.synthesis_rate  # misattributed excluded
    assert total_rate == pytest.approx(2 / 3)


# --- immutability ----------------------------------------------------------


def test_report_frozen() -> None:
    r = measure_merge_provenance_traceability([_ins("inst_a")], PARENTS)
    with pytest.raises(FrozenInstanceError):
        r.verdict = "tampered"  # type: ignore[misc]


def test_merged_insight_frozen() -> None:
    ins = MergedInsight(insight_id="x", parent_instance_id="inst_a")
    with pytest.raises(FrozenInstanceError):
        ins.parent_instance_id = "inst_b"  # type: ignore[misc]
