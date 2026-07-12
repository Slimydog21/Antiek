"""Pure tests for fullscreen residual mpk over draft-before-merge mpack tip."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

import pytest

from substrate.fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk_compose import (
    FullscreenOpenDraftBeforeMergeCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpkComposeError,
    compose_fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk,
    format_fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk_summary,
)
from tests.test_draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpack_compose import (
    COLLECTIVE_PACK,
    DRAFT_GATE,
)

FULLSCREEN = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "highlight": "Scaling laws claim from page 12",
    "prompt": "What evidence supports this?",
    "gated": False,
}

DRAFT_PACK = {
    "draft_gate": DRAFT_GATE,
    "collective_pack": COLLECTIVE_PACK,
}


def test_fullscreen_draft_before_merge_collective_ready():
    c = compose_fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk(
        fullscreen=FULLSCREEN,
        draft_pack=DRAFT_PACK,
        operator_ack=True,
    )
    assert c.fullscreen.fullscreen_ready is True
    assert c.draft_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.live_dispatched is False
    assert c.pack_dispatched is False
    assert c.merge_executed is False
    assert c.draft_written is False
    assert c.analysis_written is False
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.remote_index_queried is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk_compose_advisory"
    )
    assert "live_dispatched=false" in (
        format_fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk(
        fullscreen=FULLSCREEN,
        draft_pack=DRAFT_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.merge_executed is False
    assert c.draft_written is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk(
        fullscreen={**FULLSCREEN, "session_id": "sess-other"},
        draft_pack=DRAFT_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.merge_executed is False
    assert c.draft_written is False
    assert c.production_router_verdict == "REJECT"


def test_parent_mismatch_blocks():
    c = compose_fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk(
        fullscreen={**FULLSCREEN, "parent_asset_id": "book-other"},
        draft_pack=DRAFT_PACK,
        operator_ack=True,
    )
    assert c.parent_aligned is False
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.merge_executed is False
    assert c.draft_written is False
    assert c.production_router_verdict == "REJECT"


def test_gated_highlight_fail_closed_throws():
    with pytest.raises(
        FullscreenOpenDraftBeforeMergeCollectiveMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMpkComposeError,
        match="gated/withheld highlight cannot spawn",
    ):
        compose_fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk(
            fullscreen={**FULLSCREEN, "gated": True},
            draft_pack=DRAFT_PACK,
            operator_ack=True,
        )
