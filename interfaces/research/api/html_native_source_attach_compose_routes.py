"""Registerable HTTP surface for HTML-native source attach compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.html_native_source_attach_compose import (
    HtmlNativeSourceAttachComposeError,
    compose_html_native_source_attach,
)

html_native_source_attach_compose_router = APIRouter(
    prefix="/research/html-source-attach",
    tags=["html-native-source-attach-compose"],
)


class SourceBody(BaseModel):
    model_config = {"extra": "forbid"}

    source_id: str = Field(min_length=1, max_length=256)
    family: Literal["arxiv", "substack", "openalex", "web", "custom"]
    title: str = Field(min_length=1, max_length=2000)
    external_id: str | None = Field(default=None, max_length=512)
    url: str | None = Field(default=None, max_length=4000)
    html_fragment: str | None = Field(default=None, max_length=500_000)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    requested_families: list[
        Literal["arxiv", "substack", "openalex", "web", "custom"]
    ] = Field(min_length=1)
    sources: list[SourceBody]
    operator_ack: bool = Field(strict=True)


@html_native_source_attach_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_html_native_source_attach(
            session_id=req.session_id,
            parent_asset_id=req.parent_asset_id,
            requested_families=list(req.requested_families),
            sources=[s.model_dump() for s in req.sources],
            operator_ack=req.operator_ack,
        )
    except HtmlNativeSourceAttachComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_html_native_source_attach_compose_routes(app: FastAPI) -> None:
    app.include_router(html_native_source_attach_compose_router)


__all__ = [
    "html_native_source_attach_compose_router",
    "register_html_native_source_attach_compose_routes",
]
