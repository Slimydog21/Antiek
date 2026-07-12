"""Registerable HTTP surface for floating multi-select + model decision free settings."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.model_decision_twin_search_html_native_marketplace_free_settings_compose_routes import (
    TwinSearchPackBody,
)
from interfaces.research.api.model_decision_twin_search_weekly_html_native_compose_routes import (
    DecisionBody,
)
from substrate.floating_multiselect_model_decision_twin_search_free_settings_compose import (
    FloatingMultiselectModelDecisionTwinSearchFreeSettingsComposeError,
    compose_floating_multiselect_model_decision_twin_search_free_settings,
)

floating_multiselect_model_decision_twin_search_free_settings_compose_router = (
    APIRouter(
        prefix=(
            "/research/floating-multiselect-model-decision-twin-search-free-settings"
        ),
        tags=[
            "floating-multiselect-model-decision-twin-search-free-settings-compose"
        ],
    )
)

TrayStatus = Literal["proposed", "open", "completed", "closed"]
PackMode = Literal["cohesive_prompt", "collective_pack", "cohesive_plus_analysis"]


class MemberBody(BaseModel):
    model_config = {"extra": "forbid"}

    instance_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    status: TrayStatus
    highlight: str | None = Field(default=None, max_length=4000)
    prior_prompt: str | None = Field(default=None, max_length=8000)
    context: list[str] | None = None
    findings: list[str] | None = None


class MultiSelectBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    members: list[MemberBody] = Field(min_length=2)
    selected_instance_ids: list[str] = Field(min_length=2)
    pack_mode: PackMode
    cohesive_prompt: str = Field(min_length=1, max_length=8000)
    extra_context: list[str] | None = None
    analysis_kind: Literal["draft_analysis", "full_analysis"] | None = None
    extra_findings: list[str] | None = None


class DecisionPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    decision: DecisionBody
    twin_search_pack: TwinSearchPackBody
    require_both: bool | None = Field(default=None, strict=True)
    block_on_budget_exceed: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    multiselect: MultiSelectBody
    decision_pack: DecisionPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@floating_multiselect_model_decision_twin_search_free_settings_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_floating_multiselect_model_decision_twin_search_free_settings(
            multiselect=req.multiselect.model_dump(),
            decision_pack=req.decision_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except FloatingMultiselectModelDecisionTwinSearchFreeSettingsComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_floating_multiselect_model_decision_twin_search_free_settings_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        floating_multiselect_model_decision_twin_search_free_settings_compose_router
    )


__all__ = [
    "floating_multiselect_model_decision_twin_search_free_settings_compose_router",
    "register_floating_multiselect_model_decision_twin_search_free_settings_compose_routes",
]
