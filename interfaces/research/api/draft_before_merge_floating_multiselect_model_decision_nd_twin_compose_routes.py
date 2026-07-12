"""Registerable HTTP surface for draft-before-merge + floating multi-select model decision."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.floating_multiselect_model_decision_nd_twin_compose_routes import (
    DecisionPackBody,
    MultiSelectBody,
)
from substrate.draft_before_merge_floating_multiselect_model_decision_nd_twin_compose import (
    DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinComposeError,
    compose_draft_before_merge_floating_multiselect_model_decision_nd_twin,
)

draft_before_merge_floating_multiselect_model_decision_nd_twin_compose_router = APIRouter(
    prefix="/research/draft-before-merge-floating-multiselect-model-decision-nd-twin",
    tags=["draft-before-merge-floating-multiselect-model-decision-nd-twin-compose"],
)

TrayStatus = Literal["proposed", "open", "completed", "closed"]


class SourceBody(BaseModel):
    model_config = {"extra": "forbid"}

    instance_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    status: TrayStatus
    highlight: str | None = Field(default=None, max_length=4000)
    findings: list[str] | None = None


class DraftGateBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    sources: list[SourceBody] = Field(min_length=1)
    stage: Literal["draft_only", "promote_full_merge"]
    parent_excerpt: str | None = Field(default=None, max_length=50000)
    full_merge_ack: bool | None = Field(default=None, strict=True)


class MultiPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    multiselect: MultiSelectBody
    decision_pack: DecisionPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    draft_gate: DraftGateBody
    multi_pack: MultiPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@draft_before_merge_floating_multiselect_model_decision_nd_twin_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_draft_before_merge_floating_multiselect_model_decision_nd_twin(
            draft_gate=req.draft_gate.model_dump(),
            multi_pack=req.multi_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_draft_before_merge_floating_multiselect_model_decision_nd_twin_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        draft_before_merge_floating_multiselect_model_decision_nd_twin_compose_router
    )


__all__ = [
    "draft_before_merge_floating_multiselect_model_decision_nd_twin_compose_router",
    "register_draft_before_merge_floating_multiselect_model_decision_nd_twin_compose_routes",
]
