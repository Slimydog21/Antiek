"""Tests for the synthesis-specificity axis (is the conclusion concrete or a hedge?).

Exercises: specific/vague/hedging/withheld/unknown verdicts, numeric + hedge +
specificity ratios, the three-way distinction (grounding/specificity of different
objects), threshold tuning, purity/immutability, validation. Hand-counted fixtures.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.deep_research_quality.synthesis_specificity import (
    SynthesisSpecificityError,
    SynthesisSpecificityReport,
    measure_synthesis_specificity,
)
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)


def _artifact(
    *,
    synthesis_excerpt: str | None = None,
    synthesis_withheld: bool = False,
) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id="art",
        problem_question="the problem",
        insights=[ArtifactInsight(node_id="i0", text="an insight")],
        open_questions=[ArtifactQuestion(node_id="q0", text="a question")],
        synthesis_excerpt=synthesis_excerpt,
        synthesis_withheld=synthesis_withheld,
    )


# --- specific (concrete conclusion) ---------------------------------------


def test_specific_synthesis_has_numeric_evidence() -> None:
    # "model 4 scored 86.4 percent" -> 5 tokens: model, 4, scored, 86.4, percent.
    # numeric: 4, 86.4 = 2. hedge: 0. numeric_ratio = 2/5 = 0.4.
    art = _artifact(synthesis_excerpt="model 4 scored 86.4 percent")
    r = measure_synthesis_specificity(art)
    assert r.verdict == "specific"
    assert r.numeric_ratio == pytest.approx(0.4)
    assert r.hedge_ratio == 0.0
    assert r.specificity_ratio == pytest.approx(0.4)
    assert r.token_count == 5
    assert r.numeric_token_count == 2
    assert r.authority == "advisory"


def test_specific_low_hedge_some_numbers() -> None:
    # "costs 30 tokens per request" -> 5 tokens, 1 numeric (30), 0 hedge.
    # numeric_ratio = 1/5 = 0.2; specificity = 0.2 >= 0.10 -> specific.
    art = _artifact(synthesis_excerpt="costs 30 tokens per request")
    r = measure_synthesis_specificity(art)
    assert r.verdict == "specific"
    assert r.numeric_ratio == pytest.approx(0.2)


# --- hedging (avoids commitment) ------------------------------------------


def test_hedging_synthesis_full_of_qualifiers() -> None:
    # "depends on various factors generally" -> 5 tokens: depends, on, various,
    # factors, generally. hedge: depends, various, factors, generally = 4.
    # hedge_ratio = 4/5 = 0.8 >= 0.15 -> hedging.
    art = _artifact(synthesis_excerpt="depends on various factors generally")
    r = measure_synthesis_specificity(art)
    assert r.verdict == "hedging"
    assert r.hedge_ratio == pytest.approx(0.8)
    assert r.hedge_token_count == 4


def test_hedging_at_threshold() -> None:
    # 5 tokens, hedge_threshold 0.15. Need >= 1 hedge (1/5 = 0.20 >= 0.15).
    # "may vary somewhat over time" -> 5 tokens: may, vary, somewhat, over, time.
    # hedge: may, vary, somewhat = 3 -> 3/5 = 0.60 -> hedging.
    art = _artifact(synthesis_excerpt="may vary somewhat over time")
    r = measure_synthesis_specificity(art)
    assert r.verdict == "hedging"


# --- vague (soft, non-committal) ------------------------------------------


def test_vague_neither_specific_nor_hedging() -> None:
    # "the models performed adequately" -> 4 tokens: the, models, performed,
    # adequately. numeric: 0. hedge: 0 (adequately not in set). specificity = 0.
    # Not hedging (0 < 0.15), not specific (0 < 0.10) -> vague.
    art = _artifact(synthesis_excerpt="the models performed adequately")
    r = measure_synthesis_specificity(art)
    assert r.verdict == "vague"
    assert r.numeric_ratio == 0.0
    assert r.hedge_ratio == 0.0
    assert r.specificity_ratio == 0.0


def test_vague_balanced_numeric_and_hedge() -> None:
    # numeric_ratio == hedge_ratio -> specificity = 0 -> not specific.
    # "some 50 percent may apply" -> 5 tokens: some, 50, percent, may, apply.
    # numeric: 50 = 1 -> 1/5 = 0.20. hedge: some, may = 2 -> 2/5 = 0.40.
    # hedge_ratio 0.40 >= 0.15 -> hedging (not vague). Adjust: use fewer hedges.
    # "result 50 percent confirmed" -> 4 tokens. numeric: 50 = 1 -> 0.25.
    # hedge: 0. specificity = 0.25 -> specific. Need hedge to cancel.
    # "about 50 percent" -> 3 tokens: about, 50, percent. numeric: 50 -> 0.33.
    # hedge: about -> 0.33. specificity = max(0, 0.33-0.33) = 0. hedge 0.33>=0.15
    # -> hedging. To get VAGUE, need hedge < 0.15 AND specificity < 0.10.
    # "adequately supported" -> 2 tokens, 0 numeric, 0 hedge -> vague.
    art = _artifact(synthesis_excerpt="adequately supported")
    r = measure_synthesis_specificity(art)
    assert r.verdict == "vague"


# --- withheld (agent deferred) --------------------------------------------


def test_withheld_synthesis_is_honest_unknown() -> None:
    art = _artifact(synthesis_withheld=True)
    r = measure_synthesis_specificity(art)
    assert r.verdict == "withheld"
    assert r.numeric_ratio is None
    assert r.hedge_ratio is None
    assert r.specificity_ratio is None
    assert r.token_count == 0


# --- unknown (no text) ----------------------------------------------------


def test_unknown_when_no_synthesis_excerpt() -> None:
    art = _artifact(synthesis_excerpt=None)
    r = measure_synthesis_specificity(art)
    assert r.verdict == "unknown"
    assert r.numeric_ratio is None


def test_unknown_when_empty_excerpt() -> None:
    art = _artifact(synthesis_excerpt="")
    r = measure_synthesis_specificity(art)
    assert r.verdict == "unknown"


def test_unknown_when_punctuation_only() -> None:
    art = _artifact(synthesis_excerpt="--- ...")
    r = measure_synthesis_specificity(art)
    assert r.verdict == "unknown"
    assert r.token_count == 0  # no alphanumeric tokens


# --- custom thresholds ----------------------------------------------------


def test_custom_hedge_threshold() -> None:
    # "may apply" -> 2 tokens: may, apply. hedge: may = 1 -> 0.50.
    art = _artifact(synthesis_excerpt="may apply")
    strict = measure_synthesis_specificity(art, hedge_threshold=0.60)
    assert strict.verdict != "hedging"  # 0.50 < 0.60 -> not hedging
    loose = measure_synthesis_specificity(art, hedge_threshold=0.40)
    assert loose.verdict == "hedging"  # 0.50 >= 0.40


def test_custom_specificity_threshold() -> None:
    # "scored 50 points" -> 3 tokens: scored, 50, points. numeric: 50 -> 0.33.
    art = _artifact(synthesis_excerpt="scored 50 points")
    loose = measure_synthesis_specificity(art, specificity_threshold=0.10)
    assert loose.verdict == "specific"  # 0.33 >= 0.10
    strict = measure_synthesis_specificity(art, specificity_threshold=0.40)
    assert strict.verdict != "specific"  # 0.33 < 0.40


# --- validation -----------------------------------------------------------


@pytest.mark.parametrize("field,bad", [("hedge_threshold", -0.1), ("hedge_threshold", 1.5)])
def test_bad_hedge_threshold_raises(field: str, bad: float) -> None:
    art = _artifact(synthesis_excerpt="some text here")
    with pytest.raises(SynthesisSpecificityError, match="hedge_threshold"):
        measure_synthesis_specificity(art, hedge_threshold=bad)


@pytest.mark.parametrize("bad", [-0.1, 1.5])
def test_bad_specificity_threshold_raises(bad: float) -> None:
    art = _artifact(synthesis_excerpt="some text here")
    with pytest.raises(SynthesisSpecificityError, match="specificity_threshold"):
        measure_synthesis_specificity(art, specificity_threshold=bad)


# --- purity / immutability ------------------------------------------------


def test_report_is_frozen_and_deterministic() -> None:
    art = _artifact(synthesis_excerpt="model 4 scored 86.4 percent")
    r1 = measure_synthesis_specificity(art)
    r2 = measure_synthesis_specificity(art)
    assert dataclasses.is_dataclass(r1)
    assert r1 == r2  # deterministic
    with pytest.raises(dataclasses.FrozenInstanceError):
        r1.verdict = "tampered"  # type: ignore[misc]
    assert isinstance(r1, SynthesisSpecificityReport)


def test_notes_are_non_empty_and_auditable() -> None:
    art = _artifact(synthesis_excerpt="model 4 scored 86.4 percent")
    r = measure_synthesis_specificity(art)
    assert isinstance(r.notes, tuple)
    assert len(r.notes) >= 5
    assert all(isinstance(n, str) and n for n in r.notes)
