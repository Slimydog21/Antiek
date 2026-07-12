"""Registerable HTTP surface for marketplace HTML twin write compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.marketplace_html_twin_write_compose import (
    MarketplaceHtmlTwinWriteComposeError,
    compose_marketplace_html_twin_write,
)

marketplace_html_twin_write_compose_router = APIRouter(
    prefix="/research/marketplace-html-twin-write",
    tags=["marketplace-html-twin-write-compose"],
)


class FindingBody(BaseModel):
    model_config = {"extra": "forbid"}

    source_id: str = Field(min_length=1, max_length=256)
    body: str = Field(min_length=1, max_length=8000)
    kind: Literal["insight", "question", "claim", "data"] | None = None


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


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    asset_id: str = Field(min_length=1, max_length=256)
    draft_id: str = Field(min_length=1, max_length=256)
    title: str = Field(min_length=1, max_length=2000)
    account_id: str = Field(min_length=1, max_length=256)
    free_copy_available: bool | None = None
    free_html_projection_sha: str | None = Field(default=None, max_length=128)
    purchase_html_projection_sha: str | None = Field(
        default=None, max_length=128
    )
    port_requested: bool = Field(strict=True)
    purchase_ack: bool = Field(strict=True)
    list_price_usd: float | None = Field(default=None, ge=0)
    approved_spend_usd: float | None = Field(default=None, ge=0)
    remaining_budget_usd: float | None = Field(default=None, ge=0)
    operator_ack: bool = Field(strict=True)
    view_requested: bool = Field(strict=True)
    twin_findings: list[FindingBody] | None = None
    existing_twin_asset_id: str | None = Field(default=None, max_length=256)
    mark_for_prompt_context: bool = Field(default=False, strict=True)
    include_twin_feed: bool = Field(default=True, strict=True)
    analysis_kind: Literal["draft_analysis", "full_analysis"] | None = None
    twin_slices: list[TwinSliceBody] | None = None
    chase_slots: list[SlotBody] | None = None
    base_draft_html: str | None = Field(default=None, max_length=100000)
    require_both_with_write: bool = Field(default=True, strict=True)


@marketplace_html_twin_write_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_marketplace_html_twin_write(
            session_id=req.session_id,
            asset_id=req.asset_id,
            draft_id=req.draft_id,
            title=req.title,
            account_id=req.account_id,
            free_copy_available=req.free_copy_available,
            free_html_projection_sha=req.free_html_projection_sha,
            purchase_html_projection_sha=req.purchase_html_projection_sha,
            port_requested=req.port_requested,
            purchase_ack=req.purchase_ack,
            list_price_usd=req.list_price_usd,
            approved_spend_usd=req.approved_spend_usd,
            remaining_budget_usd=req.remaining_budget_usd,
            operator_ack=req.operator_ack,
            view_requested=req.view_requested,
            twin_findings=(
                [f.model_dump() for f in req.twin_findings]
                if req.twin_findings is not None
                else None
            ),
            existing_twin_asset_id=req.existing_twin_asset_id,
            mark_for_prompt_context=req.mark_for_prompt_context,
            include_twin_feed=req.include_twin_feed,
            analysis_kind=req.analysis_kind,
            twin_slices=(
                [s.model_dump() for s in req.twin_slices]
                if req.twin_slices is not None
                else None
            ),
            chase_slots=(
                [s.model_dump() for s in req.chase_slots]
                if req.chase_slots is not None
                else None
            ),
            base_draft_html=req.base_draft_html,
            require_both_with_write=req.require_both_with_write,
        )
    except MarketplaceHtmlTwinWriteComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_marketplace_html_twin_write_compose_routes(app: FastAPI) -> None:
    app.include_router(marketplace_html_twin_write_compose_router)


__all__ = [
    "marketplace_html_twin_write_compose_router",
    "register_marketplace_html_twin_write_compose_routes",
]
