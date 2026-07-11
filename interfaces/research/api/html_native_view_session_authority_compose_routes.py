"""Registerable HTTP surface for HTML-native view session authority pack."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.html_native_view_session_authority_compose import (
    HtmlNativeViewSessionAuthorityComposeError,
    compose_html_native_view_session_authority,
)

html_native_view_session_authority_compose_router = APIRouter(
    prefix="/research/html-native-view-session-authority",
    tags=["html-native-view-session-authority-compose"],
)


class ModeBody(BaseModel):
    model_config = {"extra": "forbid"}

    asset_id: str = Field(min_length=1, max_length=256)
    asset_kind: Literal[
        "book", "research", "twin", "analysis", "paper", "other"
    ]
    source_format: Literal["html", "pdf", "epub", "markdown", "unknown"]
    html_projection_sha: str | None = Field(default=None, max_length=128)
    prefer_html: bool = Field(default=True, strict=True)
    allow_pdf_secondary: bool = Field(default=False, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    asset_id: str = Field(min_length=1, max_length=256)
    html_projection_sha: str | None = Field(default=None, max_length=128)
    view_requested: bool = Field(strict=True)
    twin_bound: bool = Field(strict=True)
    operator_ack: bool = Field(strict=True)
    twin_substrate_ready: bool | None = Field(default=None, strict=True)
    claimed_format: str | None = Field(default=None, max_length=64)
    reading: ModeBody | None = None
    research: ModeBody | None = None


@html_native_view_session_authority_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_html_native_view_session_authority(
            session_id=req.session_id,
            asset_id=req.asset_id,
            html_projection_sha=req.html_projection_sha,
            view_requested=req.view_requested,
            twin_bound=req.twin_bound,
            operator_ack=req.operator_ack,
            twin_substrate_ready=req.twin_substrate_ready,
            claimed_format=req.claimed_format,
            reading=req.reading.model_dump() if req.reading else None,
            research=req.research.model_dump() if req.research else None,
        )
    except HtmlNativeViewSessionAuthorityComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_html_native_view_session_authority_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(html_native_view_session_authority_compose_router)


__all__ = [
    "html_native_view_session_authority_compose_router",
    "register_html_native_view_session_authority_compose_routes",
]
