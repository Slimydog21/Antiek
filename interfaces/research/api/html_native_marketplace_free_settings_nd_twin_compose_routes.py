"""Registerable HTTP surface for HTML-native view over marketplace free settings ND twin."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.marketplace_free_settings_add_model_nd_shadow_twin_compose_routes import (
    MarketBody,
    SettingsPackBody,
)
from substrate.html_native_marketplace_free_settings_nd_twin_compose import (
    HtmlNativeMarketplaceFreeSettingsNdTwinComposeError,
    compose_html_native_marketplace_free_settings_nd_twin,
)

html_native_marketplace_free_settings_nd_twin_compose_router = APIRouter(
    prefix="/research/html-native-marketplace-free-settings-nd-twin",
    tags=["html-native-marketplace-free-settings-nd-twin-compose"],
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


class MarketPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    market: MarketBody
    settings_pack: SettingsPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    html_view: HtmlViewBody
    market_pack: MarketPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@html_native_marketplace_free_settings_nd_twin_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_html_native_marketplace_free_settings_nd_twin(
            html_view=req.html_view.model_dump(),
            market_pack=req.market_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except HtmlNativeMarketplaceFreeSettingsNdTwinComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_html_native_marketplace_free_settings_nd_twin_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        html_native_marketplace_free_settings_nd_twin_compose_router
    )


__all__ = [
    "html_native_marketplace_free_settings_nd_twin_compose_router",
    "register_html_native_marketplace_free_settings_nd_twin_compose_routes",
]
