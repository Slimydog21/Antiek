"""Registerable HTTP surface for recursive twin session pack compose."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from substrate.recursive_twin_session_pack_compose import (
    RecursiveTwinSessionPackComposeError,
    compose_recursive_twin_session_pack,
)

recursive_twin_session_pack_compose_router = APIRouter(
    prefix="/twins/session-pack",
    tags=["recursive-twin-session-pack-compose"],
)


class MemberBody(BaseModel):
    model_config = {"extra": "forbid"}

    asset_id: str = Field(min_length=1, max_length=256)
    twin_bound: bool = Field(strict=True)
    insights: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    search_hits: int | None = Field(default=None, ge=0)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    members: list[MemberBody] = Field(min_length=1)


@recursive_twin_session_pack_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        pack = compose_recursive_twin_session_pack(
            session_id=req.session_id,
            members=[m.model_dump() for m in req.members],
        )
    except RecursiveTwinSessionPackComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return pack.to_dict()


def register_recursive_twin_session_pack_compose_routes(app: FastAPI) -> None:
    app.include_router(recursive_twin_session_pack_compose_router)


__all__ = [
    "recursive_twin_session_pack_compose_router",
    "register_recursive_twin_session_pack_compose_routes",
]
