"""Registerable HTTP surface for MO unattended + source attach model decision."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.source_attach_model_decision_twin_search_compose_routes import (
    DecisionPackBody,
    SourcesBody,
)
from substrate.mo_unattended_source_attach_model_decision_compose import (
    MoUnattendedSourceAttachModelDecisionComposeError,
    compose_mo_unattended_source_attach_model_decision,
)

mo_unattended_source_attach_model_decision_compose_router = APIRouter(
    prefix="/research/mo-unattended-source-attach-model-decision",
    tags=["mo-unattended-source-attach-model-decision-compose"],
)


class GoalBody(BaseModel):
    model_config = {"extra": "forbid"}

    goal_id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=2000)


class MoBody(BaseModel):
    model_config = {"extra": "forbid"}

    operator_id: str = Field(min_length=1, max_length=256)
    work_minutes: float = Field(gt=0)
    goals: list[GoalBody] = Field(min_length=1)
    price_ceiling_ack: bool = Field(strict=True)
    stage: Literal["recommend_only", "approve_ceiling", "unattended_pack"]
    usd_per_hour: float | None = Field(default=None, ge=0)
    goal_intensity: float | None = Field(default=None, gt=0)
    approved_ceiling_usd: float | None = Field(default=None, ge=0)
    below_recommend_override: bool | None = Field(default=None, strict=True)
    unattended_ack: bool | None = Field(default=None, strict=True)
    spend_consent: bool | None = Field(default=None, strict=True)


class ResearchPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    sources: SourcesBody
    decision_pack: DecisionPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    mo: MoBody
    research_pack: ResearchPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@mo_unattended_source_attach_model_decision_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_mo_unattended_source_attach_model_decision(
            mo=req.mo.model_dump(),
            research_pack=req.research_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except MoUnattendedSourceAttachModelDecisionComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_mo_unattended_source_attach_model_decision_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        mo_unattended_source_attach_model_decision_compose_router
    )


__all__ = [
    "mo_unattended_source_attach_model_decision_compose_router",
    "register_mo_unattended_source_attach_model_decision_compose_routes",
]
