"""Registerable HTTP surface for marketplace free + competition DR ND shadow pack."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.competition_dr_nd_shadow_source_attach_weekly_learn_compose_routes import (
    CompetitionBody,
    NdPackBody,
)
from substrate.marketplace_free_competition_dr_nd_shadow_source_attach_compose import (
    MarketplaceFreeCompetitionDrNdShadowSourceAttachComposeError,
    compose_marketplace_free_competition_dr_nd_shadow_source_attach,
)

marketplace_free_competition_dr_nd_shadow_source_attach_compose_router = APIRouter(
    prefix="/research/marketplace-free-competition-dr-nd-shadow-source-attach",
    tags=["marketplace-free-competition-dr-nd-shadow-source-attach-compose"],
)


class MarketBody(BaseModel):
    model_config = {"extra": "forbid"}

    title: str = Field(min_length=1, max_length=2000)
    account_id: str = Field(min_length=1, max_length=256)
    free_copy_available: bool | None = None
    free_html_projection_sha: str | None = Field(default=None, max_length=256)
    purchase_ack: bool = Field(strict=True)
    port_requested: bool = Field(strict=True)
    purchase_html_projection_sha: str | None = Field(default=None, max_length=256)


class CompetitionPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    competition: CompetitionBody
    nd_pack: NdPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    market: MarketBody
    competition_pack: CompetitionPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@marketplace_free_competition_dr_nd_shadow_source_attach_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_marketplace_free_competition_dr_nd_shadow_source_attach(
            market=req.market.model_dump(),
            competition_pack=req.competition_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except MarketplaceFreeCompetitionDrNdShadowSourceAttachComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_marketplace_free_competition_dr_nd_shadow_source_attach_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        marketplace_free_competition_dr_nd_shadow_source_attach_compose_router
    )


__all__ = [
    "marketplace_free_competition_dr_nd_shadow_source_attach_compose_router",
    "register_marketplace_free_competition_dr_nd_shadow_source_attach_compose_routes",
]
