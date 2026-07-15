"""Registerable HTTP surface for collective residual over floating DR tip residual mow12."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from typing import Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow14_mpk_compose_routes import (
    HighlightLaunchBody,
    RecordPackBody,
)
from interfaces.research.api.floating_multi_select_collective_cohesive_compose_routes import (
    MemberBody,
)
from substrate.col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow14_mpk_compose import (
    AUTHORITY,
    ColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow14MpkComposeError,
    compose_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow14_mpk,
)

col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow14_mpk_compose_router = APIRouter(
    prefix="/research/col-fdr-ws-md-ts-hn-mkt-mo-sd-cd-nds-rt-ab-sa-wt-fs-dbm-col-fdr-ws-md-ts-hn-mkt-mo-sd-cd-nds-rt-ab-sa-wt-fs-dbm-col-fdr-ws-md-ts-hn-mkt-mo-sd-cd-nds-rt-ab-sa-wt-fs-dbm-col-fdr-ws-md-ts-hn-mkt-mo-sd-cd-nds-mow14-mpk",
    tags=["col-fdr-ws-md-ts-hn-mkt-mo-sd-cd-nds-rt-ab-sa-wt-fs-dbm-col-fdr-ws-md-ts-hn-mkt-mo-sd-cd-nds-rt-ab-sa-wt-fs-dbm-col-fdr-ws-md-ts-hn-mkt-mo-sd-cd-nds-rt-ab-sa-wt-fs-dbm-col-fdr-ws-md-ts-hn-mkt-mo-sd-cd-nds-mow14-mpk-compose"],
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
    return {
        "week_id": result.week_id,
        "session_id": result.session_id,
        "parent_asset_id": result.parent_asset_id,
        "asset_id": result.asset_id,
        "title": result.title,
        "account_id": result.account_id,
        "multiselect": {
            "pack_ready": result.multiselect.pack_ready,
            "live_dispatched": False,
            "pack_dispatched": False,
            "analysis_written": False,
        },
        "floating_pack": {
            "pack_ready": result.floating_pack.pack_ready,
            "live_dispatched": False,
            "merge_executed": False,
        },
        "session_aligned": result.session_aligned,
        "parent_aligned": result.parent_aligned,
        "pack_ready": result.pack_ready,
        "live_dispatched": False,
        "pack_dispatched": False,
        "merge_executed": False,
        "analysis_written": False,
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
        "inventory_mutated": False,
        "live_dispatch_authorized": False,
        "remote_fetched": False,
        "backlog_mutated": False,
        "store_mutated": False,
        "suite_rewritten": False,
        "draft_written": False,
        "production_router_verdict": "REJECT",
        "authority": result.authority,
    }


@col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow14_mpk_compose_router.post("/compose")
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow14_mpk(
            multiselect=req.multiselect.model_dump(),
            floating_pack=req.floating_pack.model_dump(),
            operator_ack=req.operator_ack,
            require_both=req.require_both,
        )
    except ColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow14MpkComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _surface(result)


def register_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow14_mpk_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow14_mpk_compose_router)


__all__ = [
    "col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow14_mpk_compose_router",
    "register_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow14_mpk_compose_routes",
    "AUTHORITY",
]
