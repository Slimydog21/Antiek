"""Registerable HTTP surface for model decision + HTML-native settings marketplace free competition."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.html_native_settings_marketplace_free_competition_dr_nd_compose_routes import (
    HtmlViewBody,
    SettingsPackBody,
)
from interfaces.research.api.model_decision_twin_search_weekly_html_native_compose_routes import (
    DecisionBody,
)
from substrate.model_decision_html_native_settings_marketplace_free_competition_dr_nd_compose import (
    ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError,
    compose_model_decision_html_native_settings_marketplace_free_competition_dr_nd,
)

model_decision_html_native_settings_marketplace_free_competition_dr_nd_compose_router = (
    APIRouter(
        prefix=(
            "/research/model-decision-html-native-settings-marketplace-free-competition-dr-nd"
        ),
        tags=[
            "model-decision-html-native-settings-marketplace-free-competition-dr-nd-compose"
        ],
    )
)


class HtmlNativePackBody(BaseModel):
    model_config = {"extra": "forbid"}

    html_view: HtmlViewBody
    settings_pack: SettingsPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    decision: DecisionBody
    html_native_pack: HtmlNativePackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)
    block_on_budget_exceed: bool = Field(default=True, strict=True)


@model_decision_html_native_settings_marketplace_free_competition_dr_nd_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = (
            compose_model_decision_html_native_settings_marketplace_free_competition_dr_nd(
                decision=req.decision.model_dump(),
                html_native_pack=req.html_native_pack.model_dump(),
                operator_ack=req.operator_ack,
                require_both=req.require_both,
                block_on_budget_exceed=req.block_on_budget_exceed,
            )
        )
    except ModelDecisionHtmlNativeSettingsMarketplaceFreeCompetitionDrNdComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_model_decision_html_native_settings_marketplace_free_competition_dr_nd_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        model_decision_html_native_settings_marketplace_free_competition_dr_nd_compose_router
    )


__all__ = [
    "model_decision_html_native_settings_marketplace_free_competition_dr_nd_compose_router",
    "register_model_decision_html_native_settings_marketplace_free_competition_dr_nd_compose_routes",
]
