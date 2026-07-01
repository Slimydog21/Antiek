"""Sprint 25+ ad-inventory scaling gates.

This module is the substrate-side policy wrapper for the frontend
``AdSlot.shouldSuppress`` contract.  The lower-level voice rubric lives in
``substrate.voice_style.suppression``; this file binds it to ad-slot patterns
so callers can make the same decision for page-border and inline sponsor
placements without re-encoding thresholds in UI code.

Important boundary: this module never selects an ad and never books revenue.
It only decides whether a candidate placement is allowed to render without
damaging the section 5.5 voice-and-style discipline.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from substrate.voice_style import SuppressionContext, evaluate_inline_suppression
from substrate.voice_style.suppression import SuppressionVerdictKind


class AdSlotPattern(str, enum.Enum):
    PAGE_BORDER = "page-border"
    INLINE_SPONSOR = "inline-sponsor"


@dataclass(frozen=True)
class AdPlacementContext:
    """The context required to decide whether a candidate ad may render."""

    page_id: str
    surrounding_text: str
    pattern: AdSlotPattern | str = AdSlotPattern.PAGE_BORDER


@dataclass(frozen=True)
class AdPlacementDecision:
    """Decision shape consumed by frontend/API callers.

    ``should_suppress`` maps directly to the React ``AdSlot`` prop.
    ``reason`` is safe to put in an audit log or ``onSuppressed`` callback.
    """

    page_id: str
    pattern: AdSlotPattern
    should_suppress: bool
    reason: str
    voice_score: float


def evaluate_ad_placement(
    context: AdPlacementContext,
    *,
    inline_threshold: float = 0.85,
    page_border_threshold: float = 0.65,
) -> AdPlacementDecision:
    """Return the render/suppress verdict for a candidate placement.

    Inline sponsor cards interrupt prose, so they use the stricter threshold.
    Page-border placements sit outside the reading column and are more
    permissive.  Unknown patterns are rejected loudly; silently treating a new
    placement as page-border would let a more intrusive format bypass review.
    """

    pattern = _coerce_pattern(context.pattern)
    verdict = evaluate_inline_suppression(
        SuppressionContext(
            surrounding_text=context.surrounding_text,
            pattern=pattern.value,
        ),
        thresholds={
            AdSlotPattern.INLINE_SPONSOR.value: inline_threshold,
            AdSlotPattern.PAGE_BORDER.value: page_border_threshold,
        },
    )
    return AdPlacementDecision(
        page_id=context.page_id,
        pattern=pattern,
        should_suppress=verdict.kind == SuppressionVerdictKind.SUPPRESS,
        reason=verdict.reason,
        voice_score=verdict.voice_score,
    )


def should_suppress_ad_slot(
    *,
    page_id: str,
    surrounding_text: str,
    pattern: AdSlotPattern | str,
) -> bool:
    """Small boolean helper for render-layer callers."""

    return evaluate_ad_placement(
        AdPlacementContext(
            page_id=page_id,
            surrounding_text=surrounding_text,
            pattern=pattern,
        )
    ).should_suppress


def _coerce_pattern(pattern: AdSlotPattern | str) -> AdSlotPattern:
    if isinstance(pattern, AdSlotPattern):
        return pattern
    try:
        return AdSlotPattern(pattern)
    except ValueError as exc:
        valid = ", ".join(p.value for p in AdSlotPattern)
        raise ValueError(f"unknown ad slot pattern {pattern!r}; expected one of {valid}") from exc
