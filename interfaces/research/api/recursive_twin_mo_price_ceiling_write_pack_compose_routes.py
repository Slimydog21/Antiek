"""Registerable HTTP surface for recursive twin + MO price-ceiling write pack."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.mo_price_ceiling_write_twin_settings_draft_compose_routes import (
    MoBody,
    ResearchWriteBody,
)
from substrate.recursive_twin_mo_price_ceiling_write_pack_compose import (
    RecursiveTwinMoPriceCeilingWritePackComposeError,
    compose_recursive_twin_mo_price_ceiling_write_pack,
)

recursive_twin_mo_price_ceiling_write_pack_compose_router = APIRouter(
    prefix="/research/recursive-twin-mo-price-ceiling-write-pack",
    tags=["recursive-twin-mo-price-ceiling-write-pack-compose"],
)


class TwinBody(BaseModel):
    model_config = {"extra": "forbid"}

    parent_asset_id: str = Field(min_length=1, max_length=256)
    source_excerpt: str = Field(min_length=1, max_length=100000)
    existing_twin_asset_id: str | None = Field(default=None, max_length=256)
    focus_questions: list[str] | None = None


class MoWriteBody(BaseModel):
    model_config = {"extra": "forbid"}

    mo: MoBody
    research_write: ResearchWriteBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    twin: TwinBody
    mo_write: MoWriteBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


@recursive_twin_mo_price_ceiling_write_pack_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_recursive_twin_mo_price_ceiling_write_pack(
            twin=req.twin.model_dump(),
            mo_write=req.mo_write.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except RecursiveTwinMoPriceCeilingWritePackComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result.to_dict()


def register_recursive_twin_mo_price_ceiling_write_pack_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        recursive_twin_mo_price_ceiling_write_pack_compose_router
    )


__all__ = [
    "recursive_twin_mo_price_ceiling_write_pack_compose_router",
    "register_recursive_twin_mo_price_ceiling_write_pack_compose_routes",
]
