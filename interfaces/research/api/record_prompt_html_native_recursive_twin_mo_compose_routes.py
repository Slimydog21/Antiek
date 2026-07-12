"""Registerable HTTP surface for record→prompt + HTML-native recursive twin MO."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.html_native_recursive_twin_mo_write_pack_compose_routes import (
    HtmlViewBody,
    TwinMoBody,
)
from interfaces.research.api.workstation_record_prompt_model_decision_compose_routes import (
    ModelBody,
    RecordBody,
)
from substrate.record_prompt_html_native_recursive_twin_mo_compose import (
    RecordPromptHtmlNativeRecursiveTwinMoComposeError,
    compose_record_prompt_html_native_recursive_twin_mo,
)

record_prompt_html_native_recursive_twin_mo_compose_router = APIRouter(
    prefix="/research/record-prompt-html-native-recursive-twin-mo",
    tags=["record-prompt-html-native-recursive-twin-mo-compose"],
)


class RecordPromptBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    records: list[RecordBody] = Field(min_length=1)
    user_prompt: str = Field(min_length=1, max_length=8000)
    selected_model_id: str = Field(min_length=1, max_length=128)
    models: list[ModelBody] = Field(min_length=1)
    daily_cap_usd: float | None = Field(default=None, ge=0)
    spent_usd: float | None = Field(default=None, ge=0)
    placement: str | None = Field(default=None, max_length=32)
    max_context_lines: int | None = Field(default=None, ge=1, le=500)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)


class HtmlPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    html_view: HtmlViewBody
    twin_mo: TwinMoBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    record_prompt: RecordPromptBody
    html_pack: HtmlPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@record_prompt_html_native_recursive_twin_mo_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_record_prompt_html_native_recursive_twin_mo(
            record_prompt=req.record_prompt.model_dump(),
            html_pack=req.html_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except RecordPromptHtmlNativeRecursiveTwinMoComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_record_prompt_html_native_recursive_twin_mo_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        record_prompt_html_native_recursive_twin_mo_compose_router
    )


__all__ = [
    "record_prompt_html_native_recursive_twin_mo_compose_router",
    "register_record_prompt_html_native_recursive_twin_mo_compose_routes",
]
