"""Pure tests for marketplace free residual over Midnight Oil mow12."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from substrate.mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow25_mpk_compose import (
    AUTHORITY,
    compose_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow25_mpk,
    format_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow25_mpk_summary,
)
from tests.test_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow25_mpk_compose import (
    MO,
    SETTINGS_PACK,
)

MARKET = {
    "title": "Scaling Laws Book",
    "account_id": "acct-1",
    "free_copy_available": True,
    "free_html_projection_sha": "sha-free-1",
    "purchase_ack": False,
    "port_requested": True,
}

MO_PACK = {
    "mo": MO,
    "settings_pack": SETTINGS_PACK,
}


def test_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_mow12_ready():
    c = compose_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow25_mpk(
        market=MARKET,
        mo_pack=MO_PACK,
        operator_ack=True,
    )
    assert c.market.port_ready is True
    assert c.market.path == "prefer_free_html"
    assert c.mo_pack.pack_ready is True
    assert c.account_aligned is True
    assert c.pack_ready is True
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.pdf_view_authorized is False
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.twin_written is False
    assert c.production_router_verdict == "REJECT"
    assert c.authority == AUTHORITY
    assert "purchase_executed=false" in (
        format_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow25_mpk_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow25_mpk(
        market=MARKET,
        mo_pack=MO_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.charge_executed is False
    assert c.production_router_verdict == "REJECT"


def test_account_mismatch_blocks():
    c = compose_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow25_mpk(
        market={**MARKET, "account_id": "acct-other"},
        mo_pack=MO_PACK,
        operator_ack=True,
    )
    assert c.account_aligned is False
    assert c.pack_ready is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.production_router_verdict == "REJECT"


def test_unknown_free_blocks_port():
    c = compose_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow25_mpk(
        market={**MARKET, "free_copy_available": None},
        mo_pack=MO_PACK,
        operator_ack=True,
    )
    assert c.market.port_ready is False
    assert c.market.path == "blocked_unknown_free"
    assert c.pack_ready is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.production_router_verdict == "REJECT"
