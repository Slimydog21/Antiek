"""Registerable HTTP surface for HTML-native + recursive twin MO write pack."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.html_native_view_session_authority_compose_routes import (
    ModeBody,
)
from interfaces.research.api.recursive_twin_mo_price_ceiling_write_pack_compose_routes import (
    MoWriteBody,
    TwinBody,
)
from substrate.html_native_recursive_twin_mo_write_pack_compose import (
    HtmlNativeRecursiveTwinMoWritePackComposeError,
    compose_html_native_recursive_twin_mo_write_pack,
)

html_native_recursive_twin_mo_write_pack_compose_router = APIRouter(
    prefix="/research/html-native-recursive-twin-mo-write-pack",
    tags=["html-native-recursive-twin-mo-write-pack-compose"],
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
    reading: ModeBody | None = None
    research: ModeBody | None = None


class TwinMoBody(BaseModel):
    model_config = {"extra": "forbid"}

    twin: TwinBody
    mo_write: MoWriteBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    html_view: HtmlViewBody
    twin_mo: TwinMoBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@html_native_recursive_twin_mo_write_pack_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_html_native_recursive_twin_mo_write_pack(
            html_view=req.html_view.model_dump(),
            twin_mo=req.twin_mo.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except HtmlNativeRecursiveTwinMoWritePackComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_html_native_recursive_twin_mo_write_pack_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(html_native_recursive_twin_mo_write_pack_compose_router)


__all__ = [
    "html_native_recursive_twin_mo_write_pack_compose_router",
    "register_html_native_recursive_twin_mo_write_pack_compose_routes",
]
