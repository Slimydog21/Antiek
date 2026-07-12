"""Benchmark scoring — the honesty keystone.

Three scoring methods, chosen per task. **A model never grades its own output.**
This is enforced mechanically, not by convention: the rubric scorer rejects a
judge whose ``model_id`` matches the candidate's.

Output contract (frozen, feeds the recorder):

- ``score`` is a finite float in [0, 1] **or** ``None`` (pending/failed).
  Booleans never coerce to 0.0/1.0 — a bool input becomes ``None`` (mirrors
  ``_finite_score`` in the usage-learn consumer).
- ``success`` is a real ``bool`` **or** ``None``. Non-bool inputs are rejected,
  never stringily coerced (mirrors ``_as_bool_success``).
- ``pending`` marks a not-yet-scored run (e.g. human scoring awaiting the
  operator). Pending ⇒ ``score=None, success=None`` — nothing invented.

No network lives here. The rubric judge is an injectable ``RubricJudge``
protocol; tests pass a fake. The pure layer never holds live credentials.
"""

from __future__ import annotations

import math
import unicodedata
from typing import Protocol

from pydantic import BaseModel, Field, field_validator, model_validator

from .task_registry import BenchTask

ScoringMethod = str  # re-exported shape; canonical values in task_registry


def _reject_bool_score(value: object) -> object:
    """Before-validator: a bool score is rejected before pydantic coerces it to 1.0/0.0.

    Mirrors ``_finite_score`` in the usage-learn consumer: booleans are never a
    valid score. Catching pre-coercion (mode='before') is load-bearing because
    pydantic's float field would otherwise silently turn ``True`` into ``1.0``.
    """
    if isinstance(value, bool):
        raise ValueError("score must be a float, not a bool")
    return value


class RubricJudge(Protocol):
    """A heterogeneous LLM judge: scores output against a rubric.

    Implementations MUST ensure the judge is a different model lineage than the
    candidate; the scorer double-checks ``judge_model_id`` defensively.
    """

    judge_model_id: str

    def judge(
        self,
        *,
        rubric: str,
        prompt: str,
        candidate_output: str,
        candidate_model_id: str,
    ) -> JudgeVerdict:
        ...


class JudgeVerdict(BaseModel):
    """Structured verdict from a rubric judge."""

    model_config = {"frozen": True}

    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    rationale: str
    judge_model_id: str

    @model_validator(mode="after")
    def _reject_self_grade_in_verdict(self) -> JudgeVerdict:
        # Defensive: a judge must never report its own id as the verdict's judge
        # if it equals the candidate. The scorer checks the candidate match
        # separately; this guards a judge that echoes the wrong id.
        if not self.judge_model_id.strip():
            raise ValueError("JudgeVerdict.judge_model_id must be non-empty")
        return self


class SelfGradeRejected(ValueError):
    """A candidate model was asked to grade its own output. Mechanically refused."""


class ScoreVerdict(BaseModel):
    """The frozen output of scoring one run. Feeds the recorder (dual-output)."""

    model_config = {"frozen": True}

    task_id: str
    candidate_model_id: str
    method: ScoringMethod
    score: float | None = Field(default=None)

    @field_validator("score", mode="before")
    @classmethod
    def _no_bool_score(cls, value: object) -> object:
        return _reject_bool_score(value)
    success: bool | None = None
    pending: bool = False
    disputed: bool = False
    rationale: str | None = None
    judge_model_id: str | None = None
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _pending_implies_nulls(self) -> ScoreVerdict:
        if self.pending and (self.score is not None or self.success is not None):
            raise ValueError("pending verdicts must have score=None and success=None")
        return self

    @model_validator(mode="after")
    def _score_finite_in_range_or_none(self) -> ScoreVerdict:
        if self.score is None:
            return self
        if not math.isfinite(self.score) or not (0.0 <= self.score <= 1.0):
            raise ValueError(f"score must be finite in [0,1], got {self.score}")
        return self


class ExactScorer:
    """Deterministic normalised-match scorer for ``exact`` tasks.

    Normalisation (whitespace/case/unicode NFKC) is recorded so the verdict is
    re-checkable: ``success = (normalised output == normalised expected)`` and
    ``score = 1.0 if success else 0.0``.
    """

    def score(self, *, task: BenchTask, candidate_output: str) -> ScoreVerdict:
        if task.scoring != "exact" or not task.expected:
            raise ValueError(f"ExactScorer requires an exact task; got {task.task_id}")
        norm_out = _normalise(candidate_output)
        norm_exp = _normalise(task.expected)
        match = norm_out == norm_exp
        return ScoreVerdict(
            task_id=task.task_id,
            candidate_model_id="",  # filled by the runner; exact scoring is model-agnostic
            method="exact",
            score=1.0 if match else 0.0,
            success=match,
            rationale=f"normalised match={match}",
            notes=[f"norm(out)={norm_out!r}", f"norm(expected)={norm_exp!r}"],
        )


class RubricScorer:
    """Heterogeneous-LLM-judge scorer for ``rubric`` tasks.

    Self-grade is mechanically impossible: if ``judge.judge_model_id`` equals
    ``candidate_model_id``, the scorer raises ``SelfGradeRejected`` and no
    verdict is recorded. A second judge (optional) surfaces disagreement as
    ``disputed=True`` without averaging away the conflict.
    """

    def __init__(
        self,
        judge: RubricJudge,
        *,
        second_judge: RubricJudge | None = None,
    ) -> None:
        self._judge = judge
        self._second_judge = second_judge

    def score(
        self,
        *,
        task: BenchTask,
        candidate_output: str,
        candidate_model_id: str,
    ) -> ScoreVerdict:
        if task.scoring != "rubric" or not task.rubric:
            raise ValueError(f"RubricScorer requires a rubric task; got {task.task_id}")
        _reject_self_grade(
            judge_model_id=self._judge.judge_model_id,
            candidate_model_id=candidate_model_id,
        )
        primary = self._judge.judge(
            rubric=task.rubric,
            prompt=task.prompt,
            candidate_output=candidate_output,
            candidate_model_id=candidate_model_id,
        )
        notes: list[str] = []
        disputed = False
        if self._second_judge is not None:
            _reject_self_grade(
                judge_model_id=self._second_judge.judge_model_id,
                candidate_model_id=candidate_model_id,
            )
            second = self._second_judge.judge(
                rubric=task.rubric,
                prompt=task.prompt,
                candidate_output=candidate_output,
                candidate_model_id=candidate_model_id,
            )
            if second.passed != primary.passed:
                disputed = True
                notes.append(
                    f"judge disagreement: primary={primary.judge_model_id} "
                    f"second={second.judge_model_id}"
                )
        return ScoreVerdict(
            task_id=task.task_id,
            candidate_model_id=candidate_model_id,
            method="rubric",
            score=_to_finite_or_none(primary.score),
            success=bool(primary.passed),
            disputed=disputed,
            rationale=primary.rationale,
            judge_model_id=primary.judge_model_id,
            notes=notes,
        )


class HumanScorer:
    """Asynchronous human scorer for ``human`` tasks.

    Until the operator confirms, the verdict is ``pending``: ``score=None`` and
    ``success=None``. Nothing is invented.
    """

    def pending(self, *, task: BenchTask, candidate_model_id: str) -> ScoreVerdict:
        if task.scoring != "human":
            raise ValueError(f"HumanScorer requires a human task; got {task.task_id}")
        return ScoreVerdict(
            task_id=task.task_id,
            candidate_model_id=candidate_model_id,
            method="human",
            pending=True,
            rationale="awaiting operator confirmation",
        )

    def confirm(
        self,
        *,
        task: BenchTask,
        candidate_model_id: str,
        passed: bool,
        rationale: str,
    ) -> ScoreVerdict:
        if task.scoring != "human":
            raise ValueError(f"HumanScorer requires a human task; got {task.task_id}")
        return ScoreVerdict(
            task_id=task.task_id,
            candidate_model_id=candidate_model_id,
            method="human",
            score=1.0 if passed else 0.0,
            success=bool(passed),
            rationale=rationale,
            judge_model_id="operator",
        )


def _reject_self_grade(*, judge_model_id: str, candidate_model_id: str) -> None:
    if judge_model_id.strip() and judge_model_id == candidate_model_id:
        raise SelfGradeRejected(
            f"judge {judge_model_id!r} cannot grade its own output "
            f"(candidate {candidate_model_id!r}); use a different-lineage judge"
        )


def _to_finite_or_none(value: float) -> float | None:
    """Coerce a judge-reported score to finite-in-[0,1] or None.

    NaN/Inf and out-of-range become None (honest "unmeasured"), never clamped
    to a fabricated value. Booleans are rejected upstream by JudgeVerdict.
    """
    if isinstance(value, bool):
        return None
    if not math.isfinite(value):
        return None
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return float(value)


def _normalise(text: str) -> str:
    """Case/whitespace/unicode-normalise for deterministic exact matching."""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())
