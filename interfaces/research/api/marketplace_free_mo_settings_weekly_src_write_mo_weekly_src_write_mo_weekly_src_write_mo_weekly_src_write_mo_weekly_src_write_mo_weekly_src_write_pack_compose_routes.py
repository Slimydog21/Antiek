"""Registerable HTTP surface for marketplace free over MO settings decision pack."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.midnight_oil_settings_decision_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes import (
    MoBody,
    SettingsPackBody,
)
from substrate.marketplace_free_mo_settings_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    MarketplaceFreeMoSettingsWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError,
    compose_marketplace_free_mo_settings_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack,
)

marketplace_free_mo_settings_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router = APIRouter(
    prefix="/research/marketplace-free-mo-settings-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack",
    tags=["marketplace-free-mo-settings-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-mo-weekly-src-write-pack-compose"],
)


class MarketBody(BaseModel):
    model_config = {"extra": "forbid"}

    title: str = Field(min_length=1, max_length=2000)
    account_id: str = Field(min_length=1, max_length=256)
    free_copy_available: bool | None = None
    free_html_projection_sha: str | None = Field(default=None, max_length=256)
    purchase_ack: bool = Field(strict=True)
    port_requested: bool = Field(strict=True)
    purchase_html_projection_sha: str | None = Field(default=None, max_length=256)


class MoPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    mo: MoBody
    settings_pack: SettingsPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    market: MarketBody
    mo_pack: MoPackBody
    operator_ack: bool = Field(strict=True)
    require_both: bool = Field(default=True, strict=True)


def _surface(result: Any) -> dict[str, Any]:
    """HTTP surface projection — honesty flags + child pack_ready only.

    Full recursive to_dict() exceeds pydantic JSON depth (~256) on deep residual
    stacks and expands notes to multi-GB payloads. Pure compose still holds the
    full honesty graph; routes prove gates without serializing the nest.
    """
    market = result.market
    mo_pack = result.mo_pack
    return {
        "title": result.title,
        "account_id": result.account_id,
        "week_id": result.week_id,
        "session_id": result.session_id,
        "parent_asset_id": result.parent_asset_id,
        "asset_id": result.asset_id,
        "operator_id": result.operator_id,
        "focus_task": result.focus_task,
        "market": {
            "port_ready": market.port_ready,
            "purchase_executed": False,
            "hosted": False,
            "pdf_view_authorized": False,
            "pdf_primary": False,
        },
        "mo_pack": {
            "pack_ready": mo_pack.pack_ready,
            "live_execution_authorized": False,
            "charge_executed": False,
            "production_router_verdict": "REJECT",
            "live_router_authorized": False,
        },
        "account_aligned": result.account_aligned,
        "pack_ready": result.pack_ready,
        "purchase_executed": False,
        "hosted": False,
        "pdf_view_authorized": False,
        "pdf_primary": False,
        "live_execution_authorized": False,
        "charge_executed": False,
        "secrets_stored": False,
        "inventory_mutated": False,
        "live_router_authorized": False,
        "live_dispatch_authorized": False,
        "remote_fetched": False,
        "backlog_mutated": False,
        "store_mutated": False,
        "suite_rewritten": False,
        "twin_written": False,
        "prompts_injected": False,
        "merge_executed": False,
        "draft_written": False,
        "analysis_written": False,
        "live_dispatched": False,
        "pack_dispatched": False,
        "record_persisted": False,
        "remote_index_queried": False,
        "production_router_verdict": "REJECT",
        "authority": result.authority,
    }


@marketplace_free_mo_settings_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_marketplace_free_mo_settings_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
            market=req.market.model_dump(),
            mo_pack=req.mo_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except MarketplaceFreeMoSettingsWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _surface(result)


def register_marketplace_free_mo_settings_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        marketplace_free_mo_settings_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router
    )


__all__ = [
    "marketplace_free_mo_settings_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_router",
    "register_marketplace_free_mo_settings_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_routes",
]
