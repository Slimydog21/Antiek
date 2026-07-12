"""Registerable HTTP surface for MO price-ceiling over recursive twin note-taker twin search."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.midnight_oil_price_ceiling_approval_compose_routes import (
    GoalBody,
)
from interfaces.research.api.recursive_twin_note_taker_twin_search_model_decision_compose_routes import (
    TwinBody,
    TwinSearchPackBody,
)
from substrate.mo_price_ceiling_recursive_twin_note_taker_twin_search_compose import (
    MoPriceCeilingRecursiveTwinNoteTakerTwinSearchComposeError,
    compose_mo_price_ceiling_recursive_twin_note_taker_twin_search,
)

mo_price_ceiling_recursive_twin_note_taker_twin_search_compose_router = APIRouter(
    prefix="/research/mo-price-ceiling-recursive-twin-note-taker-twin-search",
    tags=["mo-price-ceiling-recursive-twin-note-taker-twin-search-compose"],
)


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


class TwinPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    twin: TwinBody
    twin_search_pack: TwinSearchPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    mo: MoBody
    twin_pack: TwinPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@mo_price_ceiling_recursive_twin_note_taker_twin_search_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_mo_price_ceiling_recursive_twin_note_taker_twin_search(
            mo=req.mo.model_dump(),
            twin_pack=req.twin_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except MoPriceCeilingRecursiveTwinNoteTakerTwinSearchComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_mo_price_ceiling_recursive_twin_note_taker_twin_search_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        mo_price_ceiling_recursive_twin_note_taker_twin_search_compose_router
    )


__all__ = [
    "mo_price_ceiling_recursive_twin_note_taker_twin_search_compose_router",
    "register_mo_price_ceiling_recursive_twin_note_taker_twin_search_compose_routes",
]
