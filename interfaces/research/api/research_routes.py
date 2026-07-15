"""Safe preview transport for the server-owned research route instrument."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from interfaces.research.api.settings_budget import read_operator_budget
from substrate.dispatch.research_route import (
    RESEARCH_ROUTE_POLICY_VERSION,
    prompt_fingerprint,
    route_choices,
)

research_route_router = APIRouter(prefix="/research/routes", tags=["research"])


class ResearchRoutePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=100_000)


class ResearchRouteCandidateResponse(BaseModel):
    choice_id: str
    tier: Literal["fast", "deep"]
    configuration_fingerprint: str
    display_name: str
    model_policy_label: str
    rationale: str
    ready: bool
    readiness_label: str


class ResearchRouteBudgetResponse(BaseModel):
    authority: Literal["advisory"] = "advisory"
    daily_cap_usd: float | None
    spent_usd: float | None
    spent_status: Literal["known", "unknown"]
    cap_source: str | None
    notes: list[str]
    projection_status: Literal["unavailable"] = "unavailable"
    projection_note: str = (
        "Trajectory cost is unavailable until measured recursive-investigation "
        "telemetry supports an estimator."
    )


class ResearchRoutePreviewResponse(BaseModel):
    policy_version: str
    prompt_fingerprint: str
    candidates: list[ResearchRouteCandidateResponse]
    budget: ResearchRouteBudgetResponse


@research_route_router.post("/preview", response_model=ResearchRoutePreviewResponse)
def preview_research_routes(
    request: Request, req: ResearchRoutePreviewRequest
) -> ResearchRoutePreviewResponse:
    registered = getattr(request.app.state, "registered_providers", set())
    ready = {str(value) for value in registered} if isinstance(
        registered, (set, list, tuple, frozenset)
    ) else set()
    budget = read_operator_budget()
    candidates = []
    for choice in route_choices():
        # Provider identity remains server-side; only readiness and a safe,
        # server-authored human label cross the response boundary.
        from substrate.dispatch.research_tier import resolve_research_tier

        is_ready = resolve_research_tier(choice.tier).provider in ready
        candidates.append(
            ResearchRouteCandidateResponse(
                choice_id=choice.choice_id,
                tier=choice.tier,
                configuration_fingerprint=choice.configuration_fingerprint,
                display_name=choice.display_name,
                model_policy_label=choice.model_policy_label,
                rationale=choice.rationale,
                ready=is_ready,
                readiness_label="Ready" if is_ready else "Provider unavailable",
            )
        )
    return ResearchRoutePreviewResponse(
        policy_version=RESEARCH_ROUTE_POLICY_VERSION,
        prompt_fingerprint=prompt_fingerprint(req.question),
        candidates=candidates,
        budget=ResearchRouteBudgetResponse(
            # Settings may display the daemon's operational default. Research
            # only transports a denominator when an operator/env cap supplied it.
            daily_cap_usd=budget.daily_cap_usd if budget.cap_env is not None else None,
            spent_usd=budget.spent_usd,
            spent_status="known" if budget.spent_status == "known" else "unknown",
            cap_source=budget.cap_env,
            notes=budget.notes,
        ),
    )


__all__ = ["research_route_router"]
