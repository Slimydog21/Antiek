"""Registerable HTTP surface for HTML-native view over settings marketplace free competition."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.settings_add_model_marketplace_free_competition_dr_nd_compose_routes import (
    MarketPackBody,
    SettingsBody,
)
from substrate.html_native_settings_marketplace_free_competition_dr_nd_compose import (
    HtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError,
    compose_html_native_settings_marketplace_free_competition_dr_nd,
)

html_native_settings_marketplace_free_competition_dr_nd_compose_router = APIRouter(
    prefix="/research/html-native-settings-marketplace-free-competition-dr-nd",
    tags=["html-native-settings-marketplace-free-competition-dr-nd-compose"],
)


class HtmlViewBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    asset_id: str = Field(min_length=1, max_length=256)
    html_projection_sha: str | None = Field(default=None, max_length=256)
    view_requested: bool = Field(strict=True)
    twin_bound: bool = Field(strict=True)
    twin_substrate_ready: bool | None = Field(default=None, strict=True)
    claimed_format: str | None = Field(default=None, max_length=64)


class SettingsPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    settings: SettingsBody
    market_pack: MarketPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    html_view: HtmlViewBody
    settings_pack: SettingsPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@html_native_settings_marketplace_free_competition_dr_nd_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_html_native_settings_marketplace_free_competition_dr_nd(
            html_view=req.html_view.model_dump(),
            settings_pack=req.settings_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except HtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_html_native_settings_marketplace_free_competition_dr_nd_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        html_native_settings_marketplace_free_competition_dr_nd_compose_router
    )


__all__ = [
    "html_native_settings_marketplace_free_competition_dr_nd_compose_router",
    "register_html_native_settings_marketplace_free_competition_dr_nd_compose_routes",
]
