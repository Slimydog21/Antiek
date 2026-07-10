"""Versioned qualitative rubric for non-deterministic judge axes.

Deterministic checks (keyword hit, receipt, budget, provenance) stay in code.
A judge scores only axes this module declares, within the integer bounds this
module enforces.  The rubric version is an identity field: changing the rubric
invalidates old evidence by design.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class RubricAxis:
    """One closed qualitative axis with integer bounds and evidence policy."""

    name: str
    min_score: int
    max_score: int
    requires_evidence: bool

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("axis name must not be blank")
        if self.min_score >= self.max_score:
            raise ValueError("min_score must be less than max_score")


@dataclass(frozen=True)
class RubricVersion:
    """Immutable rubric definition keyed by version and task class.

    Changing any axis, bound, or evidence requirement produces a new version.
    Old evidence retains its rubric_version; the scorer validates at claim time.
    """

    version: str
    task_class: str
    axes: tuple[RubricAxis, ...]
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("rubric version must not be blank")
        if not self.task_class.strip():
            raise ValueError("task_class must not be blank")
        if len(self.axes) < 1:
            raise ValueError("rubric must declare at least one axis")
        names: list[str] = []
        for axis in self.axes:
            if axis.name in names:
                raise ValueError(f"duplicate axis name: {axis.name}")
            names.append(axis.name)

    @property
    def axis_names(self) -> tuple[str, ...]:
        return tuple(a.name for a in self.axes)

    def axis(self, name: str) -> RubricAxis:
        for a in self.axes:
            if a.name == name:
                return a
        raise KeyError(f"unknown axis: {name}")


def now_iso() -> str:
    """UTC ISO-8601 timestamp, second precision."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def make_rubric(
    version: str,
    task_class: str,
    axes: tuple[RubricAxis, ...],
) -> RubricVersion:
    """Construct a rubric with a generated creation timestamp."""
    return RubricVersion(
        version=version,
        task_class=task_class,
        axes=axes,
        created_at=now_iso(),
    )


@dataclass(frozen=True)
class AxisScore:
    """One score on one axis, with optional bounded rationale text."""

    axis: str
    score: int
    rationale: str

    def __post_init__(self) -> None:
        if not self.axis.strip():
            raise ValueError("axis must not be blank")


@dataclass(frozen=True)
class JudgeResult:
    """Schema-validated result from an injected JudgeClient."""

    axis_scores: tuple[AxisScore, ...]
    latency_ms: int
    failure_code: str

    @property
    def ok(self) -> bool:
        return self.failure_code == ""


def validate_scores(
    rubric: RubricVersion,
    scores: tuple[AxisScore, ...],
) -> list[str]:
    """Validate axis scores against a rubric; return error list (empty = valid)."""
    errors: list[str] = []
    seen: set[str] = set()
    for score in scores:
        if score.axis in seen:
            errors.append(f"duplicate axis score: {score.axis}")
            continue
        seen.add(score.axis)
        try:
            axis = rubric.axis(score.axis)
        except KeyError:
            errors.append(f"unknown axis: {score.axis}")
            continue
        if not axis.min_score <= score.score <= axis.max_score:
            errors.append(
                f"axis {score.axis}: {score.score} outside "
                f"[{axis.min_score}, {axis.max_score}]"
            )
        if axis.requires_evidence and not score.rationale.strip():
            errors.append(f"axis {score.axis}: evidence required but rationale is blank")
    for axis in rubric.axes:
        if axis.name not in seen:
            errors.append(f"missing axis: {axis.name}")
    return errors
