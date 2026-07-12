"""Registerable HTTP surface for recursive twin + settings fullscreen MO pack."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.settings_add_model_fullscreen_mo_draft_multi_compose_routes import (
    FullscreenMoBody,
    SettingsBody,
)
from substrate.recursive_twin_settings_fullscreen_mo_compose import (
    RecursiveTwinSettingsFullscreenMoComposeError,
    compose_recursive_twin_settings_fullscreen_mo,
)

recursive_twin_settings_fullscreen_mo_compose_router = APIRouter(
    prefix="/research/recursive-twin-settings-fullscreen-mo",
    tags=["recursive-twin-settings-fullscreen-mo-compose"],
)


class TwinBody(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    source_excerpt: str = Field(min_length=1, max_length=50000)
    existing_twin_asset_id: str | None = Field(default=None, max_length=256)
    focus_questions: list[str] | None = None


class SettingsPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    settings: SettingsBody
    fullscreen_mo: FullscreenMoBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    twin: TwinBody
    settings_pack: SettingsPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@recursive_twin_settings_fullscreen_mo_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_recursive_twin_settings_fullscreen_mo(
            twin=req.twin.model_dump(),
            settings_pack=req.settings_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except RecursiveTwinSettingsFullscreenMoComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_recursive_twin_settings_fullscreen_mo_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(recursive_twin_settings_fullscreen_mo_compose_router)


__all__ = [
    "recursive_twin_settings_fullscreen_mo_compose_router",
    "register_recursive_twin_settings_fullscreen_mo_compose_routes",
]
