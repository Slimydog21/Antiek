"""Pure tests for twin-search residual over HTML-native marketplace free mow12."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from substrate.ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow18_mpk_compose import (
    AUTHORITY,
    compose_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow18_mpk,
    format_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow18_mpk_summary,
)
from tests.test_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow18_mpk_compose import (
    HTML_VIEW,
    MARKET_PACK,
)

TWIN_RECORDS = [
    {
        "twin_id": "twin-book-1",
        "parent_asset_id": "book-1",
        "insights": [
            "scaling laws hold under noise in compute-optimal regimes"
        ],
        "questions": ["Where does scaling break under distribution shift?"],
        "source_label": "book-1-twin",
    },
    {
        "twin_id": "twin-arxiv-1",
        "parent_asset_id": "cite-parent-c1",
        "insights": ["Scaling Laws under Noise"],
        "questions": ["How does arxiv residual inform Antiek DR?"],
        "source_label": "arxiv",
    },
]

HTML_PACK = {
    "html_view": HTML_VIEW,
    "market_pack": MARKET_PACK,
}


def test_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_mow12_ready():
    c = compose_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow18_mpk(
        search_query="scaling noise",
        twin_records=TWIN_RECORDS,
        html_pack=HTML_PACK,
        operator_ack=True,
    )
    assert c.hit_count >= 1
    assert c.html_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.remote_index_queried is False
    assert c.twin_written is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.pdf_primary is False
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.production_router_verdict == "REJECT"
    assert c.authority == AUTHORITY
    assert "remote_index_queried=false" in (
        format_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow18_mpk_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow18_mpk(
        search_query="scaling noise",
        twin_records=TWIN_RECORDS,
        html_pack=HTML_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.remote_index_queried is False
    assert c.twin_written is False
    assert c.purchase_executed is False
    assert c.production_router_verdict == "REJECT"


def test_empty_twin_records_blocks():
    c = compose_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow18_mpk(
        search_query="scaling noise",
        twin_records=[],
        html_pack=HTML_PACK,
        operator_ack=True,
    )
    assert c.hit_count == 0
    assert c.pack_ready is False
    assert c.remote_index_queried is False
    assert c.twin_written is False
    assert c.purchase_executed is False
    assert c.production_router_verdict == "REJECT"


def test_nonsense_query_blocks():
    c = compose_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow18_mpk(
        search_query="zzzznonexistenttoken",
        twin_records=TWIN_RECORDS,
        html_pack=HTML_PACK,
        operator_ack=True,
    )
    assert c.hit_count == 0
    assert c.pack_ready is False
    assert c.remote_index_queried is False
    assert c.html_pack.pack_ready is True
    assert c.production_router_verdict == "REJECT"
