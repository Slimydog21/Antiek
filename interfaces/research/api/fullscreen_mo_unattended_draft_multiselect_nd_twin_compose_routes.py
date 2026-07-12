"""Registerable HTTP surface for fullscreen + MO unattended draft multiselect ND twin."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.mo_unattended_draft_before_merge_floating_multiselect_nd_twin_compose_routes import (
    DraftPackBody,
    MoBody,
)
from substrate.fullscreen_mo_unattended_draft_multiselect_nd_twin_compose import (
    FullscreenMoUnattendedDraftMultiselectNdTwinComposeError,
    compose_fullscreen_mo_unattended_draft_multiselect_nd_twin,
)

fullscreen_mo_unattended_draft_multiselect_nd_twin_compose_router = APIRouter(
    prefix="/research/fullscreen-mo-unattended-draft-multiselect-nd-twin",
    tags=["fullscreen-mo-unattended-draft-multiselect-nd-twin-compose"],
)


class FullscreenBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    highlight: str | None = Field(default=None, max_length=4000)
    prompt: str | None = Field(default=None, max_length=8000)
    gated: bool | None = Field(default=None, strict=True)


class MoPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    mo: MoBody
    draft_pack: DraftPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    fullscreen: FullscreenBody
    mo_pack: MoPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@fullscreen_mo_unattended_draft_multiselect_nd_twin_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_fullscreen_mo_unattended_draft_multiselect_nd_twin(
            fullscreen=req.fullscreen.model_dump(),
            mo_pack=req.mo_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except FullscreenMoUnattendedDraftMultiselectNdTwinComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_fullscreen_mo_unattended_draft_multiselect_nd_twin_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        fullscreen_mo_unattended_draft_multiselect_nd_twin_compose_router
    )


__all__ = [
    "fullscreen_mo_unattended_draft_multiselect_nd_twin_compose_router",
    "register_fullscreen_mo_unattended_draft_multiselect_nd_twin_compose_routes",
]
