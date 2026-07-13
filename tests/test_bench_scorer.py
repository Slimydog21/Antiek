"""Tests for ``substrate.antiek_bench.scorer`` — the harness §6 honesty keystone.
Each test isolates ONE method or ONE honesty invariant (§10) so the dual-output
contract + self-grade rejection + finite-or-None + disputed-not-averaged are
exercised independently."""

from __future__ import annotations

import dataclasses
import math

import pytest

from substrate.antiek_bench.scorer import (
    METHOD_EXACT,
    METHOD_HUMAN,
    METHOD_RUBRIC,
    SCORING_METHODS,
    JudgeVerdict,
    RunCapture,
    ScorerError,
    confirm_human,
    normalize_exact,
    score_run,
)


def _capture(method: str = METHOD_EXACT) -> RunCapture:
    return RunCapture(
        task_id="reasoning::syllogism-1",
        candidate_model_id="grok-composer-2.5",
        raw_output="All men are mortal. Socrates is a man.",
        method=method,
    )


def _judge(judge_model_id: str, passed: bool, score: float | None = 0.8) -> JudgeVerdict:
    return JudgeVerdict(judge_model_id=judge_model_id, passed=passed, score=score, rationale="ok")


# ---------------------------------------------------------------------------
# exact
# ---------------------------------------------------------------------------


def test_exact_match_success_and_score_one() -> None:
    capture = RunCapture(
        task_id="t", candidate_model_id="m", raw_output="  Hello   World  ", method=METHOD_EXACT
    )
    run = score_run(capture, expected="hello world")
    assert run.score == 1.0
    assert run.success is True
    assert run.disputed is False
    assert run.incomplete is False
    assert run.normalization is not None
    assert run.judge_model_id is None


def test_exact_mismatch_success_false_score_zero() -> None:
    run = score_run(_capture(METHOD_EXACT), expected="something else entirely")
    assert run.score == 0.0
    assert run.success is False
    assert run.incomplete is False


def test_exact_unicode_nfc_normalization() -> None:
    # composed vs decomposed é should normalize equal
    capture = RunCapture(
        task_id="t", candidate_model_id="m", raw_output="cafe\u0301", method=METHOD_EXACT  # decomposed e + combining acute
    )
    run = score_run(capture, expected="café")  # precomposed é
    assert run.success is True


def test_exact_requires_expected() -> None:
    with pytest.raises(ScorerError):
        score_run(_capture(METHOD_EXACT))


# ---------------------------------------------------------------------------
# rubric
# ---------------------------------------------------------------------------


def test_rubric_primary_judge_drives_success_and_score() -> None:
    run = score_run(
        _capture(METHOD_RUBRIC),
        primary_judge=_judge("gpt-5.5", passed=True, score=0.9),
    )
    assert run.success is True
    assert run.score == 0.9
    assert run.disputed is False
    assert run.incomplete is False
    assert run.judge_model_id == "gpt-5.5"
    assert run.rationale == "ok"


def test_rubric_self_grade_rejected() -> None:
    with pytest.raises(ScorerError):
        score_run(
            _capture(METHOD_RUBRIC),
            primary_judge=_judge("grok-composer-2.5", passed=True, score=0.9),  # == candidate
        )


def test_rubric_secondary_self_grade_rejected() -> None:
    with pytest.raises(ScorerError):
        score_run(
            _capture(METHOD_RUBRIC),
            primary_judge=_judge("gpt-5.5", passed=True),
            secondary_judge=_judge("grok-composer-2.5", passed=True),  # == candidate
        )


def test_rubric_disagreement_surfaces_disputed_not_averaged() -> None:
    run = score_run(
        _capture(METHOD_RUBRIC),
        primary_judge=_judge("gpt-5.5", passed=True, score=0.9),
        secondary_judge=_judge("claude-opus", passed=False, score=0.3),
    )
    assert run.disputed is True
    # score + success follow the PRIMARY judge (not averaged)
    assert run.score == 0.9
    assert run.success is True
    assert "judge disagreement" in " ".join(run.notes)


def test_rubric_agreement_not_disputed() -> None:
    run = score_run(
        _capture(METHOD_RUBRIC),
        primary_judge=_judge("gpt-5.5", passed=True, score=0.9),
        secondary_judge=_judge("claude-opus", passed=True, score=0.85),
    )
    assert run.disputed is False


def test_rubric_non_bool_passed_rejected() -> None:
    bad = JudgeVerdict(judge_model_id="gpt-5.5", passed=1, score=0.9, rationale="x")  # type: ignore[arg-type]  # int, not bool
    with pytest.raises(ScorerError):
        score_run(_capture(METHOD_RUBRIC), primary_judge=bad)


def test_rubric_nan_score_becomes_none_incomplete() -> None:
    run = score_run(
        _capture(METHOD_RUBRIC),
        primary_judge=_judge("gpt-5.5", passed=True, score=float("nan")),
    )
    assert run.score is None  # NaN -> None
    assert run.success is True  # passed is still real
    assert run.incomplete is True  # score None -> incomplete


def test_rubric_inf_score_becomes_none() -> None:
    run = score_run(
        _capture(METHOD_RUBRIC),
        primary_judge=_judge("gpt-5.5", passed=False, score=float("inf")),
    )
    assert run.score is None
    assert run.success is False


def test_rubric_requires_primary_judge() -> None:
    with pytest.raises(ScorerError):
        score_run(_capture(METHOD_RUBRIC))


# ---------------------------------------------------------------------------
# human
# ---------------------------------------------------------------------------


def test_human_pending_is_none_none_incomplete() -> None:
    run = score_run(_capture(METHOD_HUMAN))
    assert run.score is None
    assert run.success is None
    assert run.incomplete is True
    assert run.disputed is False


def test_human_confirm_sets_real_bool_success() -> None:
    pending = score_run(_capture(METHOD_HUMAN))
    confirmed = confirm_human(pending, confirmed_passed=True, confirmed_score=0.7)
    assert confirmed.success is True
    assert confirmed.score == 0.7
    assert confirmed.incomplete is False


def test_human_confirm_pass_without_numeric_score() -> None:
    # operator can confirm pass/fail WITHOUT a numeric score
    pending = score_run(_capture(METHOD_HUMAN))
    confirmed = confirm_human(pending, confirmed_passed=False)
    assert confirmed.success is False
    assert confirmed.score is None  # no numeric score
    assert confirmed.incomplete is False  # still complete (verdict given)


def test_human_confirm_rejects_non_bool() -> None:
    pending = score_run(_capture(METHOD_HUMAN))
    with pytest.raises(ScorerError):
        confirm_human(pending, confirmed_passed=1)  # type: ignore[arg-type]  # int not bool


def test_human_confirm_only_valid_for_human() -> None:
    run = score_run(_capture(METHOD_EXACT), expected="x")  # exact run
    with pytest.raises(ScorerError):
        confirm_human(run, confirmed_passed=True)


def test_human_confirm_does_not_mutate_pending() -> None:
    pending = score_run(_capture(METHOD_HUMAN))
    confirm_human(pending, confirmed_passed=True)
    # original still pending (frozen + unchanged)
    assert pending.success is None
    assert pending.score is None
    assert pending.incomplete is True


# ---------------------------------------------------------------------------
# honesty invariants (§10)
# ---------------------------------------------------------------------------


def test_bool_score_input_rejected_never_coerced() -> None:
    # booleans never coerce to 0.0/1.0 — a bool passed as score is a type error
    bad = JudgeVerdict(judge_model_id="gpt-5.5", passed=True, score=True, rationale="x")
    with pytest.raises(ScorerError):
        score_run(_capture(METHOD_RUBRIC), primary_judge=bad)


def test_unknown_method_raises() -> None:
    capture = RunCapture(task_id="t", candidate_model_id="m", raw_output="x", method="vibes")
    with pytest.raises(ScorerError):
        score_run(capture)


def test_empty_task_id_raises() -> None:
    capture = RunCapture(task_id="", candidate_model_id="m", raw_output="x", method=METHOD_EXACT)
    with pytest.raises(ScorerError):
        score_run(capture, expected="x")


def test_empty_candidate_model_id_raises() -> None:
    capture = RunCapture(task_id="t", candidate_model_id="", raw_output="x", method=METHOD_EXACT)
    with pytest.raises(ScorerError):
        score_run(capture, expected="x")


def test_scoring_methods_contract() -> None:
    assert frozenset({METHOD_EXACT, METHOD_RUBRIC, METHOD_HUMAN}) == SCORING_METHODS


def test_normalize_exact_deterministic_and_recorded() -> None:
    assert normalize_exact("  Héllo   WORLD ") == "héllo world"
    assert normalize_exact("hello") == normalize_exact("  hello  ")


def test_dual_output_one_run_yields_both_score_and_success() -> None:
    # the §2/§7 contract: one scored run yields BOTH a finite score (for view) and
    # a real bool success (for usage-learn). exact case:
    run = score_run(_capture(METHOD_EXACT), expected="all men are mortal. socrates is a man.")
    assert isinstance(run.score, float)
    assert math.isfinite(run.score)
    assert isinstance(run.success, bool)
    # rubric case:
    run2 = score_run(_capture(METHOD_RUBRIC), primary_judge=_judge("gpt-5.5", True, 0.8))
    assert isinstance(run2.score, float)
    assert math.isfinite(run2.score)
    assert isinstance(run2.success, bool)


def test_authority_is_advisory() -> None:
    run = score_run(_capture(METHOD_EXACT), expected="x")
    assert run.authority == "scorer_advisory"


def test_report_is_frozen() -> None:
    run = score_run(_capture(METHOD_EXACT), expected="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        run.score = 0.5  # type: ignore[misc]


def test_deterministic_same_inputs_same_run() -> None:
    run1 = score_run(_capture(METHOD_EXACT), expected="hello")
    run2 = score_run(_capture(METHOD_EXACT), expected="hello")
    assert run1 == run2
