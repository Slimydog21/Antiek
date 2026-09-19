"""Route tests for mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk (advisory only)."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from interfaces.research.api.mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk_compose_routes import (
    post_mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk_compose,
)
from tests.test_mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk_compose import MO, MKT_PACK


def test_route_ready():
    r = post_mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk_compose(
        {
            "mo": MO,
            "mkt_pack": MKT_PACK,
            "operator_ack": True,
        }
    )
    assert r["ok"] is True
    assert r["pack_ready"] is True
    assert r["live_execution_authorized"] is False
    assert r["charge_executed"] is False
    assert r["purchase_executed"] is False
    assert r["production_router_verdict"] == "REJECT"


def test_route_operator_ack_false():
    r = post_mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk_compose(
        {
            "mo": MO,
            "mkt_pack": MKT_PACK,
            "operator_ack": False,
        }
    )
    assert r["ok"] is True
    assert r["pack_ready"] is False
    assert r["production_router_verdict"] == "REJECT"


def test_route_bad_body():
    r = post_mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk_compose("not-a-dict")  # type: ignore[arg-type]
    assert r["ok"] is False
    assert r["live_execution_authorized"] is False
    assert r["production_router_verdict"] == "REJECT"


def test_route_missing_mo():
    r = post_mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk_compose({"mkt_pack": MKT_PACK, "operator_ack": True})
    assert r["ok"] is False
    assert r["production_router_verdict"] == "REJECT"
