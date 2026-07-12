"""Registerable HTTP surface for MO unattended + draft multiselect ND twin pack."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.draft_before_merge_floating_multiselect_model_decision_nd_twin_compose_routes import (
    DraftGateBody,
    MultiPackBody,
)
from interfaces.research.api.midnight_oil_unattended_package_compose_routes import (
    GoalBody,
)
from substrate.mo_unattended_draft_before_merge_floating_multiselect_nd_twin_compose import (
    MoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinComposeError,
    compose_mo_unattended_draft_before_merge_floating_multiselect_nd_twin,
)

mo_unattended_draft_before_merge_floating_multiselect_nd_twin_compose_router = APIRouter(
    prefix="/research/mo-unattended-draft-before-merge-floating-multiselect-nd-twin",
    tags=["mo-unattended-draft-before-merge-floating-multiselect-nd-twin-compose"],
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


class DraftPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    draft_gate: DraftGateBody
    multi_pack: MultiPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    mo: MoBody
    draft_pack: DraftPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@mo_unattended_draft_before_merge_floating_multiselect_nd_twin_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_mo_unattended_draft_before_merge_floating_multiselect_nd_twin(
            mo=req.mo.model_dump(),
            draft_pack=req.draft_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except MoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_mo_unattended_draft_before_merge_floating_multiselect_nd_twin_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        mo_unattended_draft_before_merge_floating_multiselect_nd_twin_compose_router
    )


__all__ = [
    "mo_unattended_draft_before_merge_floating_multiselect_nd_twin_compose_router",
    "register_mo_unattended_draft_before_merge_floating_multiselect_nd_twin_compose_routes",
]
