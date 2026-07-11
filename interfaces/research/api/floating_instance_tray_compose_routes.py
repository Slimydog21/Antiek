"""Registerable HTTP surface for floating instance tray compose."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.floating_instance_tray_compose import (
    FloatingInstanceTrayComposeError,
    compose_floating_instance_tray,
)

floating_instance_tray_compose_router = APIRouter(
    prefix="/research/floating-tray",
    tags=["floating-instance-tray-compose"],
)


class MemberBody(BaseModel):
    model_config = {"extra": "forbid"}

    instance_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    status: Literal["proposed", "open", "completed", "closed"]
    view_mode: str | None = None
    highlight: str | None = None
    live_dispatched: Literal[False] = False
    merge_executed: Literal[False] = False


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    members: list[MemberBody] = Field(min_length=1)
    selected_instance_ids: list[str]
    action: Literal[
        "none",
        "fullscreen_one",
        "collective_pack",
        "cohesive_prompt",
        "draft_merge_one",
        "full_merge_one",
    ]
    operator_ack: bool = Field(strict=True)


@floating_instance_tray_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_floating_instance_tray(
            parent_asset_id=req.parent_asset_id,
            members=[m.model_dump() for m in req.members],
            selected_instance_ids=list(req.selected_instance_ids),
            action=req.action,
            operator_ack=req.operator_ack,
        )
    except FloatingInstanceTrayComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_floating_instance_tray_compose_routes(app: FastAPI) -> None:
    app.include_router(floating_instance_tray_compose_router)


__all__ = [
    "floating_instance_tray_compose_router",
    "register_floating_instance_tray_compose_routes",
]
