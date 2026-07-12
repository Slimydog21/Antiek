"""Registerable HTTP surface for collective multiselect over floating DR workstation MO weekly src write pack."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes import (
    HighlightLaunchBody,
    RecordPackBody,
)
from interfaces.research.api.floating_multi_select_collective_cohesive_compose_routes import (
    MemberBody,
)
from substrate.collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    CollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError,
    compose_collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack,
)

collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router = APIRouter(
    prefix="/research/collective-multiselect-floating-dr-workstation-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack",
    tags=["collective-multiselect-floating-dr-workstation-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack-compose"],
)


class MultiselectBody(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    members: list[MemberBody] = Field(min_length=2)
    selected_instance_ids: list[str] = Field(min_length=2)
    pack_mode: Literal[
        "cohesive_prompt", "collective_pack", "cohesive_plus_analysis"
    ]
    cohesive_prompt: str = Field(min_length=1, max_length=8000)
    extra_context: list[str] | None = None
    analysis_kind: Literal["draft_analysis", "full_analysis"] | None = None
    extra_findings: list[str] | None = None


class FloatingPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    highlight_launch: HighlightLaunchBody
    record_pack: RecordPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    multiselect: MultiselectBody
    floating_pack: FloatingPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)



def _surface(result: Any) -> dict[str, Any]:
    """HTTP surface projection — honesty flags + child pack_ready only.

    Full recursive to_dict() exceeds pydantic JSON depth (~256) and can explode
    notes to multi-GB. Pure compose remains authoritative for the honesty graph.
    """
    return {
        "week_id": result.week_id,
        "session_id": result.session_id,
        "parent_asset_id": result.parent_asset_id,
        "asset_id": result.asset_id,
        "title": result.title,
        "account_id": result.account_id,
        "session_aligned": result.session_aligned,
        "parent_aligned": result.parent_aligned,
        "pack_ready": result.pack_ready,
        "live_dispatched": result.live_dispatched,
        "pack_dispatched": result.pack_dispatched,
        "merge_executed": result.merge_executed,
        "analysis_written": result.analysis_written,
        "record_persisted": result.record_persisted,
        "prompts_injected": result.prompts_injected,
        "live_router_authorized": result.live_router_authorized,
        "secrets_stored": result.secrets_stored,
        "remote_index_queried": result.remote_index_queried,
        "twin_written": result.twin_written,
        "purchase_executed": result.purchase_executed,
        "hosted": result.hosted,
        "pdf_view_authorized": result.pdf_view_authorized,
        "pdf_primary": result.pdf_primary,
        "live_dispatch_authorized": result.live_dispatch_authorized,
        "live_execution_authorized": result.live_execution_authorized,
        "charge_executed": result.charge_executed,
        "production_router_verdict": result.production_router_verdict,
        "authority": result.authority,
        "multiselect": {
            "pack_ready": result.multiselect.pack_ready,
            "pack_mode": result.multiselect.pack_mode,
            "live_dispatched": result.multiselect.live_dispatched,
            "pack_dispatched": result.multiselect.pack_dispatched,
            "merge_executed": result.multiselect.merge_executed,
            "analysis_written": result.multiselect.analysis_written,
        },
        "floating_pack": {
            "pack_ready": result.floating_pack.pack_ready,
            "live_dispatched": result.floating_pack.live_dispatched,
            "merge_executed": result.floating_pack.merge_executed,
            "record_persisted": result.floating_pack.record_persisted,
            "production_router_verdict": result.floating_pack.production_router_verdict,
        },
        "notes_count": len(result.notes),
    }

@collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router.post(
    "/compose"
)

def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
            multiselect=req.multiselect.model_dump(),
            floating_pack=req.floating_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except CollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _surface(result)


def register_collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router
    )


__all__ = [
    "collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router",
    "register_collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes",
]
