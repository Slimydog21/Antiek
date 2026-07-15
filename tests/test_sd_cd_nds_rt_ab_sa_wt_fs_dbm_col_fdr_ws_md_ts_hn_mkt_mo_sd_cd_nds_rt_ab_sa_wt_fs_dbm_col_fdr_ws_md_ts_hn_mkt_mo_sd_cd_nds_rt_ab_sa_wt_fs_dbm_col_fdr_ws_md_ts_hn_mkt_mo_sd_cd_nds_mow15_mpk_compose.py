"""Pure tests for settings residual over competition DR ND shadow mow12."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from substrate.sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk_compose import (
    AUTHORITY,
    compose_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk,
    format_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk_summary,
)
from tests.test_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk_compose import (
    COMPETITION,
    ND_PACK,
)
from tests.test_settings_add_model_bench_decision_compose import (
    DECISION_MODELS,
    MODELS,
    events_deep_research,
)

SETTINGS = {
    "models": MODELS,
    "pending_add_model_ids": ["mimo-v2"],
    "action": "preview",
    "week_id": "2026-W28",
    "focus_task": "deep_research",
    "events": events_deep_research(),
    "decision_models": DECISION_MODELS,
    "selected_model_id": "gpt-5.5",
    "daily_cap_usd": 20,
    "spent_usd": 5,
    "projected_cost_usd_high": 0.5,
    "projected_cost_usd_low": 0.2,
    "existing_tasks": ["deep_research", "twin_notes"],
}

COMPETITION_PACK = {
    "competition": COMPETITION,
    "nd_pack": ND_PACK,
}


def test_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_mow12_ready():
    c = compose_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk(
        settings=SETTINGS,
        competition_pack=COMPETITION_PACK,
        operator_ack=True,
    )
    assert c.settings.pack_ready is True
    assert c.competition_pack.pack_ready is True
    assert c.week_aligned is True
    assert c.session_aligned is True
    assert c.pack_ready is True
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.live_router_authorized is False
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.backlog_mutated is False
    assert c.twin_written is False
    assert c.production_router_verdict == "REJECT"
    assert c.authority == AUTHORITY
    assert "secrets_stored=false" in (
        format_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk(
        settings=SETTINGS,
        competition_pack=COMPETITION_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_week_mismatch_blocks():
    c = compose_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk(
        settings={**SETTINGS, "week_id": "2026-W99"},
        competition_pack=COMPETITION_PACK,
        operator_ack=True,
    )
    assert c.week_aligned is False
    assert c.pack_ready is False
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_ts_hn_mkt_mo_sd_cd_nds_mow15_mpk(
        settings=SETTINGS,
        competition_pack={
            **COMPETITION_PACK,
            "competition": {**COMPETITION, "session_id": "sess-other"},
        },
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.secrets_stored is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"
