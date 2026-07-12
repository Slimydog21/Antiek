"""Deep-research quality measurement (pure, advisory).

Scores completed deep-research artifacts on falsifiable rubric axes. This package
is the seed of the DR-quality benchmark (see
``.infinite/sprint-briefs/deep-research-quality-competitive-spec.md``).
"""

from .rubric_scorer import (
    AxisName,
    DRQualityScore,
    RubricAxisScore,
    score_deep_research_quality,
)

__all__ = [
    "AxisName",
    "DRQualityScore",
    "RubricAxisScore",
    "score_deep_research_quality",
]
