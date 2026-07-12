"""Registerable HTTP surface for write twin + highlight float twin-search pack."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.highlight_float_twin_search_competition_compose_routes import (
    HighlightBody,
    TwinSearchPackBody,
)
from substrate.write_twin_collective_highlight_float_twin_search_compose import (
    WriteTwinCollectiveHighlightFloatTwinSearchComposeError,
    compose_write_twin_collective_highlight_float_twin_search,
)

write_twin_collective_highlight_float_twin_search_compose_router = APIRouter(
    prefix="/research/write-twin-collective-highlight-float-twin-search",
    tags=["write-twin-collective-highlight-float-twin-search-compose"],
)


class TwinSliceBody(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    insights: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


class SlotBody(BaseModel):
    model_config = {"extra": "forbid"}

    slot_id: str = Field(min_length=1, max_length=256)
    question_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    status: Literal["proposed", "open", "completed", "closed"]
    findings: list[str] | None = None
    body: str | None = Field(default=None, max_length=8000)


class WriteBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    draft_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    twin_slices: list[TwinSliceBody] = Field(min_length=1)
    chase_slots: list[SlotBody] = Field(min_length=2)
    analysis_kind: Literal["draft_analysis", "full_analysis"]
    base_draft_html: str | None = Field(default=None, max_length=50000)
    extra_findings: list[str] | None = None
    require_both: bool | None = Field(default=None, strict=True)


class HighlightPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    highlight: HighlightBody
    twin_search_pack: TwinSearchPackBody
    seed_search_from_highlight: bool | None = Field(default=None, strict=True)
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    write: WriteBody
    highlight_pack: HighlightPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@write_twin_collective_highlight_float_twin_search_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_write_twin_collective_highlight_float_twin_search(
            write=req.write.model_dump(),
            highlight_pack=req.highlight_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except WriteTwinCollectiveHighlightFloatTwinSearchComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_write_twin_collective_highlight_float_twin_search_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        write_twin_collective_highlight_float_twin_search_compose_router
    )


__all__ = [
    "write_twin_collective_highlight_float_twin_search_compose_router",
    "register_write_twin_collective_highlight_float_twin_search_compose_routes",
]
