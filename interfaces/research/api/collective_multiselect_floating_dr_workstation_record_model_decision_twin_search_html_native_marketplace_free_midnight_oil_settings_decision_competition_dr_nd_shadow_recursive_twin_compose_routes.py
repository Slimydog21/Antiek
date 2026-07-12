"""Registerable HTTP surface for collective multiselect over floating DR workstation record pack."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_routes import (
    HighlightLaunchBody,
    RecordPackBody,
)
from interfaces.research.api.floating_multi_select_collective_cohesive_compose_routes import (
    MemberBody,
)
from substrate.collective_multiselect_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose import (
    CollectiveMultiselectFloatingDrWorkstationRecordModelDecisionTwinSearchHtmlNativeMarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinComposeError,
    compose_collective_multiselect_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin,
)

collective_multiselect_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_router = APIRouter(
    prefix="/research/collective-multiselect-floating-dr-workstation-record-model-decision-twin-search-html-native-marketplace-free-midnight-oil-settings-decision-competition-dr-nd-shadow-recursive-twin",
    tags=["collective-multiselect-floating-dr-workstation-record-model-decision-twin-search-html-native-marketplace-free-midnight-oil-settings-decision-competition-dr-nd-shadow-recursive-twin-compose"],
)


class MultiselectBody(BaseModel):
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


class FloatingPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    highlight_launch: HighlightLaunchBody
    record_pack: RecordPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    multiselect: MultiselectBody
    floating_pack: FloatingPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@collective_multiselect_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_collective_multiselect_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin(
            multiselect=req.multiselect.model_dump(),
            floating_pack=req.floating_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except CollectiveMultiselectFloatingDrWorkstationRecordModelDecisionTwinSearchHtmlNativeMarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_collective_multiselect_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        collective_multiselect_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_router
    )


__all__ = [
    "collective_multiselect_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_router",
    "register_collective_multiselect_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_routes",
]
