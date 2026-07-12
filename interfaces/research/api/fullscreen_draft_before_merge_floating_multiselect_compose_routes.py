"""Registerable HTTP surface for fullscreen + draft-before-merge multi-select pack."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.draft_before_merge_floating_multiselect_model_decision_compose_routes import (
    DraftGateBody,
    MultiPackBody,
)
from interfaces.research.api.floating_fullscreen_open_compose_routes import (
    InstanceBody,
    TraySiblingBody,
)
from substrate.fullscreen_draft_before_merge_floating_multiselect_compose import (
    FullscreenDraftBeforeMergeFloatingMultiselectComposeError,
    compose_fullscreen_draft_before_merge_floating_multiselect,
)

fullscreen_draft_before_merge_floating_multiselect_compose_router = APIRouter(
    prefix="/research/fullscreen-draft-before-merge-floating-multiselect",
    tags=["fullscreen-draft-before-merge-floating-multiselect-compose"],
)


class FullscreenBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    existing_instance: InstanceBody | None = None
    highlight: str | None = Field(default=None, max_length=8000)
    prompt: str | None = Field(default=None, max_length=8000)
    gated: bool | None = Field(default=None, strict=True)
    tray_siblings: list[TraySiblingBody] | None = None


class DraftPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    draft_gate: DraftGateBody
    multi_pack: MultiPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    fullscreen: FullscreenBody
    draft_pack: DraftPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@fullscreen_draft_before_merge_floating_multiselect_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_fullscreen_draft_before_merge_floating_multiselect(
            fullscreen=req.fullscreen.model_dump(),
            draft_pack=req.draft_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except FullscreenDraftBeforeMergeFloatingMultiselectComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_fullscreen_draft_before_merge_floating_multiselect_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        fullscreen_draft_before_merge_floating_multiselect_compose_router
    )


__all__ = [
    "fullscreen_draft_before_merge_floating_multiselect_compose_router",
    "register_fullscreen_draft_before_merge_floating_multiselect_compose_routes",
]
