"""Registerable HTTP surface for highlight deep research launch compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.highlight_deep_research_launch_compose import (
    HighlightDeepResearchLaunchComposeError,
    compose_highlight_deep_research_launch,
)

highlight_deep_research_launch_compose_router = APIRouter(
    prefix="/research/highlight-dr-launch",
    tags=["highlight-deep-research-launch-compose"],
)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    highlight: str = Field(min_length=1, max_length=8000)
    gated: bool = Field(strict=True)
    prompt: str | None = Field(default=None, max_length=4000)
    preferred_view_mode: Literal["floating", "fullscreen"] | None = None
    would_exceed: bool | None = None
    operator_override: bool = Field(default=False, strict=True)
    selected_model_id: str | None = Field(default=None, max_length=128)
    source_families: list[
        Literal["arxiv", "substack", "openalex", "web", "custom"]
    ] | None = None
    operator_ack: bool = Field(strict=True)


@highlight_deep_research_launch_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_highlight_deep_research_launch(
            parent_asset_id=req.parent_asset_id,
            highlight=req.highlight,
            gated=req.gated,
            prompt=req.prompt,
            preferred_view_mode=req.preferred_view_mode,
            would_exceed=req.would_exceed,
            operator_override=req.operator_override,
            selected_model_id=req.selected_model_id,
            source_families=req.source_families,
            operator_ack=req.operator_ack,
        )
    except HighlightDeepResearchLaunchComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_highlight_deep_research_launch_compose_routes(app: FastAPI) -> None:
    app.include_router(highlight_deep_research_launch_compose_router)


__all__ = [
    "highlight_deep_research_launch_compose_router",
    "register_highlight_deep_research_launch_compose_routes",
]
