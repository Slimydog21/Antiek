"""Registerable HTTP surface for HTML-native + recursive twin settings fullscreen MO pack."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.recursive_twin_settings_fullscreen_mo_compose_routes import (
    SettingsPackBody,
    TwinBody,
)
from substrate.html_native_recursive_twin_settings_fullscreen_mo_compose import (
    HtmlNativeRecursiveTwinSettingsFullscreenMoComposeError,
    compose_html_native_recursive_twin_settings_fullscreen_mo,
)

html_native_recursive_twin_settings_fullscreen_mo_compose_router = APIRouter(
    prefix="/research/html-native-recursive-twin-settings-fullscreen-mo",
    tags=["html-native-recursive-twin-settings-fullscreen-mo-compose"],
)


class HtmlViewBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    asset_id: str = Field(min_length=1, max_length=256)
    html_projection_sha: str | None = Field(default=None, max_length=128)
    view_requested: bool = Field(strict=True)
    twin_bound: bool = Field(strict=True)
    twin_substrate_ready: bool | None = Field(default=None, strict=True)
    claimed_format: str | None = Field(default=None, max_length=64)


class TwinPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    twin: TwinBody
    settings_pack: SettingsPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    html_view: HtmlViewBody
    twin_pack: TwinPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@html_native_recursive_twin_settings_fullscreen_mo_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_html_native_recursive_twin_settings_fullscreen_mo(
            html_view=req.html_view.model_dump(),
            twin_pack=req.twin_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except HtmlNativeRecursiveTwinSettingsFullscreenMoComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_html_native_recursive_twin_settings_fullscreen_mo_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        html_native_recursive_twin_settings_fullscreen_mo_compose_router
    )


__all__ = [
    "html_native_recursive_twin_settings_fullscreen_mo_compose_router",
    "register_html_native_recursive_twin_settings_fullscreen_mo_compose_routes",
]
