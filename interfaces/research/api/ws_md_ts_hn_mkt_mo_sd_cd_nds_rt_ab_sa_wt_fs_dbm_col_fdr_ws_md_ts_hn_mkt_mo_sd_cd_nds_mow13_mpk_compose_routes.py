"""Registerable HTTP surface for workstation residual over model-decision mow12."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow13_mpk_compose_routes import (
    DecisionBody,
    TwinSearchPackBody,
)
from substrate.ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow13_mpk_compose import (
    AUTHORITY,
    WsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow13MpkComposeError,
    compose_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow13_mpk,
)

ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow13_mpk_compose_router = APIRouter(
    prefix="/research/ws-md-ts-hn-mkt-mo-sd-cd-nds-rt-ab-sa-wt-fs-dbm-col-fdr-ws-md-ts-hn-mkt-mo-sd-cd-nds-mow13-mpk",
    tags=["ws-md-ts-hn-mkt-mo-sd-cd-nds-rt-ab-sa-wt-fs-dbm-col-fdr-ws-md-ts-hn-mkt-mo-sd-cd-nds-mow13-mpk-compose"],
)


class RecordItemBody(BaseModel):
    model_config = {"extra": "forbid"}

    record_id: str = Field(min_length=1, max_length=256)
    kind: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=8000)
    asset_id: str | None = Field(default=None, max_length=256)
    weight: float | None = None


class DecisionPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    decision: DecisionBody
    twin_search_pack: TwinSearchPackBody
    require_both: bool | None = Field(default=None, strict=True)
    block_on_budget_exceed: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    session_id: str = Field(min_length=1, max_length=256)
    items: list[RecordItemBody]
    decision_pack: DecisionPackBody
    operator_ack: bool = Field(strict=True)
    max_context_lines: int | None = Field(default=None, ge=1, le=10000)
    require_both: bool = Field(default=True, strict=True)


def _surface(result: Any) -> dict[str, Any]:
    """HTTP surface projection — honesty flags + pack_ready only."""
    return {
        "week_id": result.week_id,
        "session_id": result.session_id,
        "parent_asset_id": result.parent_asset_id,
        "asset_id": result.asset_id,
        "title": result.title,
        "account_id": result.account_id,
        "records": {
            "pack_ready": result.records.pack_ready,
            "item_count": result.records.item_count,
            "record_persisted": False,
            "prompts_injected": False,
        },
        "decision_pack": {
            "pack_ready": result.decision_pack.pack_ready,
            "live_router_authorized": False,
            "production_router_verdict": "REJECT",
        },
        "session_aligned": result.session_aligned,
        "pack_ready": result.pack_ready,
        "record_persisted": False,
        "prompts_injected": False,
        "live_router_authorized": False,
        "secrets_stored": False,
        "live_meter_read": False,
        "remote_index_queried": False,
        "twin_written": False,
        "purchase_executed": False,
        "hosted": False,
        "pdf_view_authorized": False,
        "pdf_primary": False,
        "live_execution_authorized": False,
        "charge_executed": False,
        "production_router_verdict": "REJECT",
        "authority": result.authority,
    }


@ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow13_mpk_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow13_mpk(
            session_id=req.session_id,
            items=[i.model_dump() for i in req.items],
            decision_pack=req.decision_pack.model_dump(),
            operator_ack=req.operator_ack,
            max_context_lines=req.max_context_lines,
            require_both=req.require_both,
        )
    except WsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow13MpkComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _surface(result)


def register_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow13_mpk_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow13_mpk_compose_router
    )


__all__ = [
    "ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow13_mpk_compose_router",
    "register_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow13_mpk_compose_routes",
    "AUTHORITY",
]
