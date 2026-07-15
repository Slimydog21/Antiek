"""Pure tests for workstation residual over model-decision mow12."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from substrate.ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_compose import (
    AUTHORITY,
    compose_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk,
    format_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_summary,
)
from tests.test_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_compose import (
    DECISION,
    TWIN_SEARCH_PACK,
)

ITEMS = [
    {
        "record_id": "r1",
        "kind": "insight",
        "text": "scaling holds under noise in compute-optimal regimes",
        "asset_id": "book-1",
        "weight": 0.9,
    },
    {
        "record_id": "r2",
        "kind": "question",
        "text": "Where does scaling break under distribution shift?",
        "asset_id": "book-1",
        "weight": 0.7,
    },
]

DECISION_PACK = {
    "decision": DECISION,
    "twin_search_pack": TWIN_SEARCH_PACK,
}


def test_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_mow12_ready():
    c = compose_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk(
        session_id="sess-1",
        items=ITEMS,
        decision_pack=DECISION_PACK,
        operator_ack=True,
    )
    assert c.records.pack_ready is True
    assert c.records.item_count == 2
    assert c.decision_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.pack_ready is True
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.remote_index_queried is False
    assert c.twin_written is False
    assert c.purchase_executed is False
    assert c.production_router_verdict == "REJECT"
    assert c.authority == AUTHORITY
    assert "record_persisted=false" in (
        format_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk(
        session_id="sess-1",
        items=ITEMS,
        decision_pack=DECISION_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert c.production_router_verdict == "REJECT"


def test_empty_items_blocks():
    c = compose_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk(
        session_id="sess-1",
        items=[],
        decision_pack=DECISION_PACK,
        operator_ack=True,
    )
    assert c.records.item_count == 0
    assert c.records.pack_ready is False
    assert c.pack_ready is False
    assert c.record_persisted is False
    assert c.production_router_verdict == "REJECT"


def test_session_misalign_blocks():
    c = compose_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk(
        session_id="sess-OTHER",
        items=ITEMS,
        decision_pack=DECISION_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.record_persisted is False
    assert c.production_router_verdict == "REJECT"
