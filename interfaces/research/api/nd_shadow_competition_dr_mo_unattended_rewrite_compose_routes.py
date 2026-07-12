"""Registerable HTTP surface for ND shadow REJECT over competition DR MO rewrite."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.competition_dr_mo_unattended_source_attach_rewrite_compose_routes import (
    CompetitionBody,
    MoPackBody,
)
from substrate.nd_shadow_competition_dr_mo_unattended_rewrite_compose import (
    NdShadowCompetitionDrMoUnattendedRewriteComposeError,
    compose_nd_shadow_competition_dr_mo_unattended_rewrite,
)

nd_shadow_competition_dr_mo_unattended_rewrite_compose_router = APIRouter(
    prefix="/research/nd-shadow-competition-dr-mo-unattended-rewrite",
    tags=["nd-shadow-competition-dr-mo-unattended-rewrite-compose"],
)


class NdShadowBody(BaseModel):
    model_config = {"extra": "forbid"}

    selected_model_id: str = Field(min_length=1, max_length=256)
    nd_recommended_model_id: str | None = Field(default=None, max_length=256)
    kill_switch_on: bool = Field(strict=True)
    confidence: float | None = Field(default=None, ge=0, le=1)
    task: str | None = Field(default=None, max_length=256)
    inventory_model_ids: list[str] | None = None


class CompetitionPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    competition: CompetitionBody
    mo_pack: MoPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    nd_shadow: NdShadowBody
    competition_pack: CompetitionPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@nd_shadow_competition_dr_mo_unattended_rewrite_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_nd_shadow_competition_dr_mo_unattended_rewrite(
            nd_shadow=req.nd_shadow.model_dump(),
            competition_pack=req.competition_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except NdShadowCompetitionDrMoUnattendedRewriteComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_nd_shadow_competition_dr_mo_unattended_rewrite_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        nd_shadow_competition_dr_mo_unattended_rewrite_compose_router
    )


__all__ = [
    "nd_shadow_competition_dr_mo_unattended_rewrite_compose_router",
    "register_nd_shadow_competition_dr_mo_unattended_rewrite_compose_routes",
    "NdShadowBody",
    "CompetitionPackBody",
]
