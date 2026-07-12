"""Deep-research quality rubric scorer (pure, advisory).

Operator vision: "the highest quality deep research product in the world" requires
*measurable* quality, not vibes. This module scores a completed deep-research
artifact (``ResearchArtifactBody``) on five falsifiable rubric axes derived from
what makes a DR output trustworthy and useful.

Honesty rules (load-bearing):
* Every score is a finite float in [0.0, 1.0]; 0.0 when unmeasurable, never invented.
* An axis that cannot be measured for an artifact reports ``measured=False`` and
  contributes nothing to the overall mean (only measured axes are averaged).
* The scorer is deterministic: same artifact in -> same score out. No LLM, no
  network, no mutation. ``authority`` is always advisory.
* Booleans never coerce to numeric scores via ``float()`` traps; scores are
  explicit literals or clamped arithmetic on integer counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from substrate.research_artifact.schema import ResearchArtifactBody

AxisName = Literal[
    "citation_density",
    "grounding_completeness",
    "uncertainty_surfacing",
    "conflict_resolution",
    "synthesis_present",
]

_CONFLICT_MARKERS: tuple[str, ...] = (
    "however",
    "but ",
    "conflict",
    "disagree",
    "tension",
    "caveat",
    "although",
)


@dataclass(frozen=True)
class RubricAxisScore:
    """One rubric axis verdict for a single artifact."""

    axis: AxisName
    score: float
    measured: bool
    reason: str


@dataclass(frozen=True)
class DRQualityScore:
    """Aggregate quality verdict across all measured axes."""

    investigation_id: str
    overall: float
    axes: tuple[RubricAxisScore, ...]
    measured_count: int
    notes: tuple[str, ...]
    authority: str


def _clamp01(value: float) -> float:
    """Clamp to [0.0, 1.0]; guards against float overflow on huge counts."""
    if value != value:  # NaN
        return 0.0
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _has_conflict_marker(text: str) -> str | None:
    lowered = text.lower()
    for marker in _CONFLICT_MARKERS:
        if marker in lowered:
            return marker
    return None


def _score_citation_density(body: ResearchArtifactBody) -> RubricAxisScore:
    insights = body.insights
    total = len(insights)
    if total == 0:
        return RubricAxisScore(
            axis="citation_density",
            score=0.0,
            measured=False,
            reason="no insights present — citation density unmeasurable",
        )
    cited = sum(1 for ins in insights if ins.source_document_id)
    density = _clamp01(cited / total)
    return RubricAxisScore(
        axis="citation_density",
        score=density,
        measured=True,
        reason=f"{cited}/{total} insights cite a source_document_id",
    )


def _score_grounding_completeness(body: ResearchArtifactBody) -> RubricAxisScore:
    if body.synthesis_withheld or body.synthesis_excerpt is None:
        return RubricAxisScore(
            axis="grounding_completeness",
            score=0.0,
            measured=False,
            reason="synthesis withheld or absent — grounding unmeasurable",
        )
    excerpt = body.synthesis_excerpt.strip()
    score = 1.0 if excerpt else 0.0
    return RubricAxisScore(
        axis="grounding_completeness",
        score=score,
        measured=True,
        reason=(
            "non-empty grounded synthesis present"
            if score == 1.0
            else "synthesis_excerpt is blank"
        ),
    )


def _score_uncertainty_surfacing(body: ResearchArtifactBody) -> RubricAxisScore:
    count = len(body.open_questions)
    score = 1.0 if count >= 1 else 0.0
    return RubricAxisScore(
        axis="uncertainty_surfacing",
        score=score,
        measured=True,
        reason=f"{count} open question(s) surfaced",
    )


def _score_conflict_resolution(body: ResearchArtifactBody) -> RubricAxisScore:
    excerpt = body.synthesis_excerpt
    if not isinstance(excerpt, str) or excerpt.strip() == "":
        return RubricAxisScore(
            axis="conflict_resolution",
            score=0.0,
            measured=False,
            reason="no synthesis excerpt — conflict resolution unmeasurable",
        )
    marker = _has_conflict_marker(excerpt)
    if marker is not None:
        score = 1.0
        reason = f"explicit conflict language detected ('{marker.strip()}')"
    else:
        score = 0.5
        reason = "no explicit conflict language detected (neutral, not a failure)"
    return RubricAxisScore(
        axis="conflict_resolution",
        score=score,
        measured=True,
        reason=reason,
    )


def _score_synthesis_present(body: ResearchArtifactBody) -> RubricAxisScore:
    excerpt = body.synthesis_excerpt
    present = isinstance(excerpt, str) and excerpt.strip() != ""
    return RubricAxisScore(
        axis="synthesis_present",
        score=1.0 if present else 0.0,
        measured=True,
        reason="non-empty synthesis_excerpt" if present else "synthesis_excerpt missing",
    )


def score_deep_research_quality(body: ResearchArtifactBody) -> DRQualityScore:
    """Score a completed deep-research artifact on five falsifiable rubric axes.

    Pure, deterministic, advisory-only. Never dispatches a model, reads network,
    or mutates state. ``overall`` is the mean of MEASURED axes only; 0.0 when no
    axis is measurable.
    """
    axes: tuple[RubricAxisScore, ...] = (
        _score_citation_density(body),
        _score_grounding_completeness(body),
        _score_uncertainty_surfacing(body),
        _score_conflict_resolution(body),
        _score_synthesis_present(body),
    )

    measured = tuple(a for a in axes if a.measured)
    measured_count = len(measured)
    if measured_count == 0:
        overall = 0.0
        notes: tuple[str, ...] = ("no measurable axes — overall=0.0",)
    else:
        overall = _clamp01(sum(a.score for a in measured) / measured_count)
        notes = ()

    return DRQualityScore(
        investigation_id=body.investigation_id,
        overall=overall,
        axes=axes,
        measured_count=measured_count,
        notes=notes,
        authority="deep_research_quality_rubric_advisory",
    )


__all__ = [
    "AxisName",
    "DRQualityScore",
    "RubricAxisScore",
    "score_deep_research_quality",
]
