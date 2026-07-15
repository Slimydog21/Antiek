"""Pure tests for draft-before-merge residual over collective floating DR tip residual mow12."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from substrate.dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk_compose import (
    AUTHORITY,
    compose_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk,
    format_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk_summary,
)
from tests.test_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk_compose import (
    FLOATING_PACK,
    MULTISELECT,
)

DRAFT_GATE = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "parent_excerpt": "<p>Parent body on scaling laws</p>",
    "sources": [
        {
            "instance_id": "inst-a",
            "parent_asset_id": "book-1",
            "status": "completed",
            "highlight": "scaling laws claim",
            "findings": ["evidence A"],
        },
        {
            "instance_id": "inst-b",
            "parent_asset_id": "book-1",
            "status": "completed",
            "highlight": "counter-evidence",
            "findings": ["finding-b1"],
        },
    ],
    "stage": "draft_only",
}

COLLECTIVE_PACK = {
    "multiselect": MULTISELECT,
    "floating_pack": FLOATING_PACK,
}


def test_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_mow12_ready():
    c = compose_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk(
        draft_gate=DRAFT_GATE,
        collective_pack=COLLECTIVE_PACK,
        operator_ack=True,
    )
    assert c.draft_gate.gate_ready is True
    assert c.collective_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.draft_written is False
    assert c.merge_executed is False
    assert c.live_dispatched is False
    assert c.pack_dispatched is False
    assert c.analysis_written is False
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert c.production_router_verdict == "REJECT"
    assert c.authority == AUTHORITY
    assert "merge_executed=false" in (
        format_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk(
        draft_gate=DRAFT_GATE,
        collective_pack=COLLECTIVE_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.merge_executed is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk(
        draft_gate={**DRAFT_GATE, "session_id": "sess-other"},
        collective_pack=COLLECTIVE_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.merge_executed is False
    assert c.production_router_verdict == "REJECT"


def test_parent_mismatch_blocks():
    # Sources must share draft_gate.parent_asset_id; misalign vs collective parent.
    gate = {
        **DRAFT_GATE,
        "parent_asset_id": "book-other",
        "sources": [
            {**DRAFT_GATE["sources"][0], "parent_asset_id": "book-other"},
            {**DRAFT_GATE["sources"][1], "parent_asset_id": "book-other"},
        ],
    }
    c = compose_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk(
        draft_gate=gate,
        collective_pack=COLLECTIVE_PACK,
        operator_ack=True,
    )
    assert c.parent_aligned is False
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.production_router_verdict == "REJECT"
