"""Registerable HTTP surface for floating DR over workstation record model decision pack."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_routes import (
    DecisionPackBody,
    RecordItemBody,
)
from substrate.floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose import (
    FloatingDrWorkstationRecordModelDecisionTwinSearchHtmlNativeMarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinComposeError,
    compose_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin,
)

floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_router = APIRouter(
    prefix="/research/floating-dr-workstation-record-model-decision-twin-search-html-native-marketplace-free-midnight-oil-settings-decision-competition-dr-nd-shadow-recursive-twin",
    tags=["floating-dr-workstation-record-model-decision-twin-search-html-native-marketplace-free-midnight-oil-settings-decision-competition-dr-nd-shadow-recursive-twin-compose"],
)


class HighlightLaunchBody(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    highlight: str = Field(min_length=1, max_length=8000)
    gated: bool = Field(strict=True)
    prompt: str | None = Field(default=None, max_length=4000)
    preferred_view_mode: Literal["floating", "fullscreen"] | None = None
    would_exceed: bool | None = None
    operator_override: bool | None = Field(default=None, strict=True)
    selected_model_id: str | None = Field(default=None, max_length=128)
    source_families: list[
        Literal["arxiv", "substack", "openalex", "web", "custom"]
    ] | None = None


class RecordPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    items: list[RecordItemBody]
    decision_pack: DecisionPackBody
    max_context_lines: int | None = Field(default=None, ge=1, le=10000)
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    highlight_launch: HighlightLaunchBody
    record_pack: RecordPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin(
            highlight_launch=req.highlight_launch.model_dump(),
            record_pack=req.record_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except FloatingDrWorkstationRecordModelDecisionTwinSearchHtmlNativeMarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_routes(app: FastAPI) -> None:
    app.include_router(floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_router)


__all__ = [
    "floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_router",
    "register_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_routes",
]
