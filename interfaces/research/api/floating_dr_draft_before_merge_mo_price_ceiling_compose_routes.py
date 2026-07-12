"""Registerable HTTP surface for floating DR over draft-before-merge MO price-ceiling pack."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.draft_before_merge_mo_price_ceiling_recursive_twin_compose_routes import (
    DraftGateBody,
    MoPackBody,
)
from interfaces.research.api.reading_highlight_float_twin_feed_compose_routes import (
    FindingBody,
    MemberBody,
)
from substrate.floating_dr_draft_before_merge_mo_price_ceiling_compose import (
    FloatingDrDraftBeforeMergeMoPriceCeilingComposeError,
    compose_floating_dr_draft_before_merge_mo_price_ceiling,
)

floating_dr_draft_before_merge_mo_price_ceiling_compose_router = APIRouter(
    prefix="/research/floating-dr-draft-before-merge-mo-price-ceiling",
    tags=["floating-dr-draft-before-merge-mo-price-ceiling-compose"],
)


class HighlightSurfaceBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    highlight: str = Field(min_length=1, max_length=8000)
    gated: bool = Field(strict=True)
    would_exceed: bool | None = None
    surface_action: Literal[
        "spawn_only",
        "spawn_and_fullscreen",
        "spawn_and_draft_merge",
        "spawn_and_full_merge",
        "tray_collective",
        "tray_cohesive",
    ]
    prompt: str | None = Field(default=None, max_length=4000)
    preferred_view_mode: Literal["floating", "fullscreen"] | None = None
    operator_override: bool = Field(default=False, strict=True)
    selected_model_id: str | None = Field(default=None, max_length=128)
    source_families: list[
        Literal["arxiv", "substack", "openalex", "web", "custom"]
    ] | None = None
    existing_members: list[MemberBody] | None = None
    selected_instance_ids: list[str] | None = None
    twin_findings: list[FindingBody] | None = None
    existing_twin_asset_id: str | None = Field(default=None, max_length=256)
    mark_for_prompt_context: bool = Field(default=False, strict=True)
    include_twin_feed: bool = Field(default=True, strict=True)


class DraftPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    draft_gate: DraftGateBody
    mo_pack: MoPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    highlight_surface: HighlightSurfaceBody
    draft_pack: DraftPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@floating_dr_draft_before_merge_mo_price_ceiling_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_floating_dr_draft_before_merge_mo_price_ceiling(
            highlight_surface=req.highlight_surface.model_dump(),
            draft_pack=req.draft_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except FloatingDrDraftBeforeMergeMoPriceCeilingComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_floating_dr_draft_before_merge_mo_price_ceiling_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        floating_dr_draft_before_merge_mo_price_ceiling_compose_router
    )


__all__ = [
    "floating_dr_draft_before_merge_mo_price_ceiling_compose_router",
    "register_floating_dr_draft_before_merge_mo_price_ceiling_compose_routes",
]
