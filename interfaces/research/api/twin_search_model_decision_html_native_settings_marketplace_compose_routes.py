"""Registerable HTTP surface for twin search over model decision HTML-native settings marketplace."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.model_decision_html_native_settings_marketplace_free_competition_dr_nd_compose_routes import (
    DecisionBody,
    HtmlNativePackBody,
)
from interfaces.research.api.twin_search_html_native_marketplace_free_settings_compose_routes import (
    TwinRecordBody,
)
from substrate.twin_search_model_decision_html_native_settings_marketplace_compose import (
    TwinSearchModelDecisionHtmlNativeSettingsMarketplaceComposeError,
    compose_twin_search_model_decision_html_native_settings_marketplace,
)

twin_search_model_decision_html_native_settings_marketplace_compose_router = APIRouter(
    prefix="/research/twin-search-model-decision-html-native-settings-marketplace",
    tags=["twin-search-model-decision-html-native-settings-marketplace-compose"],
)


class ModelDecisionPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    decision: DecisionBody
    html_native_pack: HtmlNativePackBody
    require_both: bool | None = Field(default=None, strict=True)
    block_on_budget_exceed: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    search_query: str = Field(min_length=1, max_length=2048)
    twin_records: list[TwinRecordBody]
    model_decision_pack: ModelDecisionPackBody
    operator_ack: bool = Field(strict=True)
    search_limit: int | None = Field(default=None, ge=1, le=500)
    require_both: bool = Field(default=True, strict=True)


@twin_search_model_decision_html_native_settings_marketplace_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_twin_search_model_decision_html_native_settings_marketplace(
            search_query=req.search_query,
            twin_records=[r.model_dump() for r in req.twin_records],
            model_decision_pack=req.model_decision_pack.model_dump(),
            operator_ack=req.operator_ack,
            search_limit=req.search_limit,
            require_both=req.require_both,
        )
    except TwinSearchModelDecisionHtmlNativeSettingsMarketplaceComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_twin_search_model_decision_html_native_settings_marketplace_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        twin_search_model_decision_html_native_settings_marketplace_compose_router
    )


__all__ = [
    "twin_search_model_decision_html_native_settings_marketplace_compose_router",
    "register_twin_search_model_decision_html_native_settings_marketplace_compose_routes",
]
