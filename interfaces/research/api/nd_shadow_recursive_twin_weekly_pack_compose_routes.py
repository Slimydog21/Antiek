"""Registerable HTTP surface for ND shadow over twin presentation weekly source-attach."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.recursive_twin_presentation_weekly_pack_compose_routes import (
    PresentationBody,
    TwinBody,
    WeeklyPackBody,
)
from substrate.nd_shadow_recursive_twin_weekly_pack_compose import (
    NdShadowRecursiveTwinWeeklyPackComposeError,
    compose_nd_shadow_recursive_twin_weekly_pack,
)

nd_shadow_recursive_twin_weekly_pack_compose_router = APIRouter(
    prefix="/research/nd-shadow-recursive-twin-weekly-pack",
    tags=["nd-shadow-recursive-twin-weekly-pack-compose"],
)


class NdShadowBody(BaseModel):
    model_config = {"extra": "forbid"}

    selected_model_id: str = Field(min_length=1, max_length=128)
    nd_recommended_model_id: str | None = Field(default=None, max_length=128)
    kill_switch_on: bool = Field(strict=True)
    confidence: float | None = Field(default=None, ge=0, le=1)
    task: str | None = Field(default=None, max_length=256)
    inventory_model_ids: list[str] | None = Field(default=None)


class TwinPresentationBody(BaseModel):
    model_config = {"extra": "forbid"}

    twin: TwinBody
    presentation: PresentationBody
    weekly_pack: WeeklyPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    nd_shadow: NdShadowBody
    twin_presentation: TwinPresentationBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@nd_shadow_recursive_twin_weekly_pack_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_nd_shadow_recursive_twin_weekly_pack(
            nd_shadow=req.nd_shadow.model_dump(),
            twin_presentation=req.twin_presentation.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except NdShadowRecursiveTwinWeeklyPackComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_nd_shadow_recursive_twin_weekly_pack_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        nd_shadow_recursive_twin_weekly_pack_compose_router
    )


__all__ = [
    "nd_shadow_recursive_twin_weekly_pack_compose_router",
    "register_nd_shadow_recursive_twin_weekly_pack_compose_routes",
]
