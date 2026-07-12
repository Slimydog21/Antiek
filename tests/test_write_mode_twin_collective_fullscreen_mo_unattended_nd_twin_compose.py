"""Pure tests for write twin collective over fullscreen MO unattended ND twin."""

from __future__ import annotations

from substrate.write_mode_twin_collective_fullscreen_mo_unattended_nd_twin_compose import (
    compose_write_mode_twin_collective_fullscreen_mo_unattended_nd_twin,
    format_write_mode_twin_collective_fullscreen_mo_unattended_nd_twin_summary,
)
from tests.test_fullscreen_mo_unattended_draft_multiselect_nd_twin_compose import (
    FULLSCREEN,
    MO_PACK,
)

WRITE = {
    "session_id": "sess-1",
    "draft_id": "draft-1",
    "parent_asset_id": "book-1",
    "twin_slices": [
        {
            "parent_asset_id": "asset-1",
            "insights": ["scaling claim holds in compute-optimal regimes"],
            "questions": ["Where does it break?"],
        },
        {
            "parent_asset_id": "asset-2",
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
}

FULLSCREEN_PACK = {
    "fullscreen": FULLSCREEN,
    "mo_pack": MO_PACK,
}


def test_write_twin_collective_fullscreen_mo_nd_twin_ready():
    c = compose_write_mode_twin_collective_fullscreen_mo_unattended_nd_twin(
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
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.remote_index_queried is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "write_mode_twin_collective_fullscreen_mo_unattended_nd_twin_compose_advisory"
    )
    assert "draft_written=false" in (
        format_write_mode_twin_collective_fullscreen_mo_unattended_nd_twin_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_write_mode_twin_collective_fullscreen_mo_unattended_nd_twin(
        write=WRITE,
        fullscreen_pack=FULLSCREEN_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.analysis_written is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_write_mode_twin_collective_fullscreen_mo_unattended_nd_twin(
        write={**WRITE, "session_id": "sess-other"},
        fullscreen_pack=FULLSCREEN_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.analysis_written is False
    assert c.production_router_verdict == "REJECT"


def test_spend_consent_false_blocks():
    c = compose_write_mode_twin_collective_fullscreen_mo_unattended_nd_twin(
        write=WRITE,
        fullscreen_pack={
            "fullscreen": FULLSCREEN,
            "mo_pack": {
                "mo": {**MO_PACK["mo"], "spend_consent": False},
                "draft_pack": MO_PACK["draft_pack"],
            },
        },
        operator_ack=True,
    )
    assert c.fullscreen_pack.mo_pack.mo.unattended_package_ready is False
    assert c.fullscreen_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.analysis_written is False
    assert c.live_execution_authorized is False
    assert c.production_router_verdict == "REJECT"
