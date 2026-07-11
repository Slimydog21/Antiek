"""Registerable HTTP surface for marketplace free-before-buy HTML port compose."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.marketplace_free_before_buy_html_port_compose import (
    MarketplaceFreeBeforeBuyHtmlPortComposeError,
    compose_marketplace_free_before_buy_html_port,
)

marketplace_free_before_buy_html_port_compose_router = APIRouter(
    prefix="/research/marketplace-free-before-buy-port",
    tags=["marketplace-free-before-buy-html-port-compose"],
)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    title: str = Field(min_length=1, max_length=2000)
    account_id: str = Field(min_length=1, max_length=256)
    free_copy_available: bool | None = None
    free_html_projection_sha: str | None = Field(default=None, max_length=256)
    purchase_ack: bool = Field(strict=True)
    port_requested: bool = Field(strict=True)
    purchase_html_projection_sha: str | None = Field(default=None, max_length=256)


@marketplace_free_before_buy_html_port_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_marketplace_free_before_buy_html_port(
            title=req.title,
            account_id=req.account_id,
            free_copy_available=req.free_copy_available,
            free_html_projection_sha=req.free_html_projection_sha,
            purchase_ack=req.purchase_ack,
            port_requested=req.port_requested,
            purchase_html_projection_sha=req.purchase_html_projection_sha,
        )
    except MarketplaceFreeBeforeBuyHtmlPortComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_marketplace_free_before_buy_html_port_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(marketplace_free_before_buy_html_port_compose_router)


__all__ = [
    "marketplace_free_before_buy_html_port_compose_router",
    "register_marketplace_free_before_buy_html_port_compose_routes",
]
