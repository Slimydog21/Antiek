"""Tests for the competitive-position engine (study-the-competition ask).

Each load-bearing invariant in the module docstring is a named test. Run with:

    .venv/bin/python -m pytest tests/test_competitive_position.py -q \
        --noconftest --override-ini="addopts=" -p no:cacheprovider
"""

from __future__ import annotations

import copy

import pytest

from substrate.deep_research_quality.competitive_position import (
    AxisScore,
    CompetitivePositionError,
    CompetitivePositionReport,
    MeasuredQuality,
    assess_lever_coverage,
    build_competitive_position,
    compare_against_competitor,
)

AXES = (
    "citation_density",
    "grounding_completeness",
    "uncertainty_surfacing",
    "conflict_resolution",
    "synthesis_present",
)


def _quality(pid: str, scores: dict[str, tuple[float | None, str]]) -> MeasuredQuality:
    return MeasuredQuality(
        product_id=pid,
        axes=tuple(AxisScore(axis=a, score=s, basis=b) for a, (s, b) in scores.items()),
    )


def _antiek_full() -> MeasuredQuality:
    return _quality("antiek", {a: (0.9, "measured") for a in AXES})


# --------------------------------------------------------------------------- #
# Invariant 1: measured-vs-declared never conflated (the honesty keystone)
# --------------------------------------------------------------------------- #


def test_confirmed_lead_requires_both_measured():
    antiek = _quality("antiek", {"citation_density": (0.9, "measured")})
    comp_measured = _quality("comp", {"citation_density": (0.5, "measured")})
    comp_declared = _quality("comp", {"citation_density": (0.5, "declared")})
    r1 = compare_against_competitor(antiek=antiek, competitor=comp_measured, axes=["citation_density"])
    r2 = compare_against_competitor(antiek=antiek, competitor=comp_declared, axes=["citation_density"])
    assert r1.positions[0].confidence == "confirmed"
    assert r1.positions[0].position == "lead"
    assert r2.positions[0].confidence == "apparent"
    assert r2.positions[0].position == "lead"  # still a lead, but only apparent


def test_apparent_when_either_side_declared():
    antiek = _quality("antiek", {"citation_density": (0.9, "measured")})
    comp = _quality("comp", {"citation_density": (0.5, "declared")})
    r = compare_against_competitor(antiek=antiek, competitor=comp, axes=["citation_density"])
    assert r.positions[0].confidence == "apparent"


# --------------------------------------------------------------------------- #
# Invariant 2: unmeasured axis never produces a numeric verdict
# --------------------------------------------------------------------------- #


def test_unmeasured_antiek_axis_is_unknown():
    antiek = _quality("antiek", {"citation_density": (None, "measured")})
    comp = _quality("comp", {"citation_density": (0.5, "measured")})
    r = compare_against_competitor(antiek=antiek, competitor=comp, axes=["citation_density"])
    p = r.positions[0]
    assert p.position == "unknown"
    assert p.delta is None
    assert p.confidence == "unknown"


def test_missing_axis_treated_as_unmeasured():
    antiek = _quality("antiek", {"grounding_completeness": (0.9, "measured")})
    comp = _quality("comp", {"citation_density": (0.5, "measured")})
    r = compare_against_competitor(antiek=antiek, competitor=comp, axes=["citation_density"])
    assert r.positions[0].position == "unknown"
    assert r.positions[0].antiek_score is None


# --------------------------------------------------------------------------- #
# Invariant 3: delta signed and auditable
# --------------------------------------------------------------------------- #


def test_delta_is_antiek_minus_competitor():
    antiek = _quality("antiek", {"citation_density": (0.8, "measured")})
    comp = _quality("comp", {"citation_density": (0.5, "measured")})
    r = compare_against_competitor(antiek=antiek, competitor=comp, axes=["citation_density"])
    p = r.positions[0]
    assert abs(p.delta - 0.3) < 1e-9
    assert p.antiek_score == 0.8 and p.competitor_score == 0.5


# --------------------------------------------------------------------------- #
# Invariant 4: epsilon noise floor → parity
# --------------------------------------------------------------------------- #


def test_tie_within_epsilon_is_parity():
    antiek = _quality("antiek", {"citation_density": (0.5, "measured")})
    comp = _quality("comp", {"citation_density": (0.5, "measured")})
    r = compare_against_competitor(antiek=antiek, competitor=comp, axes=["citation_density"])
    assert r.positions[0].position == "parity"


def test_tiny_delta_within_epsilon_is_parity():
    antiek = _quality("antiek", {"citation_density": (0.5000000001, "measured")})
    comp = _quality("comp", {"citation_density": (0.5, "measured")})
    r = compare_against_competitor(antiek=antiek, competitor=comp, axes=["citation_density"])
    assert r.positions[0].position == "parity"


# --------------------------------------------------------------------------- #
# Invariant 5: no competitor → empty report flagged
# --------------------------------------------------------------------------- #


def test_no_competitors_yields_empty_flagged_report():
    report = build_competitive_position(
        antiek=_antiek_full(), competitors=[], axes=AXES
    )
    assert report.has_competitors is False
    assert report.comparisons == []
    assert any("no competitors" in n for n in report.notes)


# --------------------------------------------------------------------------- #
# Invariant 6: every position grounded in a reason
# --------------------------------------------------------------------------- #


def test_rationale_names_axis_scores_delta_basis():
    antiek = _quality("antiek", {"citation_density": (0.9, "measured")})
    comp = _quality("comp", {"citation_density": (0.4, "declared")})
    r = compare_against_competitor(antiek=antiek, competitor=comp, axes=["citation_density"])
    rat = r.positions[0].rationale
    assert "citation_density" in rat and "antiek=0.9" in rat
    assert "competitor=0.4" in rat and "apparent" in rat


# --------------------------------------------------------------------------- #
# Invariant 7: deterministic + pure
# --------------------------------------------------------------------------- #


def test_identical_inputs_produce_identical_report():
    antiek = _antiek_full()
    comps = [_quality("gemini", {"citation_density": (0.7, "declared")}),
             _quality("perplexity", {"citation_density": (0.8, "declared")})]
    r1 = build_competitive_position(antiek=antiek, competitors=comps, axes=AXES)
    r2 = build_competitive_position(antiek=copy.deepcopy(antiek),
                                    competitors=copy.deepcopy(comps), axes=AXES)
    assert r1 == r2


def test_comparisons_sorted_by_competitor_id():
    antiek = _antiek_full()
    comps = [
        _quality("zeta", {a: (0.5, "measured") for a in AXES}),
        _quality("alpha", {a: (0.5, "measured") for a in AXES}),
    ]
    r = build_competitive_position(antiek=antiek, competitors=comps, axes=AXES)
    assert [c.competitor_id for c in r.comparisons] == ["alpha", "zeta"]


# --------------------------------------------------------------------------- #
# Invariant 8: advisory only (frozen value)
# --------------------------------------------------------------------------- #


def test_report_is_frozen_and_advisory():
    report = build_competitive_position(antiek=_antiek_full(), competitors=[], axes=AXES)
    assert isinstance(report, CompetitivePositionReport)
    assert all("advisory" in n for n in report.notes[:1])
    with pytest.raises(AttributeError):
        report.comparisons = []  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Invariant 9: lever coverage surfaced, not fabricated
# --------------------------------------------------------------------------- #


def test_unmapped_lever_reported_not_synthesized():
    cov = assess_lever_coverage(
        levers=["search_retrieval", "citation_rigor"],
        axis_to_lever={"citation_density": "citation_rigor"},
        measured_axes=["citation_density"],
    )
    by_lever = {c.lever: c for c in cov}
    assert by_lever["search_retrieval"].state == "unmapped"
    assert by_lever["citation_rigor"].state == "mapped"
    assert by_lever["citation_rigor"].mapped_axes == ("citation_density",)


def test_mapped_but_unmeasured_lever_noted():
    cov = assess_lever_coverage(
        levers=["citation_rigor"],
        axis_to_lever={"citation_density": "citation_rigor", "grounding_completeness": "citation_rigor"},
        measured_axes=["citation_density"],  # grounding not measured
    )
    assert cov[0].state == "mapped"
    assert "citation_density" in cov[0].note


# --------------------------------------------------------------------------- #
# Invariant 10: competitor identity stable; overall confirmed-lead aggregation
# --------------------------------------------------------------------------- #


def test_overall_confirmed_lead_vs_all_competitors():
    antiek = _quality("antiek", {"citation_density": (0.95, "measured"), "synthesis_present": (0.9, "measured")})
    comp_a = _quality("a", {"citation_density": (0.5, "measured"), "synthesis_present": (0.95, "measured")})
    comp_b = _quality("b", {"citation_density": (0.6, "measured"), "synthesis_present": (0.8, "measured")})
    r = build_competitive_position(
        antiek=antiek, competitors=[comp_a, comp_b],
        axes=["citation_density", "synthesis_present"],
    )
    # Antiek confirmed-leads both on citation_density; not synthesis (loses to a)
    assert "citation_density" in r.overall_confirmed_lead_axes
    assert "synthesis_present" not in r.overall_confirmed_lead_axes


def test_confirmed_lead_not_counted_if_any_competitor_apparent():
    antiek = _quality("antiek", {"citation_density": (0.95, "measured")})
    comp_measured = _quality("a", {"citation_density": (0.5, "measured")})
    comp_declared = _quality("b", {"citation_density": (0.5, "declared")})
    r = build_competitive_position(
        antiek=antiek, competitors=[comp_measured, comp_declared], axes=["citation_density"]
    )
    # b is declared → not confirmed → no overall confirmed lead
    assert "citation_density" not in r.overall_confirmed_lead_axes


# --------------------------------------------------------------------------- #
# Validation + edge cases
# --------------------------------------------------------------------------- #


def test_invalid_basis_rejected():
    with pytest.raises(CompetitivePositionError):
        AxisScore(axis="x", score=0.5, basis="guessed")


def test_out_of_range_score_rejected():
    with pytest.raises(CompetitivePositionError):
        AxisScore(axis="x", score=1.5, basis="measured")


def test_self_comparison_rejected():
    antiek = _quality("antiek", {"citation_density": (0.9, "measured")})
    with pytest.raises(CompetitivePositionError):
        build_competitive_position(antiek=antiek, competitors=[antiek], axes=["citation_density"])


def test_duplicate_competitor_skipped():
    antiek = _antiek_full()
    comp = _quality("dup", {a: (0.5, "measured") for a in AXES})
    r = build_competitive_position(antiek=antiek, competitors=[comp, comp], axes=AXES)
    assert len(r.comparisons) == 1
    assert any("duplicate" in n for n in r.notes)


def test_negative_epsilon_rejected():
    antiek = _quality("antiek", {"citation_density": (0.9, "measured")})
    comp = _quality("comp", {"citation_density": (0.5, "measured")})
    with pytest.raises(CompetitivePositionError):
        compare_against_competitor(antiek=antiek, competitor=comp, axes=["citation_density"], epsilon=-0.1)


def test_lag_recorded_correctly():
    antiek = _quality("antiek", {"citation_density": (0.3, "measured")})
    comp = _quality("comp", {"citation_density": (0.9, "measured")})
    r = compare_against_competitor(antiek=antiek, competitor=comp, axes=["citation_density"])
    assert r.positions[0].position == "lag"
    assert r.lags == ("citation_density",)


def test_lead_count_property():
    antiek = _quality("antiek", {"citation_density": (0.9, "measured"), "grounding_completeness": (0.95, "measured")})
    comp = _quality("comp", {"citation_density": (0.5, "measured"), "grounding_completeness": (0.9, "declared")})
    r = compare_against_competitor(antiek=antiek, competitor=comp,
                                   axes=["citation_density", "grounding_completeness"])
    assert r.lead_count == 2  # one confirmed, one apparent
    assert r.confirmed_leads == ("citation_density",)
    assert r.apparent_leads == ("grounding_completeness",)


def test_score_for_missing_axis_returns_none():
    q = _quality("antiek", {"citation_density": (0.9, "measured")})
    assert q.score_for("nonexistent") is None
    assert q.score_for("citation_density") is not None


def test_end_to_end_with_levers():
    antiek = _quality("antiek", {
        "citation_density": (0.92, "measured"),
        "grounding_completeness": (0.88, "measured"),
        "uncertainty_surfacing": (0.7, "measured"),
        "conflict_resolution": (0.65, "measured"),
        "synthesis_present": (0.9, "measured"),
    })
    gemini = _quality("gemini", {
        "citation_density": (0.75, "declared"),
        "grounding_completeness": (0.7, "declared"),
        "uncertainty_surfacing": (0.5, "declared"),
        "conflict_resolution": (0.6, "declared"),
        "synthesis_present": (0.85, "declared"),
    })
    perplexity = _quality("perplexity", {
        "citation_density": (0.8, "measured"),
        "grounding_completeness": (0.78, "measured"),
        "uncertainty_surfacing": (0.4, "measured"),
        "conflict_resolution": (0.5, "measured"),
        "synthesis_present": (0.82, "measured"),
    })
    levers = ["search_retrieval", "citation_rigor", "source_coverage", "synthesis_quality", "cost_transparency"]
    axis_to_lever = {
        "citation_density": "citation_rigor",
        "grounding_completeness": "citation_rigor",
        "uncertainty_surfacing": "synthesis_quality",
        "conflict_resolution": "synthesis_quality",
        "synthesis_present": "synthesis_quality",
    }
    r = build_competitive_position(
        antiek=antiek, competitors=[gemini, perplexity], axes=list(AXES),
        levers=levers, axis_to_lever=axis_to_lever,
    )
    assert len(r.comparisons) == 2
    # search_retrieval and source_coverage and cost_transparency are unmapped
    unmapped = {c.lever for c in r.lever_coverage if c.state == "unmapped"}
    assert "search_retrieval" in unmapped
    assert "source_coverage" in unmapped
    assert "cost_transparency" in unmapped
    # citation_rigor mapped
    rigor = next(c for c in r.lever_coverage if c.lever == "citation_rigor")
    assert rigor.state == "mapped"
    # Antiek confirmed-leads perplexity on all 5 (both measured, antiek higher)
    perplexity_cmp = next(c for c in r.comparisons if c.competitor_id == "perplexity")
    assert len(perplexity_cmp.confirmed_leads) == 5
