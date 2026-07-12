"""Registerable HTTP surface for competition DR over ND shadow twin presentation weekly."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.competition_dr_quality_source_pack_compose_routes import (
    CitationBody,
    DecisionArea,
    DecisionBody,
    CitationFamily,
)
from interfaces.research.api.nd_shadow_recursive_twin_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack_compose_routes import (
    NdShadowBody,
    TwinPresentationBody,
)
from substrate.competition_dr_nd_shadow_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack_compose import (
    CompetitionDrNdShadowWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpackComposeError,
    compose_competition_dr_nd_shadow_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack,
)

competition_dr_nd_shadow_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack_compose_router = APIRouter(
    prefix="/research/competition-dr-nd-shadow-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mpack",
    tags=["competition-dr-nd-shadow-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mpack-compose"],
)


class CompetitionBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    competitor_decisions: list[DecisionBody]
    focus_areas: list[DecisionArea] | None = None
    requested_families: list[CitationFamily] = Field(min_length=1)
    citations: list[CitationBody]
    filter_to_selected_families: bool | None = Field(default=None, strict=True)
    quality_overall: float | None = Field(default=None, ge=0, le=1)
    quality_floor: float | None = Field(default=None, ge=0, le=1)
    would_exceed: bool | None = None
    operator_override: bool | None = Field(default=None, strict=True)
    require_no_behind_gaps: bool | None = Field(default=None, strict=True)


class NdPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    nd_shadow: NdShadowBody
    twin_presentation: TwinPresentationBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    competition: CompetitionBody
    nd_pack: NdPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


def _surface(result: Any) -> dict[str, Any]:
    """HTTP surface projection — honesty flags + child pack_ready only."""
    return {
        "session_id": result.session_id,
        "week_id": result.week_id,
        "parent_asset_id": result.parent_asset_id,
        "asset_id": result.asset_id,
        "title": result.title,
        "account_id": result.account_id,
        "session_aligned": result.session_aligned,
        "pack_ready": result.pack_ready,
        "live_dispatch_authorized": False,
        "remote_fetched": False,
        "backlog_mutated": False,
        "store_mutated": False,
        "suite_rewritten": False,
        "production_router_verdict": "REJECT",
        "live_router_authorized": False,
        "twin_written": False,
        "purchase_executed": False,
        "hosted": False,
        "prompts_injected": False,
        "pdf_view_authorized": False,
        "pdf_primary": False,
        "charge_executed": False,
        "live_execution_authorized": False,
        "draft_written": False,
        "analysis_written": False,
        "merge_executed": False,
        "record_persisted": False,
        "secrets_stored": False,
        "inventory_mutated": False,
        "live_dispatched": False,
        "pack_dispatched": False,
        "authority": result.authority,
        "notes_count": len(result.notes),
        "competition": {
            "pack_ready": result.competition.pack_ready,
            "remote_fetched": getattr(result.competition, "remote_fetched", False),
            "live_dispatch_authorized": getattr(
                result.competition, "live_dispatch_authorized", False
            ),
        },
        "nd_pack": {
            "pack_ready": result.nd_pack.pack_ready,
            "live_router_authorized": result.nd_pack.live_router_authorized,
            "production_router_verdict": result.nd_pack.production_router_verdict,
            "twin_written": getattr(result.nd_pack, "twin_written", False),
        },
    }


@competition_dr_nd_shadow_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_competition_dr_nd_shadow_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack(
            competition=req.competition.model_dump(),
            nd_pack=req.nd_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except CompetitionDrNdShadowWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpackComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _surface(result)


def register_competition_dr_nd_shadow_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        competition_dr_nd_shadow_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack_compose_router
    )


__all__ = [
    "CompetitionBody",
    "NdPackBody",
    "competition_dr_nd_shadow_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack_compose_router",
    "register_competition_dr_nd_shadow_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack_compose_routes",
]
