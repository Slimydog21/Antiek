"""Pure tests for model-decision residual over twin-search mow12."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from substrate.md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk_compose import (
    AUTHORITY,
    compose_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk,
    format_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk_summary,
)
from tests.test_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk_compose import (
    HTML_PACK,
    TWIN_RECORDS,
)

DECISION = {
    "selected_model_id": "gpt-5.5",
    "models": [
        {
            "model_id": "gpt-5.5",
            "tier": "frontier",
            "projected_cost_usd_high": 2,
            "projected_cost_usd_low": 1,
        },
        {
            "model_id": "composer-2.5",
            "tier": "workhorse",
            "projected_cost_usd_high": 0.5,
        },
    ],
    "daily_cap_usd": 100,
    "spent_usd": 40,
    "projected_cost_usd_high": 2,
    "projected_cost_usd_low": 1,
    "focus_task": "deep_research",
    "pending_add_model_ids": ["mimo-v2"],
}

TWIN_SEARCH_PACK = {
    "search_query": "scaling noise",
    "twin_records": TWIN_RECORDS,
    "html_pack": HTML_PACK,
}


def test_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_mow12_ready():
    c = compose_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk(
        decision=DECISION,
        twin_search_pack=TWIN_SEARCH_PACK,
        operator_ack=True,
    )
    assert c.decision.decision_ready is True
    assert c.decision.would_exceed is False
    assert c.twin_search_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.live_meter_read is False
    assert c.remote_index_queried is False
    assert c.twin_written is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"
    assert c.authority == AUTHORITY
    assert "live_router_authorized=false" in (
        format_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk(
        decision=DECISION,
        twin_search_pack=TWIN_SEARCH_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.decision.decision_ready is False
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.production_router_verdict == "REJECT"


def test_would_exceed_blocks_pack():
    c = compose_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk(
        decision={
            **DECISION,
            "daily_cap_usd": 10,
            "spent_usd": 9,
            "projected_cost_usd_high": 5,
        },
        twin_search_pack=TWIN_SEARCH_PACK,
        operator_ack=True,
    )
    assert c.decision.would_exceed is True
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.production_router_verdict == "REJECT"


def test_empty_twin_hits_blocks():
    c = compose_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk(
        decision=DECISION,
        twin_search_pack={**TWIN_SEARCH_PACK, "twin_records": []},
        operator_ack=True,
    )
    assert c.twin_search_pack.hit_count == 0
    assert c.twin_search_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.remote_index_queried is False
    assert c.production_router_verdict == "REJECT"
