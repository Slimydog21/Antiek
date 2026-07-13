"""Tests for the draft-divergence axis (pre-merge drift — ask #3).

Pure lexical arithmetic — distinctive terms (stop-words stripped) counted by hand.
Use alpha/beta/gamma nonsense tokens so every ratio is exactly countable.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.draft_divergence import (
    DraftDivergenceError,
    DraftInput,
    measure_draft_divergence,
)

P = ["alpha beta gamma"]  # parent = 3 distinctive terms


# --- verdicts ---------------------------------------------------------------


def test_no_drift_draft_echoes_parents() -> None:
    # Draft = exactly the parents' terms -> divergence 0, novel 0 -> no_drift.
    report = measure_draft_divergence(DraftInput("alpha beta gamma", P))
    assert report.verdict == "no_drift"
    assert report.draft_term_count == 3
    assert report.inherited_term_count == 3
    assert report.novel_term_count == 0
    assert report.divergence_ratio == 0.0


def test_high_drift_mostly_novel() -> None:
    # 3 inherited + 8 novel = 11 draft terms -> 8/11 = 0.727 >= 0.70 -> high_drift.
    # 3 inherited + 8 novel = 11 draft terms -> 8/11 = 0.727 >= 0.70 -> high_drift.
    draft = "alpha beta gamma delta echo foxtrot golf hotel india juliet kilo"
    report = measure_draft_divergence(DraftInput(draft, P))
    assert report.verdict == "high_drift"
    assert report.novel_term_count == 8
    assert report.inherited_term_count == 3
    assert report.divergence_ratio == pytest.approx(8 / 11)


def test_high_drift_at_threshold_boundary_is_a_hit() -> None:
    # 3 inherited + 7 novel = 10 -> 7/10 = 0.70 == threshold -> high_drift (>= boundary).
    draft = "alpha beta gamma delta echo foxtrot golf hotel india juliet"
    report = measure_draft_divergence(DraftInput(draft, P))
    assert report.verdict == "high_drift"
    assert report.divergence_ratio == pytest.approx(0.70)


def test_moderate_drift_mixed() -> None:
    # 3 inherited + 3 novel = 6 -> 3/6 = 0.50 < 0.70 -> moderate_drift.
    draft = "alpha beta gamma delta echo foxtrot"
    report = measure_draft_divergence(DraftInput(draft, P))
    assert report.verdict == "moderate_drift"
    assert report.divergence_ratio == pytest.approx(0.50)


def test_moderate_drift_just_below_threshold() -> None:
    # 3 inherited + 6 novel = 9 -> 6/9 = 0.667 < 0.70 -> moderate_drift.
    draft = "alpha beta gamma delta echo foxtrot golf hotel"
    report = measure_draft_divergence(DraftInput(draft, P))
    assert report.verdict == "moderate_drift"


# --- the load-bearing distinction: no_drift != unknown --------------------


def test_no_drift_is_not_unknown() -> None:
    # A draft that perfectly echoes parents (real measurable text) -> no_drift,
    # NOT unknown. divergence_ratio is a real 0.0, not None.
    report = measure_draft_divergence(DraftInput("alpha beta", ["alpha beta"]))
    assert report.verdict == "no_drift"
    assert report.divergence_ratio == 0.0


def test_unknown_when_draft_is_none() -> None:
    report = measure_draft_divergence(DraftInput(None, P))
    assert report.verdict == "unknown"
    assert report.divergence_ratio is None  # defer, never 0.0


def test_unknown_when_draft_all_glue() -> None:
    # All stop-words -> no distinctive terms -> unknown.
    report = measure_draft_divergence(DraftInput("the and of is are", P))
    assert report.verdict == "unknown"
    assert report.divergence_ratio is None


# --- parentless draft (standalone — honest, not an error) -------------------


def test_parentless_draft_is_fully_novel() -> None:
    # Empty parent_texts -> every draft term is novel -> divergence 1.0.
    report = measure_draft_divergence(DraftInput("delta echo foxtrot", []))
    assert report.verdict == "high_drift"
    assert report.parent_term_count == 0
    assert report.novel_term_count == 3
    assert report.inherited_term_count == 0
    assert report.divergence_ratio == 1.0


def test_multiple_parents_union() -> None:
    # Two parents with overlapping terms -> union baseline.
    report = measure_draft_divergence(
        DraftInput("alpha zeta", ["alpha beta", "beta gamma"])
    )
    # parent union = {alpha, beta, gamma}; draft {alpha, zeta} -> 1 novel of 2.
    assert report.parent_term_count == 3
    assert report.inherited_term_count == 1  # alpha
    assert report.novel_term_count == 1  # zeta
    assert report.divergence_ratio == pytest.approx(0.50)


# --- stop-word floor -------------------------------------------------------


def test_stop_words_stripped_not_counted() -> None:
    # "the alpha of beta" -> distinctive {alpha, beta} (the, of stripped).
    report = measure_draft_divergence(DraftInput("the alpha of beta", ["alpha beta"]))
    assert report.draft_term_count == 2
    assert report.verdict == "no_drift"


def test_case_insensitive() -> None:
    report = measure_draft_divergence(DraftInput("ALPHA Beta GAMMA", ["alpha beta gamma"]))
    assert report.verdict == "no_drift"
    assert report.draft_term_count == 3


# --- custom threshold ------------------------------------------------------


def test_custom_threshold_promotes_to_high() -> None:
    # divergence 0.50 -> moderate at default 0.70, high at threshold 0.40.
    draft = "alpha beta gamma delta echo foxtrot"  # 3 novel of 6 = 0.50
    report_default = measure_draft_divergence(DraftInput(draft, P))
    assert report_default.verdict == "moderate_drift"
    report_loose = measure_draft_divergence(DraftInput(draft, P), high_threshold=0.40)
    assert report_loose.verdict == "high_drift"


def test_threshold_zero_promotes_any_drift_to_high() -> None:
    # threshold 0.0: any novel term -> high_drift; but zero novel -> no_drift.
    report = measure_draft_divergence(
        DraftInput("alpha beta gamma delta", P), high_threshold=0.0
    )
    # 1 novel of 4 = 0.25 > 0.0 -> high_drift.
    assert report.verdict == "high_drift"


# --- validation -----------------------------------------------------------


def test_high_threshold_out_of_range_raises() -> None:
    with pytest.raises(DraftDivergenceError, match="high_threshold"):
        measure_draft_divergence(DraftInput("alpha", P), high_threshold=1.5)
    with pytest.raises(DraftDivergenceError, match="high_threshold"):
        measure_draft_divergence(DraftInput("alpha", P), high_threshold=-0.1)


# --- purity / determinism -------------------------------------------------


def test_report_is_frozen_and_advisory() -> None:
    report = measure_draft_divergence(DraftInput("alpha beta", P))
    assert report.authority == "advisory"
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.verdict = "tampered"  # type: ignore[misc]


def test_deterministic_same_inputs_same_report() -> None:
    draft = DraftInput("alpha beta gamma delta echo", P)
    first = measure_draft_divergence(draft)
    second = measure_draft_divergence(draft)
    assert first == second


def test_notes_carry_provenance() -> None:
    report = measure_draft_divergence(DraftInput("alpha delta echo", P))
    joined = " ".join(report.notes)
    assert "draft-divergence" in joined
    assert "verdict moderate_drift" in joined or "verdict" in joined
