"""Registerable HTTP surface for source attach + settings decision MO pack."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.html_native_source_attach_compose_routes import (
    SourceBody,
)
from interfaces.research.api.settings_decision_mo_unattended_fullscreen_compose_routes import (
    DecisionBody,
    MoPackBody,
)
from substrate.source_attach_settings_decision_mo_compose import (
    SourceAttachSettingsDecisionMoComposeError,
    compose_source_attach_settings_decision_mo,
)

source_attach_settings_decision_mo_compose_router = APIRouter(
    prefix="/research/source-attach-settings-decision-mo",
    tags=["source-attach-settings-decision-mo-compose"],
)

Family = Literal["arxiv", "substack", "openalex", "web", "custom"]


class SourcesBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    requested_families: list[Family] = Field(min_length=1)
    sources: list[SourceBody]


class SettingsMoBody(BaseModel):
    model_config = {"extra": "forbid"}

    decision: DecisionBody
    mo_pack: MoPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    sources: SourcesBody
    settings_mo: SettingsMoBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@source_attach_settings_decision_mo_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_source_attach_settings_decision_mo(
            sources=req.sources.model_dump(),
            settings_mo=req.settings_mo.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except SourceAttachSettingsDecisionMoComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_source_attach_settings_decision_mo_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(source_attach_settings_decision_mo_compose_router)


__all__ = [
    "source_attach_settings_decision_mo_compose_router",
    "register_source_attach_settings_decision_mo_compose_routes",
]
