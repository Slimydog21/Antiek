"""Pure tests for Midnight Oil residual re-entry over marketplace free mow29."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from substrate.mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk_compose import (
    AUTHORITY,
    compose_mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk,
    format_mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk_summary,
)
from tests.test_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow28_mpk_compose import (
    MARKET,
    MO_PACK,
)

MO = {
    "operator_id": "op-1",
    "work_minutes": 120,
    "goals": [
        {"goal_id": "g1", "title": "Map scaling literature"},
        {"goal_id": "g2", "title": "Synthesize open problems"},
    ],
    "usd_per_hour": 30,
    "approved_ceiling_usd": 500,
    "price_ceiling_ack": True,
    "unattended_ack": True,
    "spend_consent": True,
    "stage": "unattended_pack",
}

MKT_PACK = {
    "market": MARKET,
    "mo_pack": MO_PACK,
}


def test_mo_mkt_reentry_ready():
    c = compose_mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk(
        mo=MO,
        mkt_pack=MKT_PACK,
        operator_ack=True,
    )
    assert c.mo.pack_ready is True
    assert c.mkt_pack.pack_ready is True
    assert c.account_aligned is True
    assert c.pack_ready is True
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.pdf_primary is False
    assert c.twin_written is False
    assert c.production_router_verdict == "REJECT"
    assert c.authority == AUTHORITY
    assert "charge_executed=false" in format_mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk_summary(c)


def test_operator_ack_false_blocks():
    c = compose_mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk(
        mo=MO,
        mkt_pack=MKT_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.purchase_executed is False
    assert c.production_router_verdict == "REJECT"


def test_mo_never_live_executes():
    c = compose_mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk(
        mo={**MO, "stage": "unattended_pack"},
        mkt_pack=MKT_PACK,
        operator_ack=True,
    )
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.mo.live_execution_authorized is False
    assert c.mo.charge_executed is False
    assert c.production_router_verdict == "REJECT"


def test_production_router_reject():
    c = compose_mo_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow29_mpk(
        mo=MO,
        mkt_pack=MKT_PACK,
        operator_ack=True,
    )
    assert c.production_router_verdict == "REJECT"
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.remote_fetched is False
    assert c.pdf_primary is False
