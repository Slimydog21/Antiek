"""Closed, versioned qualitative rubrics for blinded benchmark judging."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from ..suite import TaskClass

RUBRIC_VERSION = "qualitative-v1"
MIN_SCORE = 1
MAX_SCORE = 5
MAX_RATIONALE_CHARS = 1_000
MAX_EVIDENCE_REFS_PER_AXIS = 20
_EVIDENCE_REF = re.compile(r"[AB]:[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")

_AXES: dict[TaskClass, tuple[str, ...]] = {
    "distill": ("fidelity", "compression", "clarity"),
    "synthesize": ("integration", "source_handling", "nuance"),
    "wrestle": ("tension_handling", "reasoning", "nuance"),
    "book_qa": ("responsiveness", "textual_grounding", "clarity"),
}


@dataclass(frozen=True)
class AxisJudgment:
    score: int
    rationale: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class Rubric:
    version: str
    task_class: TaskClass
    axes: tuple[str, ...]
    minimum: int = MIN_SCORE
    maximum: int = MAX_SCORE


def rubric_for(task_class: TaskClass) -> Rubric:
    return Rubric(RUBRIC_VERSION, task_class, _AXES[task_class])


def validate_judgments(rubric: Rubric, version: str, judgments: Mapping[str, AxisJudgment]) -> None:
    if version != rubric.version:
        raise ValueError("rubric-version drift")
    if set(judgments) != set(rubric.axes):
        raise ValueError("axis set does not match rubric")
    for axis, judgment in judgments.items():
        if (
            not isinstance(judgment.score, int)
            or isinstance(judgment.score, bool)
            or not rubric.minimum <= judgment.score <= rubric.maximum
        ):
            raise ValueError(f"score for {axis} is out of range")
        if not judgment.rationale.strip():
            raise ValueError(f"rationale for {axis} is required")
        if len(judgment.rationale) > MAX_RATIONALE_CHARS:
            raise ValueError(f"rationale for {axis} is too long")
        if (
            not judgment.evidence_refs
            or len(judgment.evidence_refs) > MAX_EVIDENCE_REFS_PER_AXIS
            or not all(_EVIDENCE_REF.fullmatch(ref) for ref in judgment.evidence_refs)
        ):
            raise ValueError(f"evidence references for {axis} are required")
