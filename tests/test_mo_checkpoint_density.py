"""Tests for substrate/mo_checkpoint_density.py — checkpoint cadence quality."""

from __future__ import annotations

import math
from dataclasses import FrozenInstanceError

import pytest

from substrate.mo_checkpoint_density import (
    Checkpoint,
    measure_checkpoint_density,
)


def _cps(*pairs: tuple[str, float]) -> list[Checkpoint]:
    return [Checkpoint(checkpoint_id=cid, progress=p) for cid, p in pairs]


# --- unknown ---------------------------------------------------------------


def test_unknown_when_no_checkpoints() -> None:
    r = measure_checkpoint_density([])
    assert r.verdict == "unknown"
    assert r.checkpoint_count == 0
    assert r.gaps == ()
    assert r.max_gap is None
    assert r.mean_gap is None
    assert r.min_gap is None
    assert r.gap_spread is None
    assert r.authority == "advisory"
    assert any("not measurable" in n for n in r.notes)


def test_unknown_does_not_fabricate_balanced() -> None:
    # One cannot claim "balanced cadence" with zero checkpoints — that is unknown.
    r = measure_checkpoint_density([])
    assert r.verdict != "balanced"


# --- sparse ----------------------------------------------------------------


def test_sparse_single_checkpoint_at_start() -> None:
    # One checkpoint at 0.0: gaps [0,0]=0 and [0,1.0]=1.0 -> max blast radius 1.0.
    r = measure_checkpoint_density(_cps(("cp0", 0.0)))
    assert r.verdict == "sparse"
    assert r.checkpoint_count == 1
    assert r.max_gap == pytest.approx(1.0)
    assert r.mean_gap == pytest.approx(0.5)


def test_sparse_large_unprotected_span() -> None:
    # Checkpoints at 0.1, 0.2 -> trailing span [0.2, 1.0] = 0.8 dominates.
    r = measure_checkpoint_density(_cps(("a", 0.1), ("b", 0.2)))
    assert r.verdict == "sparse"
    assert r.max_gap == pytest.approx(0.8)


def test_sparse_boundary_inclusive() -> None:
    # max_gap exactly == sparse_threshold (0.40) IS sparse (>= is inclusive).
    # Checkpoints at 0.4 and 0.8 -> gaps 0.4, 0.4, 0.2 -> max 0.4 exactly.
    r = measure_checkpoint_density(_cps(("a", 0.4), ("b", 0.8)))
    assert r.verdict == "sparse"
    assert r.max_gap == pytest.approx(0.40)


# --- balanced --------------------------------------------------------------


def test_balanced_evenly_spaced() -> None:
    r = measure_checkpoint_density(
        _cps(("a", 0.2), ("b", 0.4), ("c", 0.6), ("d", 0.8))
    )
    assert r.verdict == "balanced"
    assert r.checkpoint_count == 4
    assert r.max_gap == pytest.approx(0.2)
    assert r.min_gap == pytest.approx(0.2)
    assert r.gap_spread == pytest.approx(0.0)


def test_balanced_is_measured_not_default() -> None:
    # balanced requires >= 1 checkpoint AND measured-within-bounds; not the default.
    assert measure_checkpoint_density([]).verdict == "unknown"
    assert (
        measure_checkpoint_density(
            _cps(("a", 0.2), ("b", 0.4), ("c", 0.6), ("d", 0.8))
        ).verdict
        == "balanced"
    )


# --- excessive -------------------------------------------------------------


def test_excessive_many_checkpoints() -> None:
    # 99 checkpoints at 0.01..0.99 -> 100 gaps of ~0.01 -> mean ~0.01 <= 0.02.
    cps = [Checkpoint(str(i), round(i * 0.01, 2)) for i in range(1, 100)]
    r = measure_checkpoint_density(cps)
    assert r.verdict == "excessive"
    assert r.checkpoint_count == 99
    assert r.mean_gap is not None and r.mean_gap <= 0.02
    assert r.max_gap is not None and r.max_gap < 0.40


# --- both sparse AND excessive (clustered) --------------------------------


def test_clustered_both_sparse_and_excessive() -> None:
    # 50 checkpoints clustered in [0.5, 0.549] -> leading gap 0.5 (sparse) AND
    # mean ~1/51 <= 0.02 (excessive). sparse wins; notes flag the clustering.
    cps = [
        Checkpoint(f"c{i}", round(0.5 + i * 0.001, 3)) for i in range(50)
    ]
    r = measure_checkpoint_density(cps)
    assert r.verdict == "sparse"
    assert r.max_gap is not None and r.max_gap >= 0.40
    assert r.mean_gap is not None and r.mean_gap <= 0.02
    assert any("clustered" in n for n in r.notes)


# --- dedup -----------------------------------------------------------------


def test_duplicate_progress_deduped_and_counted() -> None:
    # Two checkpoints at 0.5 (redundant) plus one at 0.25 -> dedupe keeps distinct.
    r = measure_checkpoint_density(
        _cps(("dup1", 0.5), ("real", 0.25), ("dup2", 0.5))
    )
    assert r.checkpoint_count == 2
    assert r.duplicate_checkpoint_count == 1
    assert any("redundant" in n for n in r.notes)


# --- provenance / gaps -----------------------------------------------------


def test_gap_bounding_ids_carried() -> None:
    r = measure_checkpoint_density(_cps(("a", 0.2), ("b", 0.6)))
    # gaps: [0,0.2], [0.2,0.6], [0.6,1.0]
    assert len(r.gaps) == 3
    leading, middle, trailing = r.gaps
    assert leading.preceding_checkpoint_id is None
    assert leading.following_checkpoint_id == "a"
    assert middle.preceding_checkpoint_id == "a"
    assert middle.following_checkpoint_id == "b"
    assert trailing.preceding_checkpoint_id == "b"
    assert trailing.following_checkpoint_id is None


def test_gaps_sorted_by_start() -> None:
    # Pass checkpoints out of order; gaps must still be sorted ascending.
    r = measure_checkpoint_density(_cps(("b", 0.8), ("a", 0.2)))
    starts = [g.start_progress for g in r.gaps]
    assert starts == sorted(starts)


def test_min_gap_and_spread() -> None:
    # Checkpoints 0.1, 0.9 -> gaps 0.1, 0.8, 0.1 -> min 0.1, spread 0.7.
    r = measure_checkpoint_density(_cps(("a", 0.1), ("b", 0.9)))
    assert r.min_gap == pytest.approx(0.1)
    assert r.gap_spread == pytest.approx(0.7)


def test_mean_gap_identity() -> None:
    # For a full-span partition, gaps sum to 1.0 -> mean == 1/(count+1).
    r = measure_checkpoint_density(_cps(("a", 0.2), ("b", 0.4), ("c", 0.6), ("d", 0.8)))
    assert r.checkpoint_count == 4
    assert r.mean_gap == pytest.approx(1.0 / (4 + 1))


# --- custom thresholds -----------------------------------------------------


def test_custom_sparse_threshold_flags_balanced_as_sparse() -> None:
    # Even spacing 0.2 is balanced under default 0.40, but sparse under 0.10.
    r = measure_checkpoint_density(
        _cps(("a", 0.2), ("b", 0.4), ("c", 0.6), ("d", 0.8)),
        sparse_threshold=0.10,
    )
    assert r.verdict == "sparse"


def test_custom_dense_threshold_flags_few_as_excessive() -> None:
    # 4 checkpoints (mean 0.2) is not excessive under default 0.02, but is under 0.20.
    r = measure_checkpoint_density(
        _cps(("a", 0.2), ("b", 0.4), ("c", 0.6), ("d", 0.8)),
        dense_threshold=0.20,
    )
    assert r.verdict == "excessive"


# --- validation ------------------------------------------------------------


def test_invalid_sparse_threshold_zero() -> None:
    with pytest.raises(ValueError, match="sparse_threshold"):
        measure_checkpoint_density([], sparse_threshold=0.0)


def test_invalid_sparse_threshold_over_one() -> None:
    with pytest.raises(ValueError, match="sparse_threshold"):
        measure_checkpoint_density([], sparse_threshold=1.5)


def test_invalid_dense_threshold_zero() -> None:
    with pytest.raises(ValueError, match="dense_threshold"):
        measure_checkpoint_density([], dense_threshold=0.0)


def test_invalid_progress_negative() -> None:
    with pytest.raises(ValueError, match="outside"):
        measure_checkpoint_density(_cps(("bad", -0.1)))


def test_invalid_progress_over_one() -> None:
    with pytest.raises(ValueError, match="outside"):
        measure_checkpoint_density(_cps(("bad", 1.5)))


def test_nan_progress_rejected() -> None:
    with pytest.raises(ValueError, match="NaN"):
        measure_checkpoint_density(_cps(("bad", math.nan)))


# --- immutability ----------------------------------------------------------


def test_report_is_frozen() -> None:
    r = measure_checkpoint_density(_cps(("a", 0.5)))
    with pytest.raises(FrozenInstanceError):
        r.verdict = "tampered"  # type: ignore[misc]


def test_checkpoint_at_endpoints() -> None:
    # Checkpoints at 0.0 and 1.0 but nothing between -> huge mid gap -> sparse.
    r = measure_checkpoint_density(_cps(("start", 0.0), ("end", 1.0)))
    assert r.verdict == "sparse"
    assert r.max_gap == pytest.approx(1.0)
    assert r.checkpoint_count == 2
