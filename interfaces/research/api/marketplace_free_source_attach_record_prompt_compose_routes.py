"""Registerable HTTP surface for marketplace free + source-attach pack."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.source_attach_record_prompt_html_native_mo_compose_routes import (
    RecordHtmlBody,
    SourcesBody,
)
from substrate.marketplace_free_source_attach_record_prompt_compose import (
    MarketplaceFreeSourceAttachRecordPromptComposeError,
    compose_marketplace_free_source_attach_record_prompt,
)

marketplace_free_source_attach_record_prompt_compose_router = APIRouter(
    prefix="/research/marketplace-free-source-attach-record-prompt",
    tags=["marketplace-free-source-attach-record-prompt-compose"],
)


class MarketBody(BaseModel):
    model_config = {"extra": "forbid"}

    title: str = Field(min_length=1, max_length=2000)
    account_id: str = Field(min_length=1, max_length=256)
    free_copy_available: bool | None = None
    free_html_projection_sha: str | None = Field(default=None, max_length=128)
    purchase_ack: bool = Field(strict=True)
    port_requested: bool = Field(strict=True)
    purchase_html_projection_sha: str | None = Field(
        default=None, max_length=128
    )


class ResearchBody(BaseModel):
    model_config = {"extra": "forbid"}

    sources: SourcesBody
    record_html: RecordHtmlBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    market: MarketBody
    research: ResearchBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@marketplace_free_source_attach_record_prompt_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_marketplace_free_source_attach_record_prompt(
            market=req.market.model_dump(),
            research=req.research.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except MarketplaceFreeSourceAttachRecordPromptComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_marketplace_free_source_attach_record_prompt_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        marketplace_free_source_attach_record_prompt_compose_router
    )


__all__ = [
    "marketplace_free_source_attach_record_prompt_compose_router",
    "register_marketplace_free_source_attach_record_prompt_compose_routes",
]
