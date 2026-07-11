"""Registerable HTTP surface for HTML-native view authority."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.html_native_view_authority import (
    HtmlNativeViewAuthorityError,
    evaluate_html_native_view_authority,
)

html_native_view_authority_router = APIRouter(
    prefix="/assets/html-native-view",
    tags=["html-native-view-authority"],
)


class EvaluateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    asset_id: str = Field(min_length=1, max_length=256)
    asset_kind: Literal["book", "research", "twin", "analysis", "paper", "other"]
    source_format: Literal["html", "pdf", "epub", "markdown", "unknown"]
    html_projection_sha: str | None = Field(default=None, max_length=256)
    prefer_html: bool = Field(default=True, strict=True)
    allow_pdf_secondary: bool = Field(default=True, strict=True)


@html_native_view_authority_router.post("/evaluate")
def post_evaluate(req: EvaluateRequest) -> dict[str, Any]:
    try:
        decision = evaluate_html_native_view_authority(
            asset_id=req.asset_id,
            asset_kind=req.asset_kind,
            source_format=req.source_format,
            html_projection_sha=req.html_projection_sha,
            prefer_html=req.prefer_html,
            allow_pdf_secondary=req.allow_pdf_secondary,
        )
    except HtmlNativeViewAuthorityError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return decision.to_dict()


def register_html_native_view_authority_routes(app: FastAPI) -> None:
    app.include_router(html_native_view_authority_router)


__all__ = [
    "html_native_view_authority_router",
    "register_html_native_view_authority_routes",
]
