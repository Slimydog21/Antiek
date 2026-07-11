"""Registerable HTTP surface for marketplace book host compose."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.marketplace_book_host_compose import (
    MarketplaceBookHostComposeError,
    compose_marketplace_book_host,
)

marketplace_book_host_compose_router = APIRouter(
    prefix="/books/marketplace-compose",
    tags=["marketplace-book-host-compose"],
)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    title: str = Field(min_length=1, max_length=512)
    free_copy_available: bool | None = None
    skip_free_copy: bool = Field(default=False, strict=True)
    operator_skip_acknowledged: bool = Field(default=False, strict=True)
    purchase_intent_allowed: bool | None = None
    html_projection_sha: str | None = Field(default=None, max_length=256)
    host_requested: bool = Field(default=True, strict=True)


@marketplace_book_host_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        decision = compose_marketplace_book_host(
            title=req.title,
            free_copy_available=req.free_copy_available,
            skip_free_copy=req.skip_free_copy,
            operator_skip_acknowledged=req.operator_skip_acknowledged,
            purchase_intent_allowed=req.purchase_intent_allowed,
            html_projection_sha=req.html_projection_sha,
            host_requested=req.host_requested,
        )
    except MarketplaceBookHostComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return decision.to_dict()


def register_marketplace_book_host_compose_routes(app: FastAPI) -> None:
    app.include_router(marketplace_book_host_compose_router)


__all__ = [
    "marketplace_book_host_compose_router",
    "register_marketplace_book_host_compose_routes",
]
