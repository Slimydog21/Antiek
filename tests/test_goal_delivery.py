"""Tests for the Midnight Oil goal-delivery accountability surface.

Exercises the load-bearing invariants of ``score_goal_delivery``: the four
verdict states, stop-word stripping, lexical-floor honesty (no stemming /
synonymy), the multi-goal mean with unmeasurable exclusion, the accountability
surface, the honesty rules, input validation, and unit-interval coverage.

The module is pure (no DB / LLM / clock / mutation), so every test is
deterministic and depends only on its inputs.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.midnight_oil.goal_delivery import (
    GoalDeliveryError,
    GoalDeliveryVerdict,
    RunDeliveryReport,
    score_goal_delivery,
)

BRIEF = "brief-1876-frozen-mandate"


def _score(goals: list[str], findings: str, **kwargs: float) -> RunDeliveryReport:
    return score_goal_delivery(
        brief_id=BRIEF, goals=goals, findings_text=findings, **kwargs
    )


# --- verdict states -------------------------------------------------------


def test_all_terms_covered_yields_met() -> None:
    # distinctive terms: understand transformer attention scaling laws (5)
    findings = (
        "We studied the transformer architecture to understand its attention "
        "mechanism and scaling laws across model sizes."
    )
    report = _score(["understand transformer attention scaling laws"], findings)
    verdict = report.verdicts[0]
    assert verdict.state == "met"
    assert verdict.coverage == pytest.approx(1.0)
    assert report.met_count == 1
    assert report.unmet_count == 0
    assert report.partial_count == 0
    assert report.unmeasurable_count == 0
    assert report.measured_goal_count == 1
    assert report.overall_delivery == pytest.approx(1.0)


def test_partial_verdict_between_thresholds() -> None:
    # distinctive: battery density recycling safety (4); 2 matched -> 0.5 -> partial
    report = _score(
        ["battery density recycling safety"],
        "We measured battery density in the lab.",
    )
    verdict = report.verdicts[0]
    assert verdict.state == "partial"
    assert verdict.coverage == pytest.approx(0.5)
    assert report.partial_count == 1


def test_unmet_verdict_below_partial_threshold() -> None:
    # distinctive: quantum coherence correction fidelity latency (5); 1 matched -> 0.2
    report = _score(
        ["quantum coherence correction fidelity latency"],
        "We noted some quantum effects in passing.",
    )
    verdict = report.verdicts[0]
    assert verdict.state == "unmet"
    assert verdict.coverage == pytest.approx(0.2)
    assert report.unmet_count == 1


def test_unmeasurable_when_goal_is_stop_words_only() -> None:
    report = _score(
        ["the of and to a", "real signal payload"],
        "findings mention real signal payload words",
    )
    assert report.verdicts[0].state == "unmeasurable"
    assert report.verdicts[0].coverage == pytest.approx(0.0)
    assert report.verdicts[1].state == "met"
    assert report.unmeasurable_count == 1
    assert report.measured_goal_count == 1


def test_unmeasurable_when_goal_is_whitespace() -> None:
    report = _score(["   ", "delivery content"], "delivery content here")
    assert report.verdicts[0].state == "unmeasurable"
    assert report.verdicts[1].state == "met"
    assert report.unmeasurable_count == 1


# --- lexical floor honesty ------------------------------------------------


def test_stop_words_stripped_from_distinctive_terms() -> None:
    # 4 words but only 1 signal term "deployment" after stop-word removal.
    report = _score(["what is the deployment"], "")
    verdict = report.verdicts[0]
    assert verdict.state == "unmet"
    assert verdict.unmatched_terms == ("deployment",)
    assert verdict.matched_terms == ()


def test_distinctive_terms_deduplicated() -> None:
    report = _score(["cost cost cost cost"], "The cost analysis shows results.")
    verdict = report.verdicts[0]
    assert verdict.state == "met"
    assert verdict.coverage == pytest.approx(1.0)
    assert verdict.matched_terms == ("cost",)


def test_matching_is_case_insensitive() -> None:
    report = _score(["ROCKET ENGINE THRUST"], "the rocket engine thrust curve")
    assert report.verdicts[0].state == "met"


def test_no_stemming_scale_neq_scales() -> None:
    # distinctive: model scale (2); neither matches scaling/scales -> unmet at 0.
    report = _score(["does the model scale"], "we measured scaling and scales")
    verdict = report.verdicts[0]
    assert verdict.state == "unmet"
    assert verdict.matched_terms == ()
    assert verdict.unmatched_terms == ("model", "scale")


def test_no_synonymy_impact_neq_affect() -> None:
    # distinctive: impact (1); findings say "affects" not "impact" -> unmet.
    report = _score(["the impact"], "this strongly affects end users")
    verdict = report.verdicts[0]
    assert verdict.state == "unmet"
    assert "impact" in verdict.unmatched_terms


# --- multi-goal mean & accountability ------------------------------------


def test_overall_delivery_is_mean_of_measurable_goals() -> None:
    # A: 4 terms all matched -> 1.0 (met). B: 4 terms, 2 matched -> 0.5 (partial).
    report = _score(
        ["alpha beta gamma delta", "epsilon zeta eta theta"],
        "alpha beta gamma delta epsilon zeta found here",
    )
    assert len(report.verdicts) == 2
    assert report.verdicts[0].coverage == pytest.approx(1.0)
    assert report.verdicts[1].coverage == pytest.approx(0.5)
    assert report.overall_delivery == pytest.approx(0.75)
    assert report.measured_goal_count == 2


def test_unmeasurable_goals_do_not_penalize_overall() -> None:
    # One measurable met (1.0) + one unmeasurable -> overall 1.0, not 0.5.
    report = _score(
        ["the of a", "signal payload"],
        "signal payload present",
    )
    assert report.verdicts[0].state == "unmeasurable"
    assert report.verdicts[1].state == "met"
    assert report.overall_delivery == pytest.approx(1.0)
    assert report.measured_goal_count == 1


def test_all_unmeasurable_yields_zero_overall_with_deferral_note() -> None:
    report = _score(["the of a", "an the is"], "any findings at all")
    assert report.measured_goal_count == 0
    assert report.overall_delivery == pytest.approx(0.0)
    assert any("unmeasurable" in n.lower() for n in report.notes)


def test_partial_goals_are_not_on_accountability_surface() -> None:
    report = _score(
        ["fully covered alpha beta", "partial zeta omega sigma"],
        "fully covered alpha beta plus zeta omega here",
    )
    assert report.verdicts[0].state == "met"
    # goal2: partial zeta omega sigma (3 terms); zeta omega matched -> 0.66 partial
    assert report.verdicts[1].state == "partial"
    assert report.unmet_goals == ()
    assert report.unmet_count == 0


def test_unmet_goals_form_accountability_surface() -> None:
    report = _score(
        ["fully covered alpha beta", "missing zeta omega sigma kappa"],
        "fully covered alpha beta",
    )
    assert report.verdicts[0].state == "met"
    assert report.verdicts[1].state == "unmet"
    assert report.unmet_goals == (report.verdicts[1],)
    assert all(isinstance(v, GoalDeliveryVerdict) for v in report.unmet_goals)
    assert report.unmet_count == 1
    assert any("ACCOUNTABILITY" in n for n in report.notes)


def test_empty_findings_make_measurable_goals_unmet() -> None:
    report = _score(["alpha beta gamma", "the of a"], "")
    assert report.verdicts[0].state == "unmet"
    assert report.verdicts[0].coverage == pytest.approx(0.0)
    assert report.verdicts[1].state == "unmeasurable"
    assert report.unmet_count == 1
    assert report.measured_goal_count == 1


# --- honesty / purity -----------------------------------------------------


def test_authority_is_always_advisory() -> None:
    report = _score(["alpha beta"], "alpha beta here")
    assert report.authority == "advisory"


def test_report_and_verdicts_are_immutable() -> None:
    report = _score(["alpha beta"], "alpha beta here")
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.met_count = 99  # type: ignore[misc]
    verdict = report.verdicts[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        verdict.state = "unmet"  # type: ignore[misc]


def test_determinism_same_inputs_same_report() -> None:
    goals = ["alpha beta gamma", "delta epsilon"]
    findings = "alpha beta gamma delta found"
    assert _score(goals, findings) == _score(goals, findings)


def test_extra_findings_terms_never_inflate_a_goal() -> None:
    base = _score(["alpha beta"], "alpha beta")
    rich = _score(["alpha beta"], "alpha beta plus lots of other noise tokens")
    assert base.verdicts[0] == rich.verdicts[0]


# --- provenance & structure -----------------------------------------------


def test_brief_id_carried_through() -> None:
    assert _score(["alpha beta"], "alpha beta").brief_id == BRIEF


def test_goal_index_and_text_preserved() -> None:
    report = _score(["one alpha", "two beta", "three gamma"], "alpha beta gamma")
    assert [v.goal_index for v in report.verdicts] == [0, 1, 2]
    assert [v.goal for v in report.verdicts] == ["one alpha", "two beta", "three gamma"]


def test_counts_are_consistent_with_goal_count() -> None:
    report = _score(
        ["alpha beta", "the of a", "missing kappa lambda mu nu"],
        "alpha beta found",
    )
    total = (
        report.met_count
        + report.partial_count
        + report.unmet_count
        + report.unmeasurable_count
    )
    assert total == report.goal_count
    assert report.measured_goal_count == report.met_count + report.partial_count + report.unmet_count


def test_matched_and_unmatched_terms_sorted_disjoint_tuples() -> None:
    report = _score(["zebra apple mango cherry"], "apple zebra here")
    verdict = report.verdicts[0]
    assert isinstance(verdict.matched_terms, tuple)
    assert isinstance(verdict.unmatched_terms, tuple)
    assert verdict.matched_terms == tuple(sorted(verdict.matched_terms))
    assert verdict.unmatched_terms == tuple(sorted(verdict.unmatched_terms))
    assert set(verdict.matched_terms) | set(verdict.unmatched_terms) == {
        "zebra",
        "apple",
        "mango",
        "cherry",
    }
    assert not (set(verdict.matched_terms) & set(verdict.unmatched_terms))


def test_tokenization_strips_punctuation_keeps_digits() -> None:
    # "hi-phen" -> {hi, phen}; findings "hifen" matches neither -> both unmatched.
    report = _score(["tokenize hi-phen a1b2"], "tokenize hifen a1b2 found")
    verdict = report.verdicts[0]
    assert "tokenize" in verdict.matched_terms
    assert "a1b2" in verdict.matched_terms
    assert "hi" in verdict.unmatched_terms
    assert "phen" in verdict.unmatched_terms


def test_coverage_and_overall_in_unit_interval() -> None:
    report = _score(
        ["alpha beta gamma delta epsilon", "zeta eta theta"],
        "alpha only",
    )
    for v in report.verdicts:
        assert 0.0 <= v.coverage <= 1.0
    assert 0.0 <= report.overall_delivery <= 1.0


def test_notes_describe_breakdown() -> None:
    report = _score(
        ["alpha beta", "the of a", "missing kappa lambda mu nu"],
        "alpha beta",
    )
    joined = " | ".join(report.notes)
    assert "overall delivery" in joined.lower()
    assert "unmeasurable" in joined.lower()


# --- custom thresholds ----------------------------------------------------


def test_custom_thresholds_change_verdicts() -> None:
    # distinctive: alpha beta gamma delta (4); 2 matched -> 0.5
    findings = "alpha beta found in the literature"
    assert _score(["alpha beta gamma delta"], findings).verdicts[0].state == "partial"
    assert (
        _score(["alpha beta gamma delta"], findings, met_threshold=0.5).verdicts[0].state
        == "met"
    )
    # partial raised to 0.6 makes 0.5 coverage unmet.
    assert (
        _score(
            ["alpha beta gamma delta"],
            findings,
            partial_threshold=0.6,
        ).verdicts[0].state
        == "unmet"
    )


# --- input validation -----------------------------------------------------


@pytest.mark.parametrize("bad", ["", "   ", "\t\n"])
def test_validation_rejects_empty_brief_id(bad: str) -> None:
    with pytest.raises(GoalDeliveryError, match="brief_id"):
        score_goal_delivery(brief_id=bad, goals=["a b"], findings_text="a b")


def test_validation_rejects_no_goals() -> None:
    with pytest.raises(GoalDeliveryError, match="goal"):
        score_goal_delivery(brief_id=BRIEF, goals=[], findings_text="x")


@pytest.mark.parametrize("bad", [0.0, -0.1, 1.0001, 2.0])
def test_validation_rejects_bad_met_threshold(bad: float) -> None:
    with pytest.raises(GoalDeliveryError, match="met_threshold"):
        _score(["a b"], "a b", met_threshold=bad)


@pytest.mark.parametrize("bad", [0.0, -0.1, 0.8, 1.0])
def test_validation_rejects_bad_partial_threshold(bad: float) -> None:
    # 0.0 rejected (unmet band must stay reachable); >= met(0.8) rejected; negatives.
    with pytest.raises(GoalDeliveryError, match="partial_threshold"):
        _score(["a b"], "a b", partial_threshold=bad)


def test_validation_partial_must_be_below_met() -> None:
    with pytest.raises(GoalDeliveryError, match="partial_threshold"):
        _score(["a b c"], "a b c", met_threshold=0.5, partial_threshold=0.5)


def test_public_api_exports() -> None:
    from substrate.midnight_oil import goal_delivery as mod

    assert set(mod.__all__) == {
        "GoalDeliveryError",
        "GoalDeliveryVerdict",
        "RunDeliveryReport",
        "score_goal_delivery",
    }
    assert issubclass(mod.GoalDeliveryError, ValueError)
    assert dataclasses.is_dataclass(mod.GoalDeliveryVerdict)
    assert dataclasses.is_dataclass(mod.RunDeliveryReport)
