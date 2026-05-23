"""§5.5 voice-discipline suppression for inline ad placements.

The Sprint 25+ inline-sponsor card pattern is gated by a
voice-discipline test: the card suppresses itself when the
surrounding prose pattern would be disrupted. This module is the
substrate-side predicate the AdSlot React component (its
`shouldSuppress` prop) consumes.

Discipline:
- Inline placements get the more stringent threshold (default 0.85)
- Page-border placements get the lower threshold (0.65) — they don't
  interrupt prose flow as severely
- A voice score below threshold → suppress
- A surrounding context that flagged any HEAVY violation
  (BULLET_ABUSE / SLOP_BOILERPLATE) → suppress regardless of score
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from .rubric import (
    ViolationKind,
    VoiceStyleScore,
    score_voice_style_detailed,
)


class SuppressionVerdictKind(str, enum.Enum):
    RENDER = "render"
    SUPPRESS = "suppress"


@dataclass(frozen=True)
class SuppressionContext:
    """The placement context the AdSlot caller passes."""

    surrounding_text: str
    pattern: str  # "page-border" | "inline-sponsor"
    # Page-border placements live below the prose, so the voice-impact
    # test is more permissive. Inline placements interrupt prose, so
    # the test is stricter.


@dataclass(frozen=True)
class SuppressionVerdict:
    kind: SuppressionVerdictKind
    reason: str
    voice_score: float


_DEFAULT_THRESHOLDS = {
    "page-border": 0.65,
    "inline-sponsor": 0.85,
}


_HEAVY_VIOLATIONS = frozenset({
    ViolationKind.BULLET_ABUSE,
    ViolationKind.SLOP_BOILERPLATE,
})


def evaluate_inline_suppression(
    context: SuppressionContext,
    *,
    thresholds: dict[str, float] = None,  # type: ignore[assignment]
) -> SuppressionVerdict:
    """Return RENDER or SUPPRESS based on the §5.5 rubric."""
    th = thresholds if thresholds is not None else _DEFAULT_THRESHOLDS
    threshold = th.get(context.pattern, 0.85)

    rubric: VoiceStyleScore = score_voice_style_detailed(context.surrounding_text)

    # Heavy-violation rule short-circuits regardless of score.
    heavy_hits = [v for v in rubric.violations if v.kind in _HEAVY_VIOLATIONS]
    if heavy_hits:
        return SuppressionVerdict(
            kind=SuppressionVerdictKind.SUPPRESS,
            reason=(
                f"§5.5 heavy violation in surrounding context: "
                f"{[v.kind.value for v in heavy_hits]}"
            ),
            voice_score=rubric.score,
        )

    if rubric.score < threshold:
        return SuppressionVerdict(
            kind=SuppressionVerdictKind.SUPPRESS,
            reason=(
                f"voice score {rubric.score:.2f} below {context.pattern} "
                f"threshold {threshold:.2f}"
            ),
            voice_score=rubric.score,
        )

    return SuppressionVerdict(
        kind=SuppressionVerdictKind.RENDER,
        reason=(
            f"voice score {rubric.score:.2f} ≥ {context.pattern} "
            f"threshold {threshold:.2f}"
        ),
        voice_score=rubric.score,
    )
