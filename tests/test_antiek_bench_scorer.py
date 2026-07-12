"""Antiek-bench scorer — the honesty keystone (§10 invariants #2-#5)."""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from substrate.antiek_bench.scorer import (
    ExactScorer,
    HumanScorer,
    JudgeVerdict,
    RubricScorer,
    ScoreVerdict,
    SelfGradeRejected,
)
from substrate.antiek_bench.task_registry import BenchTask


def _exact_task(expected: str = "C is true.") -> BenchTask:
    return BenchTask(
        task_id="reasoning::two_step",
        family="reasoning",
        prompt="p",
        scoring="exact",
        expected=expected,
    )


def _rubric_task() -> BenchTask:
    return BenchTask(
        task_id="writing::summary",
        family="writing",
        prompt="Summarize.",
        scoring="rubric",
        rubric="PASS if covers thesis without fabrication.",
    )


def _human_task() -> BenchTask:
    return BenchTask(
        task_id="reading_comprehension::main_claim",
        family="reading_comprehension",
        prompt="State the main claim.",
        scoring="human",
    )


class _FakeJudge:
    """A test double for RubricJudge (no network)."""

    def __init__(self, model_id: str, *, passed: bool, score: float) -> None:
        self.judge_model_id = model_id
        self._passed = passed
        self._score = score

    def judge(
        self,
        *,
        rubric: str,
        prompt: str,
        candidate_output: str,
        candidate_model_id: str,
    ) -> JudgeVerdict:
        return JudgeVerdict(
            passed=self._passed,
            score=self._score,
            rationale="fake verdict",
            judge_model_id=self.judge_model_id,
        )


# --- exact scoring -------------------------------------------------------- #


def test_exact_match_scores_one_success_true() -> None:
    verdict = ExactScorer().score(task=_exact_task(), candidate_output="C is true.")
    assert verdict.score == 1.0
    assert verdict.success is True
    assert verdict.pending is False


def test_exact_mismatch_scores_zero_success_false() -> None:
    verdict = ExactScorer().score(task=_exact_task(), candidate_output="D is false.")
    assert verdict.score == 0.0
    assert verdict.success is False


def test_exact_normalises_whitespace_and_case() -> None:
    verdict = ExactScorer().score(task=_exact_task(), candidate_output="  c   IS   true.  ")
    assert verdict.success is True
    # normalisation is recorded for re-checkability
    assert any("norm(" in n for n in verdict.notes)


# --- rubric scoring + self-grade rejection -------------------------------- #


def test_rubric_success_follows_primary_judge_pass() -> None:
    judge = _FakeJudge("glm-5.2-judge", passed=True, score=0.9)
    verdict = RubricScorer(judge).score(
        task=_rubric_task(), candidate_output="ok", candidate_model_id="gpt-5.5"
    )
    assert verdict.success is True
    assert verdict.score == pytest.approx(0.9)
    assert verdict.disputed is False
    assert verdict.judge_model_id == "glm-5.2-judge"


def test_rubric_self_grade_is_mechanically_rejected() -> None:
    # Invariant #4: a model never grades its own output.
    judge = _FakeJudge("gpt-5.5", passed=True, score=1.0)
    with pytest.raises(SelfGradeRejected, match="cannot grade its own output"):
        RubricScorer(judge).score(
            task=_rubric_task(), candidate_output="ok", candidate_model_id="gpt-5.5"
        )


def test_rubric_second_judge_disagreement_marked_disputed_not_averaged() -> None:
    primary = _FakeJudge("glm-5.2-judge", passed=True, score=0.9)
    second = _FakeJudge("claude-judge", passed=False, score=0.3)
    verdict = RubricScorer(primary, second_judge=second).score(
        task=_rubric_task(), candidate_output="ok", candidate_model_id="gpt-5.5"
    )
    assert verdict.disputed is True
    # success follows the primary judge; disagreement is surfaced, not averaged
    assert verdict.success is True
    assert any("judge disagreement" in n for n in verdict.notes)


def test_rubric_second_judge_self_grade_also_rejected() -> None:
    primary = _FakeJudge("glm-5.2-judge", passed=True, score=0.9)
    second = _FakeJudge("gpt-5.5", passed=False, score=0.3)
    with pytest.raises(SelfGradeRejected):
        RubricScorer(primary, second_judge=second).score(
            task=_rubric_task(), candidate_output="ok", candidate_model_id="gpt-5.5"
        )


def test_rubric_non_finite_score_becomes_none_not_clamped() -> None:
    # Invariant #3: NaN/Inf → None (honest unmeasured), never fabricated.
    judge = _FakeJudge("glm-5.2-judge", passed=True, score=float("nan"))
    # JudgeVerdict's Field(ge=0.0, le=1.0) rejects nan at construction (nan
    # fails every comparison): the verdict is never built, so scoring raises
    # pydantic ValidationError before a fabricated score can reach the record.
    with pytest.raises(ValidationError):
        RubricScorer(judge).score(
            task=_rubric_task(), candidate_output="ok", candidate_model_id="gpt-5.5"
        )


# --- human scoring -------------------------------------------------------- #


def test_human_pending_has_null_score_and_success() -> None:
    # Invariant #5: pending → score=None, success=None until confirmed.
    verdict = HumanScorer().pending(task=_human_task(), candidate_model_id="gpt-5.5")
    assert verdict.pending is True
    assert verdict.score is None
    assert verdict.success is None


def test_human_confirm_sets_real_bool_success() -> None:
    verdict = HumanScorer().confirm(
        task=_human_task(), candidate_model_id="gpt-5.5", passed=True, rationale="ok"
    )
    assert verdict.success is True
    assert verdict.score == 1.0
    assert verdict.pending is False
    assert verdict.judge_model_id == "operator"


# --- typing invariants on ScoreVerdict ------------------------------------ #


def test_pending_with_non_null_score_rejected() -> None:
    with pytest.raises(ValueError, match="pending"):
        ScoreVerdict(
            task_id="t",
            candidate_model_id="m",
            method="human",
            pending=True,
            score=0.5,
        )


def test_bool_score_rejected_not_coerced() -> None:
    # Invariant #2/#3: booleans never coerce to 0.0/1.0.
    with pytest.raises(ValueError, match="score must be a float, not a bool"):
        ScoreVerdict(
            task_id="t",
            candidate_model_id="m",
            method="rubric",
            score=True,  # type: ignore[arg-type]
        )


def test_nan_score_rejected() -> None:
    with pytest.raises(ValueError):
        ScoreVerdict(
            task_id="t",
            candidate_model_id="m",
            method="rubric",
            score=math.nan,
        )
