"""Tests for the synthesis-grounding (conclusion-vs-evidence) axis.

Exercises the load-bearing invariants: grounding coverage of the synthesis over
the insights' vocabulary, the absent/withheld-synthesis honesty rules (None
never fabricated), the empty-evidence overreach case, the lexical-floor honesty
(stop-words stripped, no stemming), the overreach accountability surface, and
purity/immutability/determinism.

Fixtures use deliberate, countable vocabularies (no contractions/possessives so
apostrophe-splitting does not perturb term counts).
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.deep_research_quality.synthesis_grounding import (
    SynthesisGroundingReport,
    measure_synthesis_grounding,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ResearchArtifactBody,
)


def _artifact(
    insights: list[tuple[str, str]],
    *,
    synthesis_excerpt: str | None = None,
    synthesis_withheld: bool = False,
    investigation_id: str = "inv-test",
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question="the question",
        insights=[ArtifactInsight(node_id=nid, text=text) for nid, text in insights],
        synthesis_excerpt=synthesis_excerpt,
        synthesis_withheld=synthesis_withheld,
    )


# --- core grounding -------------------------------------------------------


def test_fully_grounded_synthesis_yields_one() -> None:
    # synthesis distinctive: model attention scales (3); insights cover all 3
    art = _artifact(
        [("i1", "the model uses attention"), ("i2", "it scales well")],
        synthesis_excerpt="the model attention scales",
    )
    report = measure_synthesis_grounding(art)
    assert report.grounding == pytest.approx(1.0)
    assert report.overreach_terms == ()
    assert report.synthesis_term_count == 3
    assert report.matched_term_count == 3


def test_partial_grounding_with_overreach() -> None:
    # synthesis distinctive: model attention scales cheaply (4)
    # insights support: model attention scales (3); "cheaply" unsupported
    art = _artifact(
        [("i1", "the model uses attention and scales well")],
        synthesis_excerpt="the model attention scales cheaply",
    )
    report = measure_synthesis_grounding(art)
    assert report.grounding == pytest.approx(3 / 4)
    assert report.overreach_terms == ("cheaply",)
    assert any("OVERREACH" in n for n in report.notes)


def test_ungrounded_synthesis_yields_zero() -> None:
    # synthesis distinctive: quantum gravity holography (3); insights about other things
    art = _artifact(
        [("i1", "supply chain logistics optimization")],
        synthesis_excerpt="quantum gravity holography",
    )
    report = measure_synthesis_grounding(art)
    assert report.grounding == pytest.approx(0.0)
    assert set(report.overreach_terms) == {"quantum", "gravity", "holography"}


def test_grounding_in_unit_interval() -> None:
    art = _artifact(
        [("i1", "alpha beta"), ("i2", "gamma")],
        synthesis_excerpt="alpha beta gamma delta epsilon",
    )
    report = measure_synthesis_grounding(art)
    assert report.grounding is not None and 0.0 <= report.grounding <= 1.0


# --- honesty rules: absent / withheld synthesis ---------------------------


def test_withheld_synthesis_yields_none() -> None:
    art = _artifact(
        [("i1", "model attention")],
        synthesis_excerpt="the model uses attention",
        synthesis_withheld=True,
    )
    report = measure_synthesis_grounding(art)
    assert report.grounding is None
    assert report.withheld is True
    assert report.overreach_terms == ()
    assert any("withheld" in n.lower() for n in report.notes)


def test_missing_synthesis_yields_none() -> None:
    art = _artifact([("i1", "model attention")], synthesis_excerpt=None)
    report = measure_synthesis_grounding(art)
    assert report.grounding is None
    assert report.withheld is False
    assert any("no synthesis" in n.lower() for n in report.notes)


def test_empty_string_synthesis_yields_none() -> None:
    art = _artifact([("i1", "model attention")], synthesis_excerpt="   ")
    report = measure_synthesis_grounding(art)
    assert report.grounding is None


def test_withheld_takes_precedence_over_empty_excerpt() -> None:
    # withheld=True with empty excerpt still defers (withheld is the explicit signal)
    art = _artifact([("i1", "model")], synthesis_excerpt="", synthesis_withheld=True)
    report = measure_synthesis_grounding(art)
    assert report.grounding is None
    assert report.withheld is True


# --- honesty rules: stop-words-only synthesis -----------------------------


def test_stop_words_only_synthesis_yields_none() -> None:
    art = _artifact(
        [("i1", "model attention")],
        synthesis_excerpt="the of a is was the",
    )
    report = measure_synthesis_grounding(art)
    assert report.grounding is None
    assert report.synthesis_term_count == 0
    assert any("no distinctive terms" in n.lower() for n in report.notes)


# --- honesty rules: empty evidence base -----------------------------------


def test_synthesis_with_no_insights_is_full_overreach() -> None:
    # synthesis has distinctive terms but NO insights exist -> rests on nothing.
    art = _artifact([], synthesis_excerpt="model attention scales")
    report = measure_synthesis_grounding(art)
    assert report.grounding == pytest.approx(0.0)
    assert set(report.overreach_terms) == {"model", "attention", "scales"}
    assert any("OVERREACH" in n for n in report.notes)


# --- lexical floor honesty ------------------------------------------------


def test_stop_words_stripped_from_both_sides() -> None:
    # "the model the" -> distinctive {model} (1). insight "the model the" same.
    # Stop-words stripped so coverage is over signal words only.
    art = _artifact(
        [("i1", "the model the")],
        synthesis_excerpt="the model the",
    )
    report = measure_synthesis_grounding(art)
    assert report.grounding == pytest.approx(1.0)
    assert report.synthesis_term_count == 1  # only "model" is distinctive


def test_no_stemming_scales_neq_scale() -> None:
    # synthesis "scales"; insight "scale" -> no match (lexical floor, no stemming)
    art = _artifact(
        [("i1", "the model scale is important")],
        synthesis_excerpt="the architecture scales",
    )
    report = measure_synthesis_grounding(art)
    assert "scales" in report.overreach_terms
    assert "scale" not in report.overreach_terms  # "scale" is in the insights vocab


def test_matching_is_case_insensitive() -> None:
    art = _artifact(
        [("i1", "the ROCKET engine thrust analysis")],
        synthesis_excerpt="rocket engine thrust analysis",
    )
    report = measure_synthesis_grounding(art)
    assert report.grounding == pytest.approx(1.0)


def test_distinctive_terms_deduplicated_in_synthesis() -> None:
    art = _artifact(
        [("i1", "model cost analysis")],
        synthesis_excerpt="cost cost cost model",
    )
    report = measure_synthesis_grounding(art)
    assert report.synthesis_term_count == 2  # {cost, model} deduped
    assert report.grounding == pytest.approx(1.0)


def test_overreach_terms_sorted() -> None:
    # synthesis distinctive: alpha zebra mango gamma delta (5)
    # insights vocab: {alpha, beta}; matched: alpha (1); overreach: zebra mango gamma delta
    art = _artifact(
        [("i1", "alpha beta")],
        synthesis_excerpt="alpha zebra mango gamma delta",
    )
    report = measure_synthesis_grounding(art)
    assert report.overreach_terms == tuple(sorted(["zebra", "mango", "gamma", "delta"]))
    assert report.matched_term_count == 1


# --- provenance / purity --------------------------------------------------


def test_artifact_id_carried_through() -> None:
    art = _artifact(
        [("i1", "model attention")],
        synthesis_excerpt="the model uses attention",
        investigation_id="inv-999",
    )
    assert measure_synthesis_grounding(art).artifact_id == "inv-999"


def test_authority_is_always_advisory() -> None:
    art = _artifact([("i1", "model")], synthesis_excerpt="the model works")
    assert measure_synthesis_grounding(art).authority == "advisory"


def test_report_is_immutable() -> None:
    report = measure_synthesis_grounding(
        _artifact([("i1", "model")], synthesis_excerpt="the model works")
    )
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.grounding = 0.0  # type: ignore[misc]


def test_determinism_same_artifact_same_report() -> None:
    art = _artifact(
        [("i1", "model attention scales")],
        synthesis_excerpt="the model attention scales efficiently",
    )
    assert measure_synthesis_grounding(art) == measure_synthesis_grounding(art)


def test_isinstance_report_type() -> None:
    art = _artifact([("i1", "model")], synthesis_excerpt="the model works")
    assert isinstance(measure_synthesis_grounding(art), SynthesisGroundingReport)


def test_notes_describe_findings() -> None:
    # synthesis distinctive: model attention scales cheaply (4); insights support 3
    art = _artifact(
        [("i1", "model attention scales")],
        synthesis_excerpt="model attention scales cheaply",
    )
    joined = " | ".join(measure_synthesis_grounding(art).notes)
    assert "lexical floor" in joined.lower()
    assert "grounding 75%" in joined.lower()
    assert "overreach" in joined.lower()


def test_matched_plus_overreach_equals_synthesis_terms() -> None:
    # synthesis distinctive: alpha beta delta epsilon zeta (5); insights: alpha beta gamma
    art = _artifact(
        [("i1", "alpha beta gamma")],
        synthesis_excerpt="alpha beta delta epsilon zeta",
    )
    report = measure_synthesis_grounding(art)
    # matched: alpha beta (2); overreach: delta epsilon zeta (3)
    assert report.matched_term_count + len(report.overreach_terms) == report.synthesis_term_count


# --- public API -----------------------------------------------------------


def test_public_api_exports() -> None:
    from substrate.deep_research_quality import synthesis_grounding as mod

    assert set(mod.__all__) == {
        "SynthesisGroundingReport",
        "measure_synthesis_grounding",
    }
    assert dataclasses.is_dataclass(mod.SynthesisGroundingReport)
