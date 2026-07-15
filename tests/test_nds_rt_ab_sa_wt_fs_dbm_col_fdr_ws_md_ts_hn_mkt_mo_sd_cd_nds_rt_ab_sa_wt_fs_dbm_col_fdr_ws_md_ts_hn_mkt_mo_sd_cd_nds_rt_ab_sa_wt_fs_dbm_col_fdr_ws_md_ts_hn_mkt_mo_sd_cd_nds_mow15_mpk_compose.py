"""Pure tests for ND shadow residual over recursive twin tip mow12."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from substrate.nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk_compose import (
    AUTHORITY,
    compose_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk,
    format_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk_summary,
)
from tests.test_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk_compose import (
    PRESENTATION,
    TWIN,
    WEEKLY_PACK,
)
# Import SOURCE_PACK/SOURCES from the *current* ab tip residual (full nest), not
# a lag moniker — short SOURCE_PACK nests lack draft_pack depth and 422/throw.
# Full tip matches parent rt (full mow14 ab tip moniker); mow13 lag is WRONG.
from tests.test_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow14_mpk_compose import (
    SOURCE_PACK,
    SOURCES,
)

ND_SHADOW = {
    "selected_model_id": "gpt-5.5",
    "nd_recommended_model_id": "claude-opus",
    "kill_switch_on": True,
    "confidence": 0.72,
    "task": "deep_research",
    "inventory_model_ids": ["gpt-5.5", "claude-opus", "mimo"],
}

TWIN_PRESENTATION = {
    "twin": TWIN,
    "presentation": PRESENTATION,
    "weekly_pack": WEEKLY_PACK,
}


def test_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_mow12_ready():
    c = compose_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk(
        nd_shadow=ND_SHADOW,
        twin_presentation=TWIN_PRESENTATION,
        operator_ack=True,
    )
    assert c.pack_ready is True
    assert c.nd_shadow.production_router_verdict == "REJECT"
    assert c.nd_shadow.live_router_authorized is False
    assert c.twin_presentation.pack_ready is True
    assert c.twin_written is False
    assert c.live_router_authorized is False
    assert c.backlog_mutated is False
    assert c.suite_rewritten is False
    assert c.remote_fetched is False
    assert c.pdf_primary is False
    assert c.draft_written is False
    assert c.production_router_verdict == "REJECT"
    assert c.authority == AUTHORITY
    assert "REJECT" in (
        format_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk(
        nd_shadow=ND_SHADOW,
        twin_presentation=TWIN_PRESENTATION,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.twin_written is False
    assert c.live_router_authorized is False
    assert c.backlog_mutated is False
    assert c.remote_fetched is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk(
        nd_shadow=ND_SHADOW,
        twin_presentation={
            **TWIN_PRESENTATION,
            "weekly_pack": {
                **WEEKLY_PACK,
                "source_pack": {
                    **SOURCE_PACK,
                    "sources": {**SOURCES, "session_id": "sess-other"},
                },
            },
        },
        operator_ack=True,
    )
    assert c.twin_presentation.session_aligned is False
    assert c.pack_ready is False
    assert c.twin_written is False
    assert c.live_router_authorized is False
    assert c.backlog_mutated is False
    assert c.remote_fetched is False
    assert c.production_router_verdict == "REJECT"


def test_production_router_remains_reject():
    c = compose_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk(
        nd_shadow=ND_SHADOW,
        twin_presentation=TWIN_PRESENTATION,
        operator_ack=True,
    )
    assert c.production_router_verdict == "REJECT"
    assert c.nd_shadow.production_router_verdict == "REJECT"
    assert c.live_router_authorized is False
    assert c.twin_written is False
    assert c.backlog_mutated is False
    assert c.remote_fetched is False
    assert c.pdf_primary is False
    assert c.draft_written is False
