"""Registerable HTTP surface for fullscreen + draft-before-merge collective multiselect pack."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.draft_before_merge_collective_multiselect_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_routes import (
    CollectivePackBody,
    DraftGateBody,
)
from interfaces.research.api.floating_fullscreen_open_compose_routes import (
    InstanceBody,
    TraySiblingBody,
)
from substrate.fullscreen_open_draft_before_merge_collective_multiselect_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose import (
    FullscreenOpenDraftBeforeMergeCollectiveMultiselectFloatingDrWorkstationRecordModelDecisionTwinSearchHtmlNativeMarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinComposeError,
    compose_fullscreen_open_draft_before_merge_collective_multiselect_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin,
)

fullscreen_open_draft_before_merge_collective_multiselect_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_router = APIRouter(
    prefix="/research/fullscreen-open-draft-before-merge-collective-multiselect-floating-dr-workstation-record-model-decision-twin-search-html-native-marketplace-free-midnight-oil-settings-decision-competition-dr-nd-shadow-recursive-twin",
    tags=["fullscreen-open-draft-before-merge-collective-multiselect-floating-dr-workstation-record-model-decision-twin-search-html-native-marketplace-free-midnight-oil-settings-decision-competition-dr-nd-shadow-recursive-twin-compose"],
)


class FullscreenBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    existing_instance: InstanceBody | None = None
    highlight: str | None = Field(default=None, max_length=8000)
    prompt: str | None = Field(default=None, max_length=8000)
    gated: bool | None = Field(default=None, strict=True)
    tray_siblings: list[TraySiblingBody] | None = None


class DraftPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    draft_gate: DraftGateBody
    collective_pack: CollectivePackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    fullscreen: FullscreenBody
    draft_pack: DraftPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@fullscreen_open_draft_before_merge_collective_multiselect_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_fullscreen_open_draft_before_merge_collective_multiselect_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin(
            fullscreen=req.fullscreen.model_dump(),
            draft_pack=req.draft_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except FullscreenOpenDraftBeforeMergeCollectiveMultiselectFloatingDrWorkstationRecordModelDecisionTwinSearchHtmlNativeMarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_fullscreen_open_draft_before_merge_collective_multiselect_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        fullscreen_open_draft_before_merge_collective_multiselect_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_router
    )


__all__ = [
    "DraftPackBody",
    "FullscreenBody",
    "fullscreen_open_draft_before_merge_collective_multiselect_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_router",
    "register_fullscreen_open_draft_before_merge_collective_multiselect_floating_dr_workstation_record_model_decision_twin_search_html_native_marketplace_free_midnight_oil_settings_decision_competition_dr_nd_shadow_recursive_twin_compose_routes",
]
