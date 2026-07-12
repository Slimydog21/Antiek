"""Pure tests for write twin collective over fullscreen draft-before-merge pack."""

from __future__ import annotations

from substrate.write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_pack_compose import (
    compose_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_pack,
    format_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_pack_summary,
)
from tests.test_fullscreen_open_draft_before_merge_collective_mo_weekly_src_write_pack_compose import (
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


def test_write_twin_collective_fullscreen_draft_before_merge_ready():
    c = compose_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_pack(
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
    assert c.charge_executed is False
    assert c.twin_written is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_pack_compose_advisory"
    )
    assert "analysis_written=false" in (
        format_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_pack_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_pack(
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
    c = compose_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_pack(
        write={**WRITE, "session_id": "sess-other"},
        fullscreen_pack=FULLSCREEN_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.production_router_verdict == "REJECT"


def test_parent_mismatch_blocks():
    c = compose_write_mode_twin_fullscreen_draft_collective_mo_weekly_src_write_pack(
        write={
            **WRITE,
            "parent_asset_id": "book-other",
            "twin_slices": [
                {
                    **WRITE["twin_slices"][0],
                    "parent_asset_id": "book-other",
                },
                {
                    **WRITE["twin_slices"][1],
                    "parent_asset_id": "book-other-slice-2",
                },
            ],
            "chase_slots": [
                {**s, "parent_asset_id": "book-other"} for s in WRITE["chase_slots"]
            ],
        },
        fullscreen_pack=FULLSCREEN_PACK,
        operator_ack=True,
    )
    assert c.parent_aligned is False
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.analysis_written is False
    assert c.live_dispatched is False
    assert c.production_router_verdict == "REJECT"
