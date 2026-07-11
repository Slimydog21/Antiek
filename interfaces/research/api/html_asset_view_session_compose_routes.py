"""Registerable HTTP surface for HTML asset view session compose."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.html_asset_view_session_compose import (
    HtmlAssetViewSessionComposeError,
    compose_html_asset_view_session,
)

html_asset_view_session_compose_router = APIRouter(
    prefix="/research/html-asset-view",
    tags=["html-asset-view-session-compose"],
)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    asset_id: str = Field(min_length=1, max_length=256)
    html_projection_sha: str | None = Field(default=None, max_length=256)
    view_requested: bool = Field(strict=True)
    twin_bound: bool = Field(strict=True)
    twin_substrate_ready: bool = Field(default=False, strict=True)
    claimed_format: str | None = Field(default=None, max_length=128)


@html_asset_view_session_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_html_asset_view_session(
            session_id=req.session_id,
            asset_id=req.asset_id,
            html_projection_sha=req.html_projection_sha,
            view_requested=req.view_requested,
            twin_bound=req.twin_bound,
            twin_substrate_ready=req.twin_substrate_ready,
            claimed_format=req.claimed_format,
        )
    except HtmlAssetViewSessionComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_html_asset_view_session_compose_routes(app: FastAPI) -> None:
    app.include_router(html_asset_view_session_compose_router)


__all__ = [
    "html_asset_view_session_compose_router",
    "register_html_asset_view_session_compose_routes",
]
