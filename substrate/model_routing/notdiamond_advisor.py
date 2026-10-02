"""Offline NotDiamond advisor contract.

This module intentionally performs no HTTP calls and imports no NotDiamond SDK.
It gives Settings and future dispatch plumbing a typed boundary for evaluating
NotDiamond as an optional advisor while Antiek's dispatch router remains the
only execution path.
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field

AdvisorMode = Literal["disabled", "shadow", "advisory"]
AdvisorSource = Literal[
    "disabled",
    "local_policy",
    "notdiamond_candidate",
    "advisor_unavailable",
    "advisor_candidate_unavailable",
    "advisor_cache_penalty",
]


class NotDiamondAdvisorCandidate(BaseModel):
    provider: str
    model: str
    tier: str | None = None
    estimated_usd_high: float | None = Field(default=None, ge=0.0)
    pricing_known: bool = False
    cache_status: Literal["warm", "cold", "unknown"] = "unknown"


class NotDiamondExternalRecommendation(BaseModel):
    """A recommendation already obtained from an advisor test double.

    Production code must only construct this after a guarded NotDiamond call in
    a future sprint. The current sprint uses it to validate mapping, fallback,
    and cache rejection without contacting NotDiamond.
    """

    provider: str
    model: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    session_id: str | None = None


class NotDiamondPromotionGate(BaseModel):
    eligible: bool
    required_consecutive_weeks: int = 2
    evidence_week_ids: list[str] = Field(default_factory=list)
    reason: str


class NotDiamondAdvisorRecommendation(BaseModel):
    advisor: Literal["notdiamond"] = "notdiamond"
    mode: AdvisorMode
    available: bool
    provider: str | None = None
    model: str | None = None
    tier: str | None = None
    source: AdvisorSource
    confidence: float | None = None
    session_id: str | None = None
    reason: str
    cache_caveat: str | None = None
    external_call_performed: bool = False
    notdiamond_would_call: bool = False
    promotion_gate: NotDiamondPromotionGate
    notes: list[str] = Field(default_factory=list)


def advisor_mode_from_env() -> AdvisorMode:
    raw = os.environ.get("ANTIEK_ROUTER_ADVISOR", "").strip().lower()
    if raw != "notdiamond":
        return "disabled"
    mode = os.environ.get("ANTIEK_ROUTER_ADVISOR_MODE", "shadow").strip().lower()
    return "advisory" if mode == "advisory" else "shadow"


def resolve_notdiamond_advisor(
    *,
    candidates: list[NotDiamondAdvisorCandidate],
    local_selected: NotDiamondAdvisorCandidate | None,
    mode: AdvisorMode | None = None,
    task_kind: str | None = None,
    external_recommendation: NotDiamondExternalRecommendation | None = None,
    advisor_error: str | None = None,
    promotion_gate: NotDiamondPromotionGate | None = None,
) -> NotDiamondAdvisorRecommendation:
    """Resolve a NotDiamond recommendation against Antiek's configured routes.

    ``external_recommendation`` is deliberately injected by tests or a future
    guarded adapter. This function never obtains it itself.
    """

    resolved_mode = mode or advisor_mode_from_env()
    gate = promotion_gate or default_promotion_gate()
    fallback = local_selected or (candidates[0] if candidates else None)

    if resolved_mode == "disabled":
        return _recommendation(
            mode=resolved_mode,
            available=False,
            source="disabled",
            selected=fallback,
            reason="ANTIEK_ROUTER_ADVISOR is not set to notdiamond",
            gate=gate,
            notdiamond_would_call=False,
        )

    if advisor_error:
        return _recommendation(
            mode=resolved_mode,
            available=False,
            source="advisor_unavailable",
            selected=fallback,
            reason=f"NotDiamond advisor unavailable: {advisor_error}",
            gate=gate,
            notdiamond_would_call=True,
        )

    if external_recommendation is None:
        return _recommendation(
            mode=resolved_mode,
            available=False,
            source="local_policy",
            selected=fallback,
            reason="no NotDiamond call performed in offline advisory sprint",
            gate=gate,
            notdiamond_would_call=True,
            notes=[
                "future live adapter must pass redacted prompt features and configured candidates only"
            ],
        )

    matched = _find_candidate(candidates, external_recommendation)
    if matched is None:
        return _recommendation(
            mode=resolved_mode,
            available=False,
            source="advisor_candidate_unavailable",
            selected=fallback,
            reason="NotDiamond recommended a provider/model that is not configured in dispatch",
            gate=gate,
            confidence=external_recommendation.confidence,
            session_id=external_recommendation.session_id,
            notdiamond_would_call=True,
        )

    cache_caveat = _cache_caveat(
        local_selected=local_selected,
        advisor_selected=matched,
        task_kind=task_kind,
    )
    if cache_caveat is not None:
        return _recommendation(
            mode=resolved_mode,
            available=True,
            source="advisor_cache_penalty",
            selected=fallback,
            reason="NotDiamond recommendation rejected because it would lose a warm cache advantage",
            gate=gate,
            confidence=external_recommendation.confidence,
            session_id=external_recommendation.session_id,
            cache_caveat=cache_caveat,
            notdiamond_would_call=True,
        )

    return _recommendation(
        mode=resolved_mode,
        available=True,
        source="notdiamond_candidate",
        selected=matched,
        reason="NotDiamond recommendation maps to a configured dispatch candidate",
        gate=gate,
        confidence=external_recommendation.confidence,
        session_id=external_recommendation.session_id,
        notdiamond_would_call=True,
    )


def default_promotion_gate() -> NotDiamondPromotionGate:
    return NotDiamondPromotionGate(
        eligible=False,
        reason=(
            "promotion requires two consecutive ratified Antiek-bench weeks "
            "showing better cost-per-acceptable-answer than local policy on "
            "research_question and reading_highlight"
        ),
    )


def _find_candidate(
    candidates: list[NotDiamondAdvisorCandidate],
    recommendation: NotDiamondExternalRecommendation,
) -> NotDiamondAdvisorCandidate | None:
    for candidate in candidates:
        if candidate.provider == recommendation.provider and candidate.model == recommendation.model:
            return candidate
    return None


def _cache_caveat(
    *,
    local_selected: NotDiamondAdvisorCandidate | None,
    advisor_selected: NotDiamondAdvisorCandidate,
    task_kind: str | None,
) -> str | None:
    if local_selected is None:
        return None
    if local_selected.cache_status != "warm" or advisor_selected.cache_status == "warm":
        return None
    if local_selected.estimated_usd_high is None or advisor_selected.estimated_usd_high is None:
        return None
    if advisor_selected.estimated_usd_high <= local_selected.estimated_usd_high:
        return None
    task = f" for {task_kind}" if task_kind else ""
    return (
        "local dispatch candidate keeps a warm cache"
        f"{task}; advisor candidate is projected higher after cold-cache cost"
    )


def _recommendation(
    *,
    mode: AdvisorMode,
    available: bool,
    source: AdvisorSource,
    selected: NotDiamondAdvisorCandidate | None,
    reason: str,
    gate: NotDiamondPromotionGate,
    confidence: float | None = None,
    session_id: str | None = None,
    cache_caveat: str | None = None,
    notdiamond_would_call: bool,
    notes: list[str] | None = None,
) -> NotDiamondAdvisorRecommendation:
    return NotDiamondAdvisorRecommendation(
        mode=mode,
        available=available,
        provider=selected.provider if selected else None,
        model=selected.model if selected else None,
        tier=selected.tier if selected else None,
        source=source,
        confidence=confidence,
        session_id=session_id,
        reason=reason,
        cache_caveat=cache_caveat,
        external_call_performed=False,
        notdiamond_would_call=notdiamond_would_call,
        promotion_gate=gate,
        notes=notes or [],
    )
