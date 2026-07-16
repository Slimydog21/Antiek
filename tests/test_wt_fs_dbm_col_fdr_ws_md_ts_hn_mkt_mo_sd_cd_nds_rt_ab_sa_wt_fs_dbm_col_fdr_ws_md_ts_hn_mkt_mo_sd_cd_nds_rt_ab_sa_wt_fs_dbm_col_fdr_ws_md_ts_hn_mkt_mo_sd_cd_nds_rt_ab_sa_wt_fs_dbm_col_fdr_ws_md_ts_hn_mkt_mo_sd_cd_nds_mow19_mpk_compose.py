"""Pure tests for write-twin residual over fullscreen FDR MD mow12."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 50000:
    sys.setrecursionlimit(50000)

from substrate.wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow19_mpk_compose import (
    AUTHORITY,
    compose_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow19_mpk,
    format_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow19_mpk_summary,
)
from tests.test_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow19_mpk_compose import (
    DRAFT_PACK,
    FULLSCREEN,
)

WRITE = {
    "session_id": "sess-1",
    "draft_id": "draft-1",
    "parent_asset_id": "book-1",
    "twin_slices": [
        {
            "parent_asset_id": "book-1",
            "insights": ["scaling claim holds in compute-optimal regimes"],
            "questions": ["Where does it break?"],
        },
        {
            "parent_asset_id": "book-1-twin-slice-2",
            "insights": ["attention efficiency tradeoffs"],
            "questions": [],
        },
    ],
    "base_draft_html": "<p>Opening paragraph</p>",
    "chase_slots": [
        {
            "slot_id": "s1",
            "question_id": "q1",
            "parent_asset_id": "book-1",
            "status": "completed",
            "findings": ["finding A from chase"],
            "body": "What evidence supports scaling?",
        },
        {
            "slot_id": "s2",
            "question_id": "q2",
            "parent_asset_id": "book-1",
            "status": "completed",
            "findings": ["finding B from chase"],
            "body": "Counter-evidence?",
        },
    ],
    "analysis_kind": "draft_analysis",
    "extra_findings": ["operator synthesis note"],
}

FULLSCREEN_PACK = {
    "fullscreen": FULLSCREEN,
    "draft_pack": DRAFT_PACK,
}


def test_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_mow12_ready():
    c = compose_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow19_mpk(
        write=WRITE,
        fullscreen_pack=FULLSCREEN_PACK,
        operator_ack=True,
    )
    assert c.write.pack_ready is True
    assert c.fullscreen_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.draft_written is False
    assert c.analysis_written is False
    assert c.merge_executed is False
    assert c.live_dispatched is False
    assert c.live_execution_authorized is False
    assert c.twin_written is False
    assert c.production_router_verdict == "REJECT"
    assert c.authority == AUTHORITY
    assert "analysis_written=false" in (
        format_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow19_mpk_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow19_mpk(
        write=WRITE,
        fullscreen_pack=FULLSCREEN_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.analysis_written is False
    assert c.live_dispatched is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow19_mpk(
        write={**WRITE, "session_id": "sess-other"},
        fullscreen_pack=FULLSCREEN_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.production_router_verdict == "REJECT"


def test_parent_mismatch_blocks():
    # chase_slots must share write.parent_asset_id; misalign vs fullscreen parent.
    write = {
        **WRITE,
        "parent_asset_id": "book-other",
        "chase_slots": [
            {**WRITE["chase_slots"][0], "parent_asset_id": "book-other"},
            {**WRITE["chase_slots"][1], "parent_asset_id": "book-other"},
        ],
    }
    c = compose_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow19_mpk(
        write=write,
        fullscreen_pack=FULLSCREEN_PACK,
        operator_ack=True,
    )
    assert c.parent_aligned is False
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.production_router_verdict == "REJECT"
