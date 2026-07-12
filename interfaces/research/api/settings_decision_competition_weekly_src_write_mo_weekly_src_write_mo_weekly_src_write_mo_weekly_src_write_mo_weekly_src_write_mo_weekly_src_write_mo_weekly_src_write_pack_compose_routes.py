"""Registerable HTTP surface for settings decision over competition DR ND shadow twin weekly."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.competition_dr_nd_shadow_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes import (
    CompetitionBody,
    NdPackBody,
)
from interfaces.research.api.settings_add_model_bench_decision_compose_routes import (
    DecisionModelBody,
    EventBody,
    InventoryModelBody,
    TaskFamilySeedBody,
)
from substrate.settings_decision_competition_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    SettingsDecisionCompetitionWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError,
    compose_settings_decision_competition_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack,
)

settings_decision_competition_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router = APIRouter(
    prefix="/research/settings-decision-competition-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack",
    tags=["settings-decision-competition-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack-compose"],
)


class SettingsBody(BaseModel):
    model_config = {"extra": "forbid"}

    models: list[InventoryModelBody]
    pending_add_model_ids: list[str]
    action: Literal["preview", "propose_add"]
    week_id: str = Field(min_length=1, max_length=64)
    focus_task: str = Field(min_length=1, max_length=256)
    events: list[EventBody]
    daily_cap_usd: float | None = Field(default=None, ge=0)
    spent_usd: float | None = Field(default=None, ge=0)
    decision_models: list[DecisionModelBody] | None = None
    selected_model_id: str | None = Field(default=None, max_length=128)
    projected_cost_usd_high: float | None = Field(default=None, ge=0)
    projected_cost_usd_low: float | None = Field(default=None, ge=0)
    existing_tasks: list[str] | None = None
    proposed_new_tasks: list[TaskFamilySeedBody] | None = None
    min_events_for_recommendation: int | None = Field(default=None, ge=1)
    require_both: bool | None = Field(default=None, strict=True)


class CompetitionPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    competition: CompetitionBody
    nd_pack: NdPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    settings: SettingsBody
    competition_pack: CompetitionPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


def _surface(result: Any) -> dict[str, Any]:
    """HTTP surface projection — honesty flags + child pack_ready only."""
    return {
        "session_id": getattr(result, "session_id", None),
        "week_id": getattr(result, "week_id", None),
        "parent_asset_id": getattr(result, "parent_asset_id", None),
        "asset_id": getattr(result, "asset_id", None),
        "week_aligned": getattr(result, "week_aligned", False),
        "pack_ready": result.pack_ready,
        "live_router_authorized": False,
        "secrets_stored": False,
        "inventory_mutated": False,
        "remote_fetched": False,
        "live_dispatch_authorized": False,
        "twin_written": False,
        "backlog_mutated": False,
        "store_mutated": False,
        "suite_rewritten": False,
        "production_router_verdict": "REJECT",
        "authority": result.authority,
        "notes_count": len(result.notes),
        "settings": {
            "pack_ready": getattr(
                result.settings,
                "pack_ready",
                getattr(result.settings, "decision_ready", False),
            ),
            "secrets_stored": getattr(result.settings, "secrets_stored", False),
        },
        "competition_pack": {
            "pack_ready": result.competition_pack.pack_ready,
            "live_dispatch_authorized": getattr(
                result.competition_pack, "live_dispatch_authorized", False
            ),
            "production_router_verdict": getattr(
                result.competition_pack, "production_router_verdict", "REJECT"
            ),
        },
    }


@settings_decision_competition_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_settings_decision_competition_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
            settings=req.settings.model_dump(),
            competition_pack=req.competition_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except SettingsDecisionCompetitionWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _surface(result)


def register_settings_decision_competition_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        settings_decision_competition_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router
    )


__all__ = [
    "SettingsBody",
    "CompetitionPackBody",
    "settings_decision_competition_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router",
    "register_settings_decision_competition_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes",
]
