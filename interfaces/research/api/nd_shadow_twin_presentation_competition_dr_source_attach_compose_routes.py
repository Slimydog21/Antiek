"""Registerable HTTP surface for ND shadow + twin presentation competition DR source-attach."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.recursive_twin_presentation_competition_dr_source_attach_compose_routes import (
    CompetitionPackBody,
    PresentationBody,
    TwinBody,
)
from substrate.nd_shadow_twin_presentation_competition_dr_source_attach_compose import (
    NdShadowTwinPresentationCompetitionDrSourceAttachComposeError,
    compose_nd_shadow_twin_presentation_competition_dr_source_attach,
)

nd_shadow_twin_presentation_competition_dr_source_attach_compose_router = APIRouter(
    prefix="/research/nd-shadow-twin-presentation-competition-dr-source-attach",
    tags=["nd-shadow-twin-presentation-competition-dr-source-attach-compose"],
)


class NdShadowBody(BaseModel):
    model_config = {"extra": "forbid"}

    selected_model_id: str = Field(min_length=1, max_length=128)
    nd_recommended_model_id: str | None = Field(default=None, max_length=128)
    kill_switch_on: bool = Field(strict=True)
    confidence: float | None = Field(default=None, ge=0, le=1)
    task: str | None = Field(default=None, max_length=256)
    inventory_model_ids: list[str] | None = None


class TwinPresentationBody(BaseModel):
    model_config = {"extra": "forbid"}

    twin: TwinBody
    presentation: PresentationBody
    competition_pack: CompetitionPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    nd_shadow: NdShadowBody
    twin_presentation: TwinPresentationBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@nd_shadow_twin_presentation_competition_dr_source_attach_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_nd_shadow_twin_presentation_competition_dr_source_attach(
            nd_shadow=req.nd_shadow.model_dump(),
            twin_presentation=req.twin_presentation.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except NdShadowTwinPresentationCompetitionDrSourceAttachComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_nd_shadow_twin_presentation_competition_dr_source_attach_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        nd_shadow_twin_presentation_competition_dr_source_attach_compose_router
    )


__all__ = [
    "nd_shadow_twin_presentation_competition_dr_source_attach_compose_router",
    "register_nd_shadow_twin_presentation_competition_dr_source_attach_compose_routes",
]
