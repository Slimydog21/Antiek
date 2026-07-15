"""Pure tests for collective residual over floating DR tip residual mow12."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from substrate.col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk_compose import (
    AUTHORITY,
    compose_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk,
    format_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk_summary,
)
from tests.test_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk_compose import (
    HIGHLIGHT_LAUNCH,
    RECORD_PACK,
)

MULTISELECT = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "members": [
        {
            "instance_id": "inst-a",
            "parent_asset_id": "book-1",
            "status": "open",
            "highlight": "scaling laws claim",
            "prior_prompt": "What evidence supports the claim?",
            "context": ["card-a"],
        },
        {
            "instance_id": "inst-b",
            "parent_asset_id": "book-1",
            "status": "completed",
            "highlight": "counter-evidence",
            "findings": ["finding-b1"],
        },
    ],
    "selected_instance_ids": ["inst-a", "inst-b"],
    "pack_mode": "cohesive_prompt",
    "cohesive_prompt": "Synthesize A and B as one unit",
    "extra_context": ["operator note"],
}

FLOATING_PACK = {
    "highlight_launch": HIGHLIGHT_LAUNCH,
    "record_pack": RECORD_PACK,
}


def test_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_mow12_ready():
    c = compose_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk(
        multiselect=MULTISELECT,
        floating_pack=FLOATING_PACK,
        operator_ack=True,
    )
    assert c.multiselect.pack_ready is True
    assert c.floating_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.live_dispatched is False
    assert c.pack_dispatched is False
    assert c.merge_executed is False
    assert c.analysis_written is False
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert c.production_router_verdict == "REJECT"
    assert c.authority == AUTHORITY
    assert "live_dispatched=false" in (
        format_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk(
        multiselect=MULTISELECT,
        floating_pack=FLOATING_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.pack_dispatched is False
    assert c.analysis_written is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk(
        multiselect={**MULTISELECT, "session_id": "sess-other"},
        floating_pack=FLOATING_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.pack_dispatched is False
    assert c.production_router_verdict == "REJECT"


def test_parent_mismatch_blocks():
    # Members must share multiselect.parent_asset_id; misalign vs floating_pack parent.
    multi = {
        **MULTISELECT,
        "parent_asset_id": "book-other",
        "members": [
            {**MULTISELECT["members"][0], "parent_asset_id": "book-other"},
            {**MULTISELECT["members"][1], "parent_asset_id": "book-other"},
        ],
    }
    c = compose_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow16_mpk(
        multiselect=multi,
        floating_pack=FLOATING_PACK,
        operator_ack=True,
    )
    assert c.parent_aligned is False
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.production_router_verdict == "REJECT"
