"""Registerable HTTP surface for HTML-native + recursive twin marketplace pack."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.html_native_view_session_authority_compose_routes import (
    ModeBody,
)
from interfaces.research.api.recursive_twin_marketplace_free_competition_dr_compose_routes import (
    MarketPackBody,
    TwinBody,
)
from substrate.html_native_recursive_twin_marketplace_free_compose import (
    HtmlNativeRecursiveTwinMarketplaceFreeComposeError,
    compose_html_native_recursive_twin_marketplace_free,
)

html_native_recursive_twin_marketplace_free_compose_router = APIRouter(
    prefix="/research/html-native-recursive-twin-marketplace-free",
    tags=["html-native-recursive-twin-marketplace-free-compose"],
)


class HtmlViewBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    asset_id: str = Field(min_length=1, max_length=256)
    html_projection_sha: str | None = Field(default=None, max_length=128)
    view_requested: bool = Field(strict=True)
    twin_bound: bool = Field(strict=True)
    twin_substrate_ready: bool | None = Field(default=None, strict=True)
    claimed_format: str | None = Field(default=None, max_length=64)
    reading: ModeBody | None = None
    research: ModeBody | None = None


class TwinPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    twin: TwinBody
    market_pack: MarketPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    html_view: HtmlViewBody
    twin_pack: TwinPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@html_native_recursive_twin_marketplace_free_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_html_native_recursive_twin_marketplace_free(
            html_view=req.html_view.model_dump(),
            twin_pack=req.twin_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except HtmlNativeRecursiveTwinMarketplaceFreeComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_html_native_recursive_twin_marketplace_free_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        html_native_recursive_twin_marketplace_free_compose_router
    )


__all__ = [
    "html_native_recursive_twin_marketplace_free_compose_router",
    "register_html_native_recursive_twin_marketplace_free_compose_routes",
]
