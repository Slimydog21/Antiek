"""Tests for the platform-surface coverage source (ask #11 structure-loop activation).

Each load-bearing invariant in the module docstring is a named test. Run with:

    .venv/bin/python -m pytest tests/test_bench_surface_coverage.py -q \
        --noconftest --override-ini="addopts=" -p no:cacheprovider
"""

from __future__ import annotations

import copy

import pytest

from substrate.antiek_bench.surface_coverage import (
    PlatformSurface,
    SurfaceCoverageReport,
    SurfaceSignal,
    _slugify,
    derive_uncovered_surface_signals,
)

# --------------------------------------------------------------------------- #
# _slugify (deterministic task-id derivation)
# --------------------------------------------------------------------------- #


def test_slugify_lowercases_and_dashes_non_alnum():
    assert _slugify("Arxiv Ingest!") == "arxiv-ingest"


def test_slugify_collapses_runs_and_strips():
    assert _slugify("  Multiple   Words!!  ") == "multiple-words"


def test_slugify_empty_yields_empty():
    assert _slugify("   ") == ""


def test_slugify_deterministic():
    assert _slugify("Midnight-Oil") == _slugify(copy.copy("Midnight-Oil"))


# --------------------------------------------------------------------------- #
# Invariant 2: no surfaces → no signals
# --------------------------------------------------------------------------- #


def test_no_declared_surfaces_yields_no_signals():
    report = derive_uncovered_surface_signals(
        declared_surfaces=[], existing_task_ids=["acquisition::arxiv"]
    )
    assert report.signals == []
    assert report.has_signals is False


def test_no_existing_tasks_means_all_surfaces_signal():
    report = derive_uncovered_surface_signals(
        declared_surfaces=[
            PlatformSurface("arxiv-ingest", "acquisition"),
            PlatformSurface("mo-launch", "scheduling"),
        ],
        existing_task_ids=[],
    )
    assert len(report.signals) == 2
    task_ids = {s.proposed_task_id for s in report.signals}
    assert task_ids == {"acquisition::arxiv-ingest", "scheduling::mo-launch"}


# --------------------------------------------------------------------------- #
# Invariant 1: a signal fires ONLY for a genuinely-uncovered surface
# --------------------------------------------------------------------------- #


def test_covered_surface_produces_no_signal():
    report = derive_uncovered_surface_signals(
        declared_surfaces=[
            PlatformSurface("arxiv-ingest", "acquisition"),
            PlatformSurface("substack-ingest", "acquisition"),
        ],
        existing_task_ids=["acquisition::arxiv-ingest"],
    )
    task_ids = {s.proposed_task_id for s in report.signals}
    assert task_ids == {"acquisition::substack-ingest"}
    assert "arxiv-ingest" in report.covered_surface_ids
    assert "substack-ingest" not in report.covered_surface_ids


def test_covered_surface_ids_recorded_noted():
    report = derive_uncovered_surface_signals(
        declared_surfaces=[PlatformSurface("a", "fam")],
        existing_task_ids=["fam::a"],
    )
    assert report.signals == []
    assert report.covered_surface_ids == ("a",)
    assert any("already covered" in n for n in report.notes)


# --------------------------------------------------------------------------- #
# Invariant 3: dedup by proposed_task_id
# --------------------------------------------------------------------------- #


def test_two_surfaces_collapsing_to_one_task_id_dedup():
    # "Arxiv Ingest" and "arxiv-ingest" slug to the same task id.
    report = derive_uncovered_surface_signals(
        declared_surfaces=[
            PlatformSurface("Arxiv Ingest", "acquisition"),
            PlatformSurface("arxiv-ingest", "acquisition"),
        ],
        existing_task_ids=[],
    )
    assert len(report.signals) == 1
    sig = report.signals[0]
    assert sig.proposed_task_id == "acquisition::arxiv-ingest"
    # both source surface ids named in the rationale
    assert "Arxiv Ingest" in sig.rationale
    assert "arxiv-ingest" in sig.rationale


# --------------------------------------------------------------------------- #
# Invariant 4: proposed_task_id is deterministic {family}::{slug(surface_id)}
# --------------------------------------------------------------------------- #


def test_task_id_format_matches_registry_convention():
    report = derive_uncovered_surface_signals(
        declared_surfaces=[PlatformSurface("Deep Research!", "quality")],
        existing_task_ids=[],
    )
    assert report.signals[0].proposed_task_id == "quality::deep-research"


def test_same_inputs_produce_identical_reports():
    surfaces = [PlatformSurface("x", "fam"), PlatformSurface("y", "fam")]
    r1 = derive_uncovered_surface_signals(
        declared_surfaces=surfaces, existing_task_ids=["fam::z"]
    )
    r2 = derive_uncovered_surface_signals(
        declared_surfaces=copy.deepcopy(surfaces), existing_task_ids=["fam::z"]
    )
    assert r1 == r2


# --------------------------------------------------------------------------- #
# Invariant 5: malformed surfaces skipped, not fabricated
# --------------------------------------------------------------------------- #


def test_empty_family_skipped_with_note():
    report = derive_uncovered_surface_signals(
        declared_surfaces=[
            PlatformSurface("has-surface", ""),
            PlatformSurface("good", "fam"),
        ],
        existing_task_ids=[],
    )
    assert {s.proposed_task_id for s in report.signals} == {"fam::good"}
    assert len(report.skipped) == 1
    assert any("empty family" in s for s in report.skipped)
    assert any("malformed" in n for n in report.notes)


def test_empty_surface_id_skipped_with_note():
    report = derive_uncovered_surface_signals(
        declared_surfaces=[PlatformSurface("   ", "fam")],
        existing_task_ids=[],
    )
    assert report.signals == []
    assert any("empty surface_id" in s for s in report.skipped)


def test_malformed_not_coerced_into_placeholder_family():
    report = derive_uncovered_surface_signals(
        declared_surfaces=[PlatformSurface("orphan", "")],
        existing_task_ids=[],
    )
    # No signal, and no placeholder "general::orphan" fabricated.
    assert report.signals == []
    assert all("general" not in s.proposed_task_id for s in report.signals)


# --------------------------------------------------------------------------- #
# Invariant 6: deterministic + pure, sorted output
# --------------------------------------------------------------------------- #


def test_signals_emitted_in_sorted_family_task_order():
    report = derive_uncovered_surface_signals(
        declared_surfaces=[
            PlatformSurface("zeta", "zzz"),
            PlatformSurface("alpha", "aaa"),
            PlatformSurface("mid", "mmm"),
        ],
        existing_task_ids=[],
    )
    ids = [s.proposed_task_id for s in report.signals]
    assert ids == sorted(ids)
    assert ids == ["aaa::alpha", "mmm::mid", "zzz::zeta"]


# --------------------------------------------------------------------------- #
# Invariant 7: advisory only (output is a pure report; no mutation possible)
# --------------------------------------------------------------------------- #


def test_report_is_frozen_and_advisory():
    report = derive_uncovered_surface_signals(
        declared_surfaces=[PlatformSurface("a", "fam")], existing_task_ids=[]
    )
    assert isinstance(report, SurfaceCoverageReport)
    assert all("advisory" in n for n in report.notes[:1])
    with pytest.raises(AttributeError):
        report.signals = []  # type: ignore[misc]  # frozen


def test_description_carried_into_rationale_when_present():
    report = derive_uncovered_surface_signals(
        declared_surfaces=[PlatformSurface("arxiv", "acquisition", "arXiv paper ingest")],
        existing_task_ids=[],
    )
    assert "arXiv paper ingest" in report.signals[0].rationale


def test_signal_shape_matches_platform_surface_signal_contract():
    # The fields #1843's PlatformSurfaceSignal expects must all be present.
    report = derive_uncovered_surface_signals(
        declared_surfaces=[PlatformSurface("x", "fam")], existing_task_ids=[]
    )
    sig = report.signals[0]
    assert isinstance(sig, SurfaceSignal)
    assert sig.family == "fam"
    assert sig.proposed_task_id == "fam::x"
    assert isinstance(sig.rationale, str) and sig.rationale
    # prompt/scoring are optional seeds (None by default — operator may revise)
    assert sig.prompt is None
    assert sig.scoring is None


def test_existing_task_id_whitespace_normalized():
    report = derive_uncovered_surface_signals(
        declared_surfaces=[PlatformSurface("a", "fam")],
        existing_task_ids=["  fam::a  "],
    )
    assert report.signals == []
    assert report.covered_surface_ids == ("a",)


def test_end_to_end_growth_as_platform_expands():
    # Week 1: bench covers acquisition::arxiv.
    existing = ["acquisition::arxiv"]
    week1 = derive_uncovered_surface_signals(
        declared_surfaces=[PlatformSurface("arxiv", "acquisition")],
        existing_task_ids=existing,
    )
    assert week1.signals == []  # covered
    # Week 2: platform adds substack → uncovered signal fires.
    week2 = derive_uncovered_surface_signals(
        declared_surfaces=[
            PlatformSurface("arxiv", "acquisition"),
            PlatformSurface("substack", "acquisition"),
        ],
        existing_task_ids=existing,
    )
    assert {s.proposed_task_id for s in week2.signals} == {"acquisition::substack"}
