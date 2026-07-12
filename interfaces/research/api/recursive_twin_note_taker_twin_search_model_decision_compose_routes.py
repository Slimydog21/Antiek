"""Registerable HTTP surface for recursive twin note-taker over twin search model decision pack."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.recursive_twin_marketplace_free_competition_dr_compose_routes import (
    TwinBody,
)
from interfaces.research.api.twin_search_model_decision_html_native_settings_marketplace_compose_routes import (
    ModelDecisionPackBody,
)
from interfaces.research.api.twin_search_html_native_marketplace_free_settings_compose_routes import (
    TwinRecordBody,
)
from substrate.recursive_twin_note_taker_twin_search_model_decision_compose import (
    RecursiveTwinNoteTakerTwinSearchModelDecisionComposeError,
    compose_recursive_twin_note_taker_twin_search_model_decision,
)

recursive_twin_note_taker_twin_search_model_decision_compose_router = APIRouter(
    prefix="/research/recursive-twin-note-taker-twin-search-model-decision",
    tags=["recursive-twin-note-taker-twin-search-model-decision-compose"],
)


class TwinSearchPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    search_query: str = Field(min_length=1, max_length=2048)
    twin_records: list[TwinRecordBody]
    model_decision_pack: ModelDecisionPackBody
    search_limit: int | None = Field(default=None, ge=1, le=500)
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    twin: TwinBody
    twin_search_pack: TwinSearchPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@recursive_twin_note_taker_twin_search_model_decision_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_recursive_twin_note_taker_twin_search_model_decision(
            twin=req.twin.model_dump(),
            twin_search_pack=req.twin_search_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except RecursiveTwinNoteTakerTwinSearchModelDecisionComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_recursive_twin_note_taker_twin_search_model_decision_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        recursive_twin_note_taker_twin_search_model_decision_compose_router
    )


__all__ = [
    "recursive_twin_note_taker_twin_search_model_decision_compose_router",
    "register_recursive_twin_note_taker_twin_search_model_decision_compose_routes",
]
