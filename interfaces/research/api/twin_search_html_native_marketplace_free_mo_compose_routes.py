"""Registerable HTTP surface for twin search over HTML-native marketplace free MO pack."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.html_native_marketplace_free_midnight_oil_settings_compose_routes import (
    HtmlViewBody,
    MarketPackBody,
)
from substrate.twin_search_html_native_marketplace_free_mo_compose import (
    TwinSearchHtmlNativeMarketplaceFreeMoComposeError,
    compose_twin_search_html_native_marketplace_free_mo,
)

twin_search_html_native_marketplace_free_mo_compose_router = APIRouter(
    prefix="/research/twin-search-html-native-marketplace-free-mo",
    tags=["twin-search-html-native-marketplace-free-mo-compose"],
)


class TwinRecordBody(BaseModel):
    model_config = {"extra": "forbid"}

    twin_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    insights: list[str]
    questions: list[str]
    source_label: str | None = Field(default=None, max_length=256)


class HtmlPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    html_view: HtmlViewBody
    market_pack: MarketPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    search_query: str = Field(min_length=1, max_length=2000)
    twin_records: list[TwinRecordBody]
    html_pack: HtmlPackBody
    operator_ack: bool = Field(strict=True)
    search_limit: int | None = Field(default=None, ge=1, le=1000)
    require_both: bool = Field(default=True, strict=True)


@twin_search_html_native_marketplace_free_mo_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_twin_search_html_native_marketplace_free_mo(
            search_query=req.search_query,
            twin_records=[r.model_dump() for r in req.twin_records],
            html_pack=req.html_pack.model_dump(),
            operator_ack=req.operator_ack,
            search_limit=req.search_limit,
            require_both=req.require_both,
        )
    except TwinSearchHtmlNativeMarketplaceFreeMoComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_twin_search_html_native_marketplace_free_mo_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        twin_search_html_native_marketplace_free_mo_compose_router
    )


__all__ = [
    "twin_search_html_native_marketplace_free_mo_compose_router",
    "register_twin_search_html_native_marketplace_free_mo_compose_routes",
]
