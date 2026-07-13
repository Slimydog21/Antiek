"""Tests for substrate/question_specificity.py — question input-quality gate."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from substrate.question_specificity import measure_question_specificity

# --- unmeasurable ----------------------------------------------------------


def test_unmeasurable_empty() -> None:
    r = measure_question_specificity("")
    assert r.verdict == "unmeasurable"
    assert r.distinctive_term_count == 0
    assert r.distinctive_ratio is None
    assert r.distinctive_terms == ()


def test_unmeasurable_only_stopwords() -> None:
    r = measure_question_specificity("what is the a of the and is")
    assert r.verdict == "unmeasurable"
    assert r.distinctive_term_count == 0
    assert r.distinctive_ratio is None


def test_unmeasurable_never_fabricates_specific() -> None:
    assert measure_question_specificity("").verdict != "specific"


def test_unmeasurable_none_input() -> None:
    r = measure_question_specificity(None)  # type: ignore[arg-type]
    assert r.verdict == "unmeasurable"


# --- vague (too few terms) ------------------------------------------------


def test_vague_one_term() -> None:
    r = measure_question_specificity("tell me about antiek")
    assert r.verdict == "vague"
    assert r.distinctive_term_count == 2  # tell + antiek (both distinctive)


def test_vague_boundary_below_min() -> None:
    # 2 distinctive terms < default min 3 -> vague.
    r = measure_question_specificity("what is reasoning efficiency")
    assert r.distinctive_terms == ("efficiency", "reasoning")
    assert r.verdict == "vague"


def test_vague_two_distinctive() -> None:
    r = measure_question_specificity("what is reasoning efficiency")
    assert r.distinctive_terms == ("efficiency", "reasoning")
    assert r.verdict == "vague"


# --- specific (focused band) ----------------------------------------------


def test_specific_focused_band() -> None:
    r = measure_question_specificity(
        "how does reasoning model pricing compare across providers for long context"
    )
    assert r.verdict == "specific"
    assert r.has_interrogative is True
    assert r.distinctive_ratio is not None and 0 < r.distinctive_ratio <= 1.0


def test_specific_is_measured_not_default() -> None:
    assert measure_question_specificity("").verdict == "unmeasurable"
    assert (
        measure_question_specificity("compare model pricing across providers").verdict
        == "specific"
    )


def test_specific_boundary_min_inclusive() -> None:
    # exactly 3 distinctive terms == min 3 -> specific (<= max, >= min).
    r = measure_question_specificity("compare model pricing")
    assert r.distinctive_term_count == 3
    assert r.verdict == "specific"


# --- over_narrow (keyword soup) -------------------------------------------


def test_over_narrow_many_terms() -> None:
    q = " ".join(f"term{i}" for i in range(15))
    r = measure_question_specificity(q)
    assert r.verdict == "over_narrow"
    assert r.distinctive_term_count == 15


def test_over_narrow_boundary_max_inclusive() -> None:
    # exactly 12 terms == max 12 -> specific (> is the over_narrow trigger).
    q = " ".join(f"term{i}" for i in range(12))
    r = measure_question_specificity(q)
    assert r.verdict == "specific"
    q2 = " ".join(f"term{i}" for i in range(13))
    assert measure_question_specificity(q2).verdict == "over_narrow"


# --- lexical floor ---------------------------------------------------------


def test_no_stemming_lexical_floor() -> None:
    # scale != scales (no stemming).
    r = measure_question_specificity("how do model scale scales work")
    assert r.distinctive_terms == ("model", "scale", "scales", "work")


def test_no_synonymy_lexical_floor() -> None:
    # impact != affect (no synonymy) — both counted as distinct.
    r = measure_question_specificity("what is the impact affect of pricing")
    assert "impact" in r.distinctive_terms
    assert "affect" in r.distinctive_terms


def test_distinctive_terms_sorted_auditable() -> None:
    r = measure_question_specificity("zebra apple mango banana")
    assert r.distinctive_terms == ("apple", "banana", "mango", "zebra")


# --- interrogative signal --------------------------------------------------


def test_has_interrogative_present() -> None:
    r = measure_question_specificity("how does pricing work here")
    assert r.has_interrogative is True


def test_has_interrogative_absent_flagged() -> None:
    r = measure_question_specificity("pricing model comparison across providers")
    assert r.has_interrogative is False
    assert any("topic" in n for n in r.notes)


def test_interrogative_not_counted_as_subject() -> None:
    # "what" and "how" are stop-words, not distinctive terms.
    r = measure_question_specificity("what how why pricing")
    assert r.distinctive_terms == ("pricing",)


# --- distinctive ratio -----------------------------------------------------


def test_distinctive_ratio_density() -> None:
    # "the" is a stop-word: compare model the pricing -> 3 distinctive / 4 tokens.
    r2 = measure_question_specificity("compare model the pricing")
    # tokens: compare model the pricing -> distinctive: compare model pricing (the is stop)
    assert r2.distinctive_ratio == pytest.approx(3 / 4)


# --- custom thresholds -----------------------------------------------------


def test_custom_min_terms() -> None:
    # 3 terms is specific under default but vague under min_terms=5.
    r = measure_question_specificity("compare model pricing", min_terms=5)
    assert r.verdict == "vague"


def test_custom_max_terms() -> None:
    # 8 terms is specific under default max 12 but over_narrow under max_terms=5.
    q = " ".join(f"term{i}" for i in range(8))
    r = measure_question_specificity(q, max_terms=5)
    assert r.verdict == "over_narrow"


# --- validation ------------------------------------------------------------


def test_invalid_min_terms_zero() -> None:
    with pytest.raises(ValueError, match="min_terms"):
        measure_question_specificity("x", min_terms=0)


def test_invalid_max_terms_not_int() -> None:
    with pytest.raises(ValueError, match="max_terms"):
        measure_question_specificity("x", max_terms=2.5)  # type: ignore[arg-type]


def test_invalid_min_gt_max() -> None:
    with pytest.raises(ValueError, match="min_terms"):
        measure_question_specificity("x", min_terms=5, max_terms=3)


# --- immutability ----------------------------------------------------------


def test_report_frozen() -> None:
    r = measure_question_specificity("compare model pricing")
    with pytest.raises(FrozenInstanceError):
        r.verdict = "tampered"  # type: ignore[misc]
