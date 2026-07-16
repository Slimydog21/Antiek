"""Registerable HTTP surface for twin-search residual over HTML-native mow12."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from interfaces.research.api.hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow22_mpk_compose_routes import (
    HtmlViewBody,
    MarketPackBody,
)
from substrate.ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow22_mpk_compose import (
    AUTHORITY,
    TsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow22MpkComposeError,
    compose_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow22_mpk,
)

ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow22_mpk_compose_router = APIRouter(
    prefix="/research/ts-hn-mkt-mo-sd-cd-nds-rt-ab-sa-wt-fs-dbm-col-fdr-ws-md-ts-hn-mkt-mo-sd-cd-nds-rt-ab-sa-wt-fs-dbm-col-fdr-ws-md-ts-hn-mkt-mo-sd-cd-nds-rt-ab-sa-wt-fs-dbm-col-fdr-ws-md-ts-hn-mkt-mo-sd-cd-nds-mow22-mpk",
    tags=["ts-hn-mkt-mo-sd-cd-nds-rt-ab-sa-wt-fs-dbm-col-fdr-ws-md-ts-hn-mkt-mo-sd-cd-nds-rt-ab-sa-wt-fs-dbm-col-fdr-ws-md-ts-hn-mkt-mo-sd-cd-nds-rt-ab-sa-wt-fs-dbm-col-fdr-ws-md-ts-hn-mkt-mo-sd-cd-nds-mow22-mpk-compose"],
)


class TwinRecordBody(BaseModel):
    model_config = {"extra": "forbid"}

    twin_id: str = Field(min_length=1, max_length=256)
    parent_asset_id: str = Field(min_length=1, max_length=256)
    insights: list[str]
    questions: list[str]
    source_label: str | None = Field(default=None, max_length=256)


class HtmlPackBody(BaseModel):
    model_config = {"extra": "forbid"}

    html_view: HtmlViewBody
    market_pack: MarketPackBody
    require_both: bool | None = Field(default=None, strict=True)


class ComposeRequest(BaseModel):
    model_config = {"extra": "forbid"}

    search_query: str = Field(min_length=1, max_length=2000)
    twin_records: list[TwinRecordBody]
    html_pack: HtmlPackBody
    operator_ack: bool = Field(strict=True)
    search_limit: int | None = Field(default=None, ge=1, le=1000)
    require_both: bool = Field(default=True, strict=True)


def _surface(result: Any) -> dict[str, Any]:
    """HTTP surface projection — honesty flags + hit_count only."""
    return {
        "week_id": result.week_id,
        "session_id": result.session_id,
        "parent_asset_id": result.parent_asset_id,
        "asset_id": result.asset_id,
        "title": result.title,
        "account_id": result.account_id,
        "hit_count": result.hit_count,
        "search": {
            "query": result.search.query,
            "hits": [
                {
                    "twin_id": h.twin_id if hasattr(h, "twin_id") else h.get("twin_id"),
                    "score": h.score if hasattr(h, "score") else h.get("score"),
                }
                for h in (result.search.hits if hasattr(result.search, "hits") else [])
            ],
        },
        "html_pack": {
            "pack_ready": result.html_pack.pack_ready,
            "pdf_primary": False,
            "production_router_verdict": "REJECT",
        },
        "pack_ready": result.pack_ready,
        "remote_index_queried": False,
        "twin_written": False,
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
        "production_router_verdict": "REJECT",
        "authority": result.authority,
    }


@ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow22_mpk_compose_router.post(
    "/compose"
)
def post_compose(req: ComposeRequest) -> dict[str, Any]:
    try:
        result = compose_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow22_mpk(
            search_query=req.search_query,
            twin_records=[r.model_dump() for r in req.twin_records],
            html_pack=req.html_pack.model_dump(),
            operator_ack=req.operator_ack,
            search_limit=req.search_limit,
            require_both=req.require_both,
        )
    except TsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsMow22MpkComposeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _surface(result)


def register_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow22_mpk_compose_routes(
    app: FastAPI,
) -> None:
    app.include_router(
        ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow22_mpk_compose_router
    )


__all__ = [
    "ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow22_mpk_compose_router",
    "register_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow22_mpk_compose_routes",
    "AUTHORITY",
]
