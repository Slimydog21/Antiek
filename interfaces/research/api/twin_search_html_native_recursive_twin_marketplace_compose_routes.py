"""Registerable HTTP surface for twin search + HTML-native marketplace pack."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.html_native_recursive_twin_marketplace_free_compose_routes import (
    HtmlViewBody,
    TwinPackBody,
)
from interfaces.research.api.twin_search_antiek_bench_weekly_html_native_compose_routes import (
    TwinSearchRecordBody,
)
from substrate.twin_search_html_native_recursive_twin_marketplace_compose import (
    TwinSearchHtmlNativeRecursiveTwinMarketplaceComposeError,
    compose_twin_search_html_native_recursive_twin_marketplace,
)

twin_search_html_native_recursive_twin_marketplace_compose_router = APIRouter(
    prefix="/research/twin-search-html-native-recursive-twin-marketplace",
    tags=["twin-search-html-native-recursive-twin-marketplace-compose"],
)


class HtmlPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    html_view: HtmlViewBody
    twin_pack: TwinPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    search_query: str = Field(min_length=1, max_length=2048)
    twin_records: list[TwinSearchRecordBody]
    html_pack: HtmlPackBody
    operator_ack: bool = Field(strict=True)
    search_limit: int | None = Field(default=None, ge=1, le=500)
    require_both: bool = Field(default=True, strict=True)


@twin_search_html_native_recursive_twin_marketplace_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_twin_search_html_native_recursive_twin_marketplace(
            search_query=req.search_query,
            twin_records=[r.model_dump() for r in req.twin_records],
            html_pack=req.html_pack.model_dump(),
            operator_ack=req.operator_ack,
            search_limit=req.search_limit,
            require_both=req.require_both,
        )
    except TwinSearchHtmlNativeRecursiveTwinMarketplaceComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_twin_search_html_native_recursive_twin_marketplace_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        twin_search_html_native_recursive_twin_marketplace_compose_router
    )


__all__ = [
    "twin_search_html_native_recursive_twin_marketplace_compose_router",
    "register_twin_search_html_native_recursive_twin_marketplace_compose_routes",
]
