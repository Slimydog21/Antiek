"""Registerable HTTP surface for MO price-ceiling + draft multi-select pack."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.draft_before_merge_multi_select_record_write_compose_routes import (
    DraftGateBody,
    MultiPackBody,
)
from substrate.mo_price_ceiling_draft_multi_select_record_write_compose import (
    MoPriceCeilingDraftMultiSelectRecordWriteComposeError,
    compose_mo_price_ceiling_draft_multi_select_record_write,
)

mo_price_ceiling_draft_multi_select_record_write_compose_router = APIRouter(
    prefix="/research/mo-price-ceiling-draft-multi-select-record-write",
    tags=["mo-price-ceiling-draft-multi-select-record-write-compose"],
)


class GoalBody(BaseModel):
    model_config = {"extra": "forbid"}

    goal_id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=2000)


class MoBody(BaseModel):
    model_config = {"extra": "forbid"}

    operator_id: str = Field(min_length=1, max_length=256)
    work_minutes: int = Field(ge=1, le=10080)
    goals: list[GoalBody] = Field(min_length=1)
    price_ceiling_ack: bool = Field(strict=True)
    stage: Literal["recommend_only", "approve_ceiling", "unattended_pack"]
    usd_per_hour: float | None = Field(default=None, ge=0)
    goal_intensity: float | None = Field(default=None, ge=0, le=10)
    approved_ceiling_usd: float | None = Field(default=None, ge=0)
    below_recommend_override: bool | None = Field(default=None, strict=True)
    unattended_ack: bool | None = Field(default=None, strict=True)
    spend_consent: bool | None = Field(default=None, strict=True)


class DraftMultiBody(BaseModel):
    model_config = {"extra": "forbid"}

    draft_gate: DraftGateBody
    multi_pack: MultiPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    mo: MoBody
    draft_multi: DraftMultiBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@mo_price_ceiling_draft_multi_select_record_write_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_mo_price_ceiling_draft_multi_select_record_write(
            mo=req.mo.model_dump(),
            draft_multi=req.draft_multi.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except MoPriceCeilingDraftMultiSelectRecordWriteComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_mo_price_ceiling_draft_multi_select_record_write_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        mo_price_ceiling_draft_multi_select_record_write_compose_router
    )


__all__ = [
    "mo_price_ceiling_draft_multi_select_record_write_compose_router",
    "register_mo_price_ceiling_draft_multi_select_record_write_compose_routes",
]
