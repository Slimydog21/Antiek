"""Pure tests for antiek-bench residual over source-attach FDR MD mow12."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 50000:
    sys.setrecursionlimit(50000)

from substrate.ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow26_mpk_compose import (
    AUTHORITY,
    compose_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow26_mpk,
    format_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow26_mpk_summary,
)
from tests.test_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow25_mpk_compose import (
    SOURCES,
    WRITE_PACK,
)

WEEKLY_LEARN = {
    "week_id": "2026-W28",
    "min_events_per_task": 2,
    "events": [
        {
            "event_id": "e1",
            "task": "deep_research",
            "model_id": "gpt-5",
            "outcome": "failed",
        },
        {
            "event_id": "e2",
            "task": "deep_research",
            "model_id": "gpt-5",
            "outcome": "failed",
        },
        {
            "event_id": "e3",
            "task": "twin_notes",
            "model_id": "claude",
            "outcome": "worked",
        },
        {
            "event_id": "e4",
            "task": "twin_notes",
            "model_id": "claude",
            "outcome": "worked",
        },
    ],
}

SOURCE_PACK = {
    "sources": SOURCES,
    "write_pack": WRITE_PACK,
}


def test_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_mow12_ready():
    c = compose_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow26_mpk(
        weekly_learn=WEEKLY_LEARN,
        source_pack=SOURCE_PACK,
        operator_ack=True,
    )
    assert c.learn_ready is True
    assert c.weekly_learn.learn_ready is True
    assert c.weekly_learn.proposal_count >= 1
    assert c.source_pack.pack_ready is True
    assert c.attach_ready is True
    assert c.session_aligned is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.backlog_mutated is False
    assert c.store_mutated is False
    assert c.suite_rewritten is False
    assert c.remote_fetched is False
    assert c.pdf_view_authorized is False
    assert c.pdf_primary is False
    assert c.draft_written is False
    assert c.analysis_written is False
    assert c.twin_written is False
    assert c.live_dispatched is False
    assert c.production_router_verdict == "REJECT"
    assert c.authority == AUTHORITY
    assert "backlog_mutated=false" in (
        format_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow26_mpk_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow26_mpk(
        weekly_learn=WEEKLY_LEARN,
        source_pack=SOURCE_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.backlog_mutated is False
    assert c.remote_fetched is False
    assert c.pdf_primary is False
    assert c.draft_written is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow26_mpk(
        weekly_learn=WEEKLY_LEARN,
        source_pack={
            **SOURCE_PACK,
            "sources": {**SOURCES, "session_id": "sess-other"},
        },
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.backlog_mutated is False
    assert c.remote_fetched is False
    assert c.production_router_verdict == "REJECT"


def test_parent_mismatch_blocks():
    c = compose_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow26_mpk(
        weekly_learn=WEEKLY_LEARN,
        source_pack={
            **SOURCE_PACK,
            "sources": {**SOURCES, "parent_asset_id": "book-other"},
        },
        operator_ack=True,
    )
    assert c.parent_aligned is False
    assert c.pack_ready is False
    assert c.backlog_mutated is False
    assert c.remote_fetched is False
    assert c.production_router_verdict == "REJECT"
