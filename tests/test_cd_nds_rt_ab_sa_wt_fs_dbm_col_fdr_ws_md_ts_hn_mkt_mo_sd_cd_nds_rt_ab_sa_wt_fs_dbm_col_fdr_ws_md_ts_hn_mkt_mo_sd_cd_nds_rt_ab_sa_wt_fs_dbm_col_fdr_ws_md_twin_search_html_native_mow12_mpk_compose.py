"""Pure tests for competition DR residual over ND shadow recursive twin mow12."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from substrate.cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_compose import (
    AUTHORITY,
    compose_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk,
    format_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_summary,
)
from tests.test_competition_dr_quality_source_pack_compose import CITATIONS, DECISIONS
from tests.test_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_compose import (
    ND_SHADOW,
    TWIN_PRESENTATION,
)

COMPETITION = {
    "session_id": "sess-1",
    "competitor_decisions": DECISIONS,
    "requested_families": ["arxiv", "substack"],
    "citations": CITATIONS,
    "quality_overall": 0.8,
    "quality_floor": 0.5,
    "would_exceed": False,
}

ND_PACK = {
    "nd_shadow": ND_SHADOW,
    "twin_presentation": TWIN_PRESENTATION,
}


def test_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_mow12_ready():
    c = compose_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk(
        competition=COMPETITION,
        nd_pack=ND_PACK,
        operator_ack=True,
    )
    assert c.competition.pack_ready is True
    assert c.nd_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.pack_ready is True
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.backlog_mutated is False
    assert c.live_router_authorized is False
    assert c.twin_written is False
    assert c.production_router_verdict == "REJECT"
    assert c.authority == AUTHORITY
    assert "live_dispatch_authorized=false" in (
        format_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk(
        competition=COMPETITION,
        nd_pack=ND_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk(
        competition={**COMPETITION, "session_id": "sess-other"},
        nd_pack=ND_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.live_dispatch_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_quality_below_floor_blocks():
    c = compose_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk(
        competition={
            **COMPETITION,
            "quality_overall": 0.1,
            "quality_floor": 0.5,
        },
        nd_pack=ND_PACK,
        operator_ack=True,
    )
    assert c.competition.pack_ready is False
    assert c.pack_ready is False
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.production_router_verdict == "REJECT"
