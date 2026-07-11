"""HTTP surface for DRW source-policy preflight (probe_source consumer).

Register with::

    from interfaces.research.api.source_readiness_routes import (
        register_source_readiness_routes,
    )
    register_source_readiness_routes(app)

``app.py`` is currently owned by another lane; registration is additive and
tested via a local FastAPI app in unit tests until create_app can absorb it.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel, Field

from substrate.research_sources.preflight import (
    SourcePolicyPreflight,
    run_source_policy_preflight,
)

SourcePolicy = Literal["arxiv", "substack", "web", "operator_corpus"]

source_readiness_router = APIRouter(
    prefix="/research/source-policy",
    tags=["research-source-policy"],
)


class SourcePolicyPreflightRequest(BaseModel):
    source_policy: list[SourcePolicy] = Field(min_length=1)
    root_id: str | None = None
    problem: str | None = None


@source_readiness_router.post(
    "/preflight",
    response_model=SourcePolicyPreflight,
)
def source_policy_preflight(req: SourcePolicyPreflightRequest) -> SourcePolicyPreflight:
    """No-spend source-pack receipt driven by offline readiness probes."""
    return run_source_policy_preflight(
        list(req.source_policy),
        root_id=req.root_id,
        problem=req.problem,
    )


def register_source_readiness_routes(app: FastAPI) -> None:
    app.include_router(source_readiness_router)


__all__ = [
    "SourcePolicyPreflightRequest",
    "register_source_readiness_routes",
    "source_policy_preflight",
    "source_readiness_router",
]
