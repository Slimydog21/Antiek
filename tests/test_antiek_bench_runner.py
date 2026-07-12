"""Antiek-bench runner — provider-dispatch boundary + scoring composition."""

from __future__ import annotations

import pytest

from substrate.antiek_bench.runner import (
    DEFAULT_SEED,
    DEFAULT_TEMPERATURE,
    RawModelOutput,
    RunResult,
    run_and_score,
)
from substrate.antiek_bench.scorer import JudgeVerdict, SelfGradeRejected
from substrate.antiek_bench.task_registry import BenchTask


def _exact_task(expected: str = "C is true.") -> BenchTask:
    return BenchTask(
        task_id="reasoning::two_step",
        family="reasoning",
        prompt="If A implies B and B implies C, and A is true, what is C?",
        scoring="exact",
        expected=expected,
    )


def _rubric_task() -> BenchTask:
    return BenchTask(
        task_id="writing::summary",
        family="writing",
        prompt="Summarize.",
        scoring="rubric",
        rubric="PASS if covers thesis.",
    )


def _human_task() -> BenchTask:
    return BenchTask(
        task_id="reading_comprehension::main_claim",
        family="reading_comprehension",
        prompt="State the main claim.",
        scoring="human",
    )


class _FakeCaller:
    """A test double for ModelCaller (no network)."""

    def __init__(
        self,
        model_id: str = "gpt-5.5",
        *,
        output: str = "C is true.",
        cost_usd: float | None = 0.002,
    ) -> None:
        self.model_id = model_id
        self._output = output
        self._cost = cost_usd
        self.last_prompt: str | None = None
        self.last_temp: float | None = None
        self.last_seed: int | None = None

    def invoke(self, *, prompt: str, temperature: float, seed: int) -> RawModelOutput:
        self.last_prompt = prompt
        self.last_temp = temperature
        self.last_seed = seed
        return RawModelOutput(
            model_id=self.model_id,
            raw_output=self._output,
            tokens=10,
            latency_ms=500,
            cost_usd=self._cost,
        )


class _FakeJudge:
    def __init__(self, model_id: str, *, passed: bool = True, score: float = 0.9) -> None:
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
            rationale="fake",
            judge_model_id=self.judge_model_id,
        )


# --- exact path ---------------------------------------------------------- #


def test_exact_run_scores_and_stamps_candidate() -> None:
    caller = _FakeCaller(model_id="gpt-5.5", output="C is true.")
    result = run_and_score(task=_exact_task(), caller=caller, week_id="2026-W28")
    assert isinstance(result, RunResult)
    assert result.verdict.success is True
    assert result.verdict.score == 1.0
    assert result.verdict.candidate_model_id == "gpt-5.5"  # stamped post-score


def test_exact_mismatch_scores_zero() -> None:
    caller = _FakeCaller(output="D is false.")
    result = run_and_score(task=_exact_task(), caller=caller, week_id="2026-W28")
    assert result.verdict.success is False
    assert result.verdict.score == 0.0


# --- rubric path --------------------------------------------------------- #


def test_rubric_run_uses_heterogeneous_judge() -> None:
    caller = _FakeCaller(model_id="gpt-5.5")
    judge = _FakeJudge("glm-5.2-judge")
    result = run_and_score(
        task=_rubric_task(), caller=caller, week_id="2026-W28", rubric_judge=judge
    )
    assert result.verdict.success is True
    assert result.verdict.judge_model_id == "glm-5.2-judge"


def test_rubric_without_judge_raises() -> None:
    caller = _FakeCaller()
    with pytest.raises(ValueError, match="requires a rubric_judge"):
        run_and_score(task=_rubric_task(), caller=caller, week_id="2026-W28")


def test_rubric_self_grade_rejected_through_runner() -> None:
    caller = _FakeCaller(model_id="gpt-5.5")
    judge = _FakeJudge("gpt-5.5")  # same model = self-grade
    with pytest.raises(SelfGradeRejected):
        run_and_score(
            task=_rubric_task(), caller=caller, week_id="2026-W28", rubric_judge=judge
        )


# --- human path ---------------------------------------------------------- #


def test_human_run_returns_pending_verdict() -> None:
    caller = _FakeCaller(model_id="gpt-5.5")
    result = run_and_score(task=_human_task(), caller=caller, week_id="2026-W28")
    assert result.verdict.pending is True
    assert result.verdict.score is None
    assert result.verdict.success is None


# --- authority + reproducibility ----------------------------------------- #


def test_pure_runner_never_authorizes_dispatch_or_charge() -> None:
    # Authority flags hardcoded False; the authorized runner sets them after the gate.
    caller = _FakeCaller()
    result = run_and_score(task=_exact_task(), caller=caller, week_id="2026-W28")
    assert result.live_dispatch_authorized is False
    assert result.charge_executed is False


def test_invocation_uses_fixed_temperature_and_seed() -> None:
    caller = _FakeCaller()
    run_and_score(task=_exact_task(), caller=caller, week_id="2026-W28")
    assert caller.last_temp == DEFAULT_TEMPERATURE
    assert caller.last_seed == DEFAULT_SEED


def test_cost_is_provider_reported_none_when_unreported() -> None:
    caller = _FakeCaller(cost_usd=None)  # provider didn't report cost
    result = run_and_score(task=_exact_task(), caller=caller, week_id="2026-W28")
    assert result.raw.cost_usd is None  # never invented as 0


def test_task_prompt_passed_through_to_caller() -> None:
    caller = _FakeCaller()
    task = _exact_task()
    run_and_score(task=task, caller=caller, week_id="2026-W28")
    assert caller.last_prompt == task.prompt
