"""Registerable HTTP surface for collective presented twins + paid ND pack."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.floating_multi_select_collective_cohesive_compose_routes import (
    MemberBody,
)
from interfaces.research.api.paid_purchase_nd_shadow_twin_presentation_compose_routes import (
    NdTwinBody,
    PurchaseBody,
)
from substrate.collective_presented_twins_paid_nd_compose import (
    CollectivePresentedTwinsPaidNdComposeError,
    compose_collective_presented_twins_paid_nd,
)

collective_presented_twins_paid_nd_compose_router = APIRouter(
    prefix="/research/collective-presented-twins-paid-nd",
    tags=["collective-presented-twins-paid-nd-compose"],
)


class CollectiveBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    members: list[MemberBody] = Field(min_length=2)
    selected_instance_ids: list[str] = Field(min_length=2)
    pack_mode: Literal[
        "cohesive_prompt", "collective_pack", "cohesive_plus_analysis"
    ]
    cohesive_prompt: str = Field(min_length=1, max_length=8000)
    extra_context: list[str] | None = None
    analysis_kind: Literal["draft_analysis", "full_analysis"] | None = None
    extra_findings: list[str] | None = None


class PaidNdBody(BaseModel):
    model_config = {"extra": "forbid"}

    purchase: PurchaseBody
    nd_twin: NdTwinBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    collective: CollectiveBody
    paid_nd: PaidNdBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@collective_presented_twins_paid_nd_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_collective_presented_twins_paid_nd(
            collective=req.collective.model_dump(),
            paid_nd=req.paid_nd.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except CollectivePresentedTwinsPaidNdComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_collective_presented_twins_paid_nd_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(collective_presented_twins_paid_nd_compose_router)


__all__ = [
    "collective_presented_twins_paid_nd_compose_router",
    "register_collective_presented_twins_paid_nd_compose_routes",
]
