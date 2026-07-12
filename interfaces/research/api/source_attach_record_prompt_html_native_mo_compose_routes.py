"""Registerable HTTP surface for source attach + record→prompt HTML pack."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.record_prompt_html_native_recursive_twin_mo_compose_routes import (
    HtmlPackBody,
    RecordPromptBody,
)
from interfaces.research.api.source_publication_dr_attach_quality_compose_routes import (
    CitationBody,
    SourceBody,
)
from substrate.source_attach_record_prompt_html_native_mo_compose import (
    SourceAttachRecordPromptHtmlNativeMoComposeError,
    compose_source_attach_record_prompt_html_native_mo,
)

source_attach_record_prompt_html_native_mo_compose_router = APIRouter(
    prefix="/research/source-attach-record-prompt-html-native-mo",
    tags=["source-attach-record-prompt-html-native-mo-compose"],
)

Family = Literal["arxiv", "substack", "openalex", "web", "custom"]


class SourcesBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    requested_families: list[Family] = Field(min_length=1)
    sources: list[SourceBody] = Field(min_length=1)
    quality_overall: float | None = Field(default=None, ge=0, le=1)
    would_exceed: bool | None = Field(default=None, strict=True)
    citations: list[CitationBody] | None = None
    derive_citations_from_sources: bool | None = Field(
        default=None, strict=True
    )
    quality_floor: float | None = Field(default=None, ge=0, le=1)
    operator_override: bool | None = Field(default=None, strict=True)


class RecordHtmlBody(BaseModel):
    model_config = {"extra": "forbid"}

    record_prompt: RecordPromptBody
    html_pack: HtmlPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    sources: SourcesBody
    record_html: RecordHtmlBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@source_attach_record_prompt_html_native_mo_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_source_attach_record_prompt_html_native_mo(
            sources=req.sources.model_dump(),
            record_html=req.record_html.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except SourceAttachRecordPromptHtmlNativeMoComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_source_attach_record_prompt_html_native_mo_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        source_attach_record_prompt_html_native_mo_compose_router
    )


__all__ = [
    "source_attach_record_prompt_html_native_mo_compose_router",
    "register_source_attach_record_prompt_html_native_mo_compose_routes",
]
