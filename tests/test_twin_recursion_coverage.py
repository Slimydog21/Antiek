"""Twin-recursion coverage — the universality invariant (ask #4).

Distinct from all twin-QUALITY axes: THIS measures whether every asset HAS a
twin (recursion completeness), not one twin's content quality.
"""

from __future__ import annotations

import pytest

from substrate.twin_recursion_coverage import (
    TwinBinding,
    TwinRecursionCoverageError,
    measure_twin_recursion_coverage,
)

# --- universality (the happy invariant) ----------------------------------- #


def test_every_asset_has_a_twin_is_universal() -> None:
    report = measure_twin_recursion_coverage(
        ["a1", "a2", "a3"],
        [
            TwinBinding(asset_id="a1", twin_id="t1"),
            TwinBinding(asset_id="a2", twin_id="t2"),
            TwinBinding(asset_id="a3", twin_id="t3"),
        ],
    )
    assert report.verdict == "universal"
    assert report.orphan_asset_count == 0
    assert report.twin_coverage_rate == 1.0
    assert report.binding_rate == 1.0
    assert report.dangling_twin_count == 0
    assert report.multi_bound_asset_count == 0
    assert report.authority == "advisory"


def test_one_asset_one_twin_universal() -> None:
    # One asset with its twin is universal (the invariant holds for the set).
    report = measure_twin_recursion_coverage(
        ["solo"], [TwinBinding(asset_id="solo", twin_id="twin")]
    )
    assert report.verdict == "universal"
    assert report.twin_coverage_rate == 1.0


# --- partial (the primary failure: orphan assets) ------------------------- #


def test_orphan_asset_is_partial() -> None:
    # a3 has no twin — the substrate has a hole.
    report = measure_twin_recursion_coverage(
        ["a1", "a2", "a3"],
        [
            TwinBinding(asset_id="a1", twin_id="t1"),
            TwinBinding(asset_id="a2", twin_id="t2"),
        ],
    )
    assert report.verdict == "partial"
    assert report.orphan_asset_count == 1
    assert report.orphan_asset_ids == ("a3",)
    assert report.twin_coverage_rate == pytest.approx(2 / 3)
    assert report.binding_rate == 1.0  # no dangling


def test_zero_coverage_is_real_partial_not_unknown() -> None:
    # Assets measured, NONE has a twin — measured absence, NOT unknown.
    report = measure_twin_recursion_coverage(["a1", "a2"], [])
    assert report.verdict == "partial"
    assert report.twin_coverage_rate == 0.0
    assert report.orphan_asset_ids == ("a1", "a2")


# --- unknown (defer when nothing to measure) ------------------------------ #


def test_zero_assets_is_unknown_never_fabricated() -> None:
    report = measure_twin_recursion_coverage([], [])
    assert report.verdict == "unknown"
    assert report.twin_coverage_rate is None
    assert report.binding_rate is None


def test_zero_assets_with_twins_still_unknown_and_twins_dangling() -> None:
    # No assets but twins declared: the twins dangle (point at nothing); the
    # coverage question is unknown (nothing to cover), but the leak is surfaced.
    report = measure_twin_recursion_coverage(
        [], [TwinBinding(asset_id="ghost", twin_id="t9")]
    )
    assert report.verdict == "unknown"
    assert report.twin_coverage_rate is None
    assert report.dangling_twin_count == 1
    assert report.dangling_twin_ids == ("t9",)


# --- binding_rate None only when no twins --------------------------------- #


def test_binding_rate_none_when_no_twins_but_assets_present() -> None:
    report = measure_twin_recursion_coverage(["a1"], [])
    assert report.verdict == "partial"
    assert report.binding_rate is None  # undefined over zero twins
    assert report.twin_count == 0


# --- dangling twins (integrity leak, separate from coverage) -------------- #


def test_dangling_twin_surfaced_not_collapsed_into_verdict() -> None:
    # Every real asset has a twin (universal), but an extra binding points at a
    # non-existent asset — a dangling twin. Coverage is universal; the leak is
    # a SEPARATE field, not collapsed into the verdict.
    report = measure_twin_recursion_coverage(
        ["a1"],
        [
            TwinBinding(asset_id="a1", twin_id="t1"),
            TwinBinding(asset_id="ghost", twin_id="t9"),
        ],
    )
    assert report.verdict == "universal"
    assert report.dangling_twin_count == 1
    assert report.dangling_twin_ids == ("t9",)
    assert report.binding_rate == pytest.approx(1 / 2)


# --- multi-bound assets (structural anomaly) ------------------------------ #


def test_multi_bound_asset_surfaced_separately() -> None:
    # a1 has TWO twins — the invariant is "a twin" singular. Coverage is
    # universal (a1 has a twin), but the anomaly is surfaced, not hidden.
    report = measure_twin_recursion_coverage(
        ["a1", "a2"],
        [
            TwinBinding(asset_id="a1", twin_id="t1a"),
            TwinBinding(asset_id="a1", twin_id="t1b"),
            TwinBinding(asset_id="a2", twin_id="t2"),
        ],
    )
    assert report.verdict == "universal"
    assert report.multi_bound_asset_count == 1
    assert report.multi_bound_asset_ids == ("a1",)
    assert report.twin_count == 3


# --- de-duplication ------------------------------------------------------- #


def test_duplicate_binding_pair_is_one_twin() -> None:
    # Listing the same (asset, twin) twice is one twin, NOT multi-bind.
    report = measure_twin_recursion_coverage(
        ["a1"],
        [
            TwinBinding(asset_id="a1", twin_id="t1"),
            TwinBinding(asset_id="a1", twin_id="t1"),
        ],
    )
    assert report.verdict == "universal"
    assert report.twin_count == 1
    assert report.multi_bound_asset_count == 0


# --- validation (fail-closed) -------------------------------------------- #


def test_blank_asset_id_rejected() -> None:
    with pytest.raises(TwinRecursionCoverageError, match="non-blank"):
        measure_twin_recursion_coverage(["a1", "  "], [])


def test_duplicate_asset_ids_in_input_rejected() -> None:
    with pytest.raises(TwinRecursionCoverageError, match="duplicate asset id"):
        measure_twin_recursion_coverage(["a1", "a1"], [])


def test_blank_binding_id_rejected() -> None:
    with pytest.raises(TwinRecursionCoverageError, match="non-blank"):
        measure_twin_recursion_coverage(
            ["a1"], [TwinBinding(asset_id="a1", twin_id="")]
        )


# --- determinism + partition --------------------------------------------- #


def test_output_is_sorted_and_deterministic() -> None:
    bindings = [
        TwinBinding(asset_id="a3", twin_id="t3"),
        TwinBinding(asset_id="a1", twin_id="t1"),
        TwinBinding(asset_id="a2", twin_id="t2"),
        TwinBinding(asset_id="zz", twin_id="tdang"),
    ]
    r1 = measure_twin_recursion_coverage(["a1", "a2", "a3"], bindings)
    r2 = measure_twin_recursion_coverage(["a3", "a2", "a1"], list(reversed(bindings)))
    # reordering inputs yields identical sorted output.
    assert r1 == r2
    assert r1.orphan_asset_ids == tuple(sorted(r1.orphan_asset_ids))
    assert r1.dangling_twin_ids == ("tdang",)


def test_counts_partition_consistently() -> None:
    # bound + orphan == asset_count; bound + dangling == twin_count.
    report = measure_twin_recursion_coverage(
        ["a1", "a2", "a3", "a4"],
        [
            TwinBinding(asset_id="a1", twin_id="t1"),
            TwinBinding(asset_id="a2", twin_id="t2"),
            TwinBinding(asset_id="nowhere", twin_id="td"),
        ],
    )
    assert report.verdict == "partial"
    bound_assets = report.asset_count - report.orphan_asset_count
    assert bound_assets + report.orphan_asset_count == report.asset_count
    bound_twins = report.twin_count - report.dangling_twin_count
    assert bound_twins + report.dangling_twin_count == report.twin_count
    assert report.twin_coverage_rate == pytest.approx(bound_assets / report.asset_count)
