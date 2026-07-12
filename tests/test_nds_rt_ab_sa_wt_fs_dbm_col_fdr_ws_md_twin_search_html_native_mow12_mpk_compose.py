"""Pure tests for ND shadow residual over recursive twin antiek-bench mow12."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from substrate.nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_compose import (
    compose_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk,
    format_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_summary,
)
from tests.test_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_compose import (
    PRESENTATION,
    TWIN,
    WEEKLY_PACK,
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

AUTHORITY = "nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_compose_advisory"


def test_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_mow12_ready():
    c = compose_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk(
        nd_shadow=ND_SHADOW,
        twin_presentation=TWIN_PRESENTATION,
        operator_ack=True,
    )
    assert c.nd_shadow.production_router_verdict == "REJECT"
    assert c.nd_shadow.live_router_authorized is False
    assert c.twin_presentation.pack_ready is True
    assert c.pack_ready is True
    assert c.live_router_authorized is False
    assert c.twin_written is False
    assert c.backlog_mutated is False
    assert c.suite_rewritten is False
    assert c.remote_fetched is False
    assert c.pdf_primary is False
    assert c.draft_written is False
    assert c.production_router_verdict == "REJECT"
    assert c.authority == AUTHORITY
    assert "live_router_authorized=false" in (
        format_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk(
        nd_shadow=ND_SHADOW,
        twin_presentation=TWIN_PRESENTATION,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.twin_written is False
    assert c.backlog_mutated is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    from tests.test_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk_compose import (
        SOURCE_PACK,
        SOURCES,
    )

    c = compose_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk(
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
    assert c.live_router_authorized is False
    assert c.twin_written is False
    assert c.production_router_verdict == "REJECT"


def test_kill_switch_on_still_packs_when_twin_ready():
    c = compose_nds_rt_ab_sa_wt_fs_dbm_col_fdr_ws_md_twin_search_html_native_mow12_mpk(
        nd_shadow={**ND_SHADOW, "kill_switch_on": True},
        twin_presentation=TWIN_PRESENTATION,
        operator_ack=True,
    )
    assert c.nd_shadow.production_router_verdict == "REJECT"
    assert c.nd_shadow.live_router_authorized is False
    assert c.pack_ready is True
    assert c.twin_written is False
