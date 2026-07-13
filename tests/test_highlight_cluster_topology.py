"""Tests for the highlight cluster-topology axis (ask #2).

Every fixture is hand-counted: cluster counts, singletons, and scatter coefficients
are verified by inspection before assertions are written.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.highlight_cluster_topology import (
    ClusterSpan,
    HighlightClusterTopologyReport,
    measure_highlight_cluster_topology,
)

# ---------------------------------------------------------------------------
# Base cases.
# ---------------------------------------------------------------------------


def test_no_highlights_is_unknown() -> None:
    report = measure_highlight_cluster_topology([])
    assert report.verdict == "unknown"
    assert report.cluster_count is None
    assert report.singleton_count is None
    assert report.scatter_coefficient is None
    assert report.mean_cluster_size is None
    assert report.cluster_spans == ()
    assert report.authority == "advisory"


def test_single_highlight_is_base_case() -> None:
    report = measure_highlight_cluster_topology([0.5])
    assert report.verdict == "single_highlight"
    assert report.highlight_count == 1
    assert report.cluster_count == 1
    assert report.singleton_count == 1
    assert report.singleton_fraction == pytest.approx(1.0)
    assert report.mean_cluster_size == pytest.approx(1.0)
    assert report.largest_cluster_size == 1


def test_single_distinct_from_unknown() -> None:
    assert measure_highlight_cluster_topology([]).verdict == "unknown"
    assert measure_highlight_cluster_topology([0.5]).verdict == "single_highlight"


# ---------------------------------------------------------------------------
# Clustered — highlights bunch into contiguous runs.
# ---------------------------------------------------------------------------


def test_three_adjacent_highlights_form_one_cluster() -> None:
    # gaps: 0.01, 0.01 — all within default 0.05 threshold -> 1 cluster.
    report = measure_highlight_cluster_topology([0.30, 0.31, 0.32])
    assert report.cluster_count == 1
    assert report.singleton_count == 0
    assert report.singleton_fraction == pytest.approx(0.0)
    assert report.mean_cluster_size == pytest.approx(3.0)
    assert report.largest_cluster_size == 3
    assert report.scatter_coefficient == pytest.approx(0.0)
    assert report.verdict == "clustered"


def test_two_clusters_both_multi_mark() -> None:
    # cluster A: 0.10, 0.12, 0.14 (gaps 0.02); gap to next 0.30; cluster B: 0.50, 0.52
    report = measure_highlight_cluster_topology([0.10, 0.12, 0.14, 0.50, 0.52])
    assert report.cluster_count == 2
    assert report.singleton_count == 0
    assert report.scatter_coefficient == pytest.approx(0.0)
    assert report.verdict == "clustered"
    assert report.largest_cluster_size == 3


# ---------------------------------------------------------------------------
# Scattered — isolated singletons across the document.
# ---------------------------------------------------------------------------


def test_widely_spaced_singletons_are_scattered() -> None:
    # 5 highlights spread across the doc with gaps >> 0.05 -> 5 singletons.
    report = measure_highlight_cluster_topology([0.1, 0.3, 0.5, 0.7, 0.9])
    assert report.cluster_count == 5
    assert report.singleton_count == 5
    assert report.singleton_fraction == pytest.approx(1.0)
    assert report.scatter_coefficient == pytest.approx(1.0)
    assert report.mean_cluster_size == pytest.approx(1.0)
    assert report.verdict == "scattered"


def test_mostly_singletons_one_pair_is_scattered() -> None:
    # 5 highlights: 4 singletons + 1 pair -> scatter = 4/5 = 0.80 >= 0.60 -> scattered.
    report = measure_highlight_cluster_topology([0.1, 0.3, 0.50, 0.51, 0.8])
    assert report.cluster_count == 4  # [0.1],[0.3],[0.50,0.51],[0.8]
    assert report.singleton_count == 3  # [0.1],[0.3],[0.8]
    assert report.scatter_coefficient == pytest.approx(3 / 5)
    assert report.verdict == "scattered"


# ---------------------------------------------------------------------------
# Mixed topology.
# ---------------------------------------------------------------------------


def test_mixed_topology_clusters_and_singletons() -> None:
    # 10 highlights: 2 clusters of 3 each + 4 singletons.
    # scatter = 4/10 = 0.40 -> between 0.20 and 0.60 -> mixed.
    report = measure_highlight_cluster_topology(
        [0.10, 0.11, 0.12, 0.30, 0.50, 0.51, 0.52, 0.70, 0.85, 0.95]
    )
    assert report.cluster_count == 6  # [3],[1],[3],[1],[1],[1]
    assert report.singleton_count == 4
    assert report.scatter_coefficient == pytest.approx(0.40)
    assert report.verdict == "mixed_topology"


def test_mixed_at_boundary_scattered_threshold() -> None:
    # 5 highlights, 3 singletons -> scatter 0.60 == scattered_threshold -> scattered (>=).
    report = measure_highlight_cluster_topology(
        [0.10, 0.11, 0.50, 0.70, 0.90]
    )
    assert report.singleton_count == 3  # [0.50],[0.70],[0.90]
    assert report.scatter_coefficient == pytest.approx(0.60)
    assert report.verdict == "scattered"


# ---------------------------------------------------------------------------
# Cluster-span auditability + gap threshold.
# ---------------------------------------------------------------------------


def test_cluster_spans_sorted_by_size_desc() -> None:
    report = measure_highlight_cluster_topology(
        [0.10, 0.11, 0.50, 0.51, 0.52]
    )
    sizes = [cs.size for cs in report.cluster_spans]
    assert sizes == [3, 2]
    big = report.cluster_spans[0]
    assert big.start_position == pytest.approx(0.50)
    assert big.end_position == pytest.approx(0.52)


def test_gap_threshold_boundary_inclusive() -> None:
    # gap exactly 0.05 == threshold -> same cluster (<=).
    report = measure_highlight_cluster_topology([0.10, 0.15])
    assert report.cluster_count == 1


def test_custom_gap_threshold_splits_clusters() -> None:
    # gap 0.03: one cluster at default 0.05; two clusters at strict 0.02.
    positions = [0.10, 0.13]
    assert measure_highlight_cluster_topology(positions).cluster_count == 1
    strict = measure_highlight_cluster_topology(positions, cluster_gap_threshold=0.02)
    assert strict.cluster_count == 2


# ---------------------------------------------------------------------------
# Edge integrity — clamping + dedup + out-of-order.
# ---------------------------------------------------------------------------


def test_out_of_range_positions_clamped() -> None:
    report = measure_highlight_cluster_topology([-0.2, 0.5, 1.5])
    assert report.highlight_count == 3  # clamped to 0.0, 0.5, 1.0
    spans_start = sorted(cs.start_position for cs in report.cluster_spans)
    assert spans_start == [pytest.approx(0.0), pytest.approx(0.5), pytest.approx(1.0)]


def test_duplicate_positions_merged() -> None:
    report = measure_highlight_cluster_topology([0.5, 0.5, 0.5])
    assert report.highlight_count == 1  # three identical marks -> one highlight
    assert report.verdict == "single_highlight"


def test_unsorted_input_sorted_internally() -> None:
    report = measure_highlight_cluster_topology([0.9, 0.1, 0.5])
    assert report.cluster_count == 3  # sorted to [0.1, 0.5, 0.9]


# ---------------------------------------------------------------------------
# Threshold validation + custom thresholds.
# ---------------------------------------------------------------------------


def test_cluster_gap_threshold_out_of_range_raises() -> None:
    with pytest.raises(ValueError, match="cluster_gap_threshold"):
        measure_highlight_cluster_topology([0.5], cluster_gap_threshold=0.0)
    with pytest.raises(ValueError, match="cluster_gap_threshold"):
        measure_highlight_cluster_topology([0.5], cluster_gap_threshold=1.5)


def test_scattered_below_clustered_raises() -> None:
    with pytest.raises(ValueError, match="scattered_threshold"):
        measure_highlight_cluster_topology(
            [0.5], scattered_threshold=0.10, clustered_threshold=0.20
        )


def test_custom_thresholds_reclassify() -> None:
    # scatter 0.40: mixed at defaults; scattered at 0.35; clustered at 0.50.
    positions = [0.10, 0.11, 0.12, 0.30, 0.50, 0.51, 0.52, 0.70, 0.85, 0.95]
    assert measure_highlight_cluster_topology(positions).verdict == "mixed_topology"
    assert (
        measure_highlight_cluster_topology(positions, scattered_threshold=0.35).verdict
        == "scattered"
    )
    assert (
        measure_highlight_cluster_topology(
            positions, clustered_threshold=0.50, scattered_threshold=0.80
        ).verdict
        == "clustered"
    )


# ---------------------------------------------------------------------------
# Determinism + immutability + authority + report type.
# ---------------------------------------------------------------------------


def test_report_is_frozen() -> None:
    report = measure_highlight_cluster_topology([0.1, 0.11])
    with pytest.raises(FrozenInstanceError):
        report.verdict = "scattered"  # type: ignore[misc]


def test_deterministic_output() -> None:
    positions = [0.9, 0.1, 0.5, 0.51, 0.12]
    assert measure_highlight_cluster_topology(positions) == measure_highlight_cluster_topology(
        positions
    )


def test_report_is_highlight_cluster_topology_report_instance() -> None:
    report = measure_highlight_cluster_topology([0.1, 0.11])
    assert isinstance(report, HighlightClusterTopologyReport)
    assert all(isinstance(cs, ClusterSpan) for cs in report.cluster_spans)
    assert report.authority == "advisory"


def test_notes_nonempty_when_measurable() -> None:
    report = measure_highlight_cluster_topology([0.10, 0.11, 0.12])
    assert len(report.notes) >= 3
    assert all(isinstance(n, str) and n for n in report.notes)
    assert any("orthogonal" in n.lower() for n in report.notes)
    assert any("contiguity" in n.lower() for n in report.notes)
