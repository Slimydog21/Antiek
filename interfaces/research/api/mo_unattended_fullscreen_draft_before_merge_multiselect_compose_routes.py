"""Registerable HTTP surface for MO unattended + fullscreen draft multi-select pack."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.fullscreen_draft_before_merge_floating_multiselect_compose_routes import (
    DraftPackBody,
    FullscreenBody,
)
from interfaces.research.api.midnight_oil_unattended_package_compose_routes import (
    GoalBody,
)
from substrate.mo_unattended_fullscreen_draft_before_merge_multiselect_compose import (
    MoUnattendedFullscreenDraftBeforeMergeMultiselectComposeError,
    compose_mo_unattended_fullscreen_draft_before_merge_multiselect,
)

mo_unattended_fullscreen_draft_before_merge_multiselect_compose_router = APIRouter(
    prefix="/research/mo-unattended-fullscreen-draft-before-merge-multiselect",
    tags=["mo-unattended-fullscreen-draft-before-merge-multiselect-compose"],
)


class MoBody(BaseModel):
    model_config = {"extra": "forbid"}

    operator_id: str = Field(min_length=1, max_length=256)
    work_minutes: float = Field(gt=0)
    goals: list[GoalBody] = Field(min_length=1)
    usd_per_hour: float | None = Field(default=None, ge=0)
    approved_ceiling_usd: float | None = Field(default=None, ge=0)
    unattended_ack: bool = Field(strict=True)
    spend_consent: bool = Field(strict=True)
    brief_dispatch_ready: bool | None = None


class FullscreenPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    fullscreen: FullscreenBody
    draft_pack: DraftPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    mo: MoBody
    fullscreen_pack: FullscreenPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@mo_unattended_fullscreen_draft_before_merge_multiselect_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_mo_unattended_fullscreen_draft_before_merge_multiselect(
            mo=req.mo.model_dump(),
            fullscreen_pack=req.fullscreen_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except MoUnattendedFullscreenDraftBeforeMergeMultiselectComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_mo_unattended_fullscreen_draft_before_merge_multiselect_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        mo_unattended_fullscreen_draft_before_merge_multiselect_compose_router
    )


__all__ = [
    "mo_unattended_fullscreen_draft_before_merge_multiselect_compose_router",
    "register_mo_unattended_fullscreen_draft_before_merge_multiselect_compose_routes",
]
