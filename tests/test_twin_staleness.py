"""Tests for the twin-staleness axis (ask #4 — recursive note-taker integrity).

Pure version arithmetic — integer offsets, ratios computed by hand.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.twin_staleness import (
    TwinStalenessError,
    TwinVersionInput,
    measure_twin_staleness,
)

# --- verdicts ---------------------------------------------------------------


def test_current_when_twin_at_source_version() -> None:
    report = measure_twin_staleness(TwinVersionInput(source_version=10, twin_generated_at_version=10))
    assert report.verdict == "current"
    assert report.version_offset == 0
    assert report.staleness_ratio == 0.0
    assert report.authority == "advisory"


def test_current_at_version_one() -> None:
    # A fresh source: version 1, twin generated against version 1 -> current.
    report = measure_twin_staleness(TwinVersionInput(source_version=1, twin_generated_at_version=1))
    assert report.verdict == "current"
    assert report.version_offset == 0


def test_stale_one_version_behind() -> None:
    report = measure_twin_staleness(TwinVersionInput(source_version=10, twin_generated_at_version=9))
    assert report.verdict == "stale"
    assert report.version_offset == 1
    assert report.staleness_ratio == pytest.approx(0.10)


def test_stale_several_versions_behind() -> None:
    report = measure_twin_staleness(TwinVersionInput(source_version=10, twin_generated_at_version=6))
    assert report.verdict == "stale"
    assert report.version_offset == 4
    assert report.staleness_ratio == pytest.approx(0.40)


def test_stale_critical_at_threshold_boundary_is_a_hit() -> None:
    # offset 5 == regenerate_threshold default 5 -> stale_critical (>= boundary).
    report = measure_twin_staleness(TwinVersionInput(source_version=10, twin_generated_at_version=5))
    assert report.verdict == "stale_critical"
    assert report.version_offset == 5
    assert report.staleness_ratio == pytest.approx(0.50)


def test_stale_critical_fully_behind() -> None:
    # Twin generated against v1, source now v10 -> offset 9, ratio 0.90.
    report = measure_twin_staleness(TwinVersionInput(source_version=10, twin_generated_at_version=1))
    assert report.verdict == "stale_critical"
    assert report.version_offset == 9
    assert report.staleness_ratio == pytest.approx(0.90)


# --- unknown (missing version data) ----------------------------------------


def test_unknown_when_source_version_none() -> None:
    report = measure_twin_staleness(TwinVersionInput(source_version=None, twin_generated_at_version=5))
    assert report.verdict == "unknown"
    assert report.version_offset is None
    assert report.staleness_ratio is None  # defer, never 0.0


def test_unknown_when_twin_generated_at_none() -> None:
    report = measure_twin_staleness(TwinVersionInput(source_version=10, twin_generated_at_version=None))
    assert report.verdict == "unknown"
    assert report.version_offset is None
    assert report.staleness_ratio is None


def test_unknown_when_both_none() -> None:
    report = measure_twin_staleness(TwinVersionInput(source_version=None, twin_generated_at_version=None))
    assert report.verdict == "unknown"


# --- staleness_ratio normalisation (comparability) -------------------------


def test_staleness_ratio_normalises_across_ages() -> None:
    # Same offset (2) on different-age sources -> different ratios.
    young = measure_twin_staleness(TwinVersionInput(source_version=4, twin_generated_at_version=2))
    old = measure_twin_staleness(TwinVersionInput(source_version=100, twin_generated_at_version=98))
    assert young.version_offset == 2
    assert old.version_offset == 2
    assert young.staleness_ratio == 0.5  # 2/4 — far behind a young source
    assert old.staleness_ratio == pytest.approx(0.02)  # 2/100 — barely behind an old source
    assert young.staleness_ratio is not None and old.staleness_ratio is not None
    assert young.staleness_ratio > old.staleness_ratio  # normalised comparability


# --- custom regenerate threshold -------------------------------------------


def test_custom_threshold_promotes_to_critical() -> None:
    # offset 3 -> stale at default threshold 5, stale_critical at threshold 2.
    versions = TwinVersionInput(source_version=10, twin_generated_at_version=7)
    assert measure_twin_staleness(versions).verdict == "stale"
    assert measure_twin_staleness(versions, regenerate_threshold=2).verdict == "stale_critical"


def test_threshold_boundary_at_custom_value() -> None:
    # threshold 3: offset 3 == threshold -> stale_critical (>= boundary).
    versions = TwinVersionInput(source_version=10, twin_generated_at_version=7)
    assert measure_twin_staleness(versions, regenerate_threshold=3).verdict == "stale_critical"


# --- validation (load-bearing invariants) ----------------------------------


def test_twin_generated_exceeds_source_raises() -> None:
    # A twin generated against a FUTURE version is a recording error.
    with pytest.raises(TwinStalenessError, match="cannot exceed"):
        measure_twin_staleness(TwinVersionInput(source_version=5, twin_generated_at_version=8))


def test_nonpositive_source_version_raises() -> None:
    with pytest.raises(TwinStalenessError, match="source_version"):
        measure_twin_staleness(TwinVersionInput(source_version=0, twin_generated_at_version=0))


def test_nonpositive_twin_generated_raises() -> None:
    with pytest.raises(TwinStalenessError, match="twin_generated_at_version"):
        measure_twin_staleness(TwinVersionInput(source_version=5, twin_generated_at_version=0))


def test_nonpositive_regenerate_threshold_raises() -> None:
    with pytest.raises(TwinStalenessError, match="regenerate_threshold"):
        measure_twin_staleness(
            TwinVersionInput(source_version=10, twin_generated_at_version=5), regenerate_threshold=0
        )


# --- purity / determinism ---------------------------------------------------


def test_report_is_frozen_and_advisory() -> None:
    report = measure_twin_staleness(TwinVersionInput(source_version=10, twin_generated_at_version=8))
    assert report.authority == "advisory"
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.verdict = "tampered"  # type: ignore[misc]


def test_deterministic_same_inputs_same_report() -> None:
    versions = TwinVersionInput(source_version=10, twin_generated_at_version=4)
    first = measure_twin_staleness(versions)
    second = measure_twin_staleness(versions)
    assert first == second


def test_notes_carry_provenance() -> None:
    report = measure_twin_staleness(TwinVersionInput(source_version=10, twin_generated_at_version=4))
    joined = " ".join(report.notes)
    assert "twin-staleness" in joined
    assert "verdict stale" in joined
    assert "version_offset 6" in joined
