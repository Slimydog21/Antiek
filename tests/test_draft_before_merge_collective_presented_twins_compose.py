"""Pure tests for draft-before-merge + collective presented twins pack."""

from __future__ import annotations

import pytest

from substrate.draft_before_merge_collective_presented_twins_compose import (
    DraftBeforeMergeCollectivePresentedTwinsComposeError,
    compose_draft_before_merge_collective_presented_twins,
    format_draft_before_merge_collective_presented_twins_summary,
)
from tests.test_collective_presented_twins_paid_nd_compose import (
    COLLECTIVE,
    PAID_ND,
)

DRAFT_GATE = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "parent_excerpt": "<p>Parent body on scaling laws</p>",
    "sources": [
        {
            "instance_id": "float-1",
            "parent_asset_id": "book-1",
            "status": "completed",
            "highlight": "key claim",
            "findings": ["evidence A"],
        }
    ],
    "stage": "draft_only",
}

COLLECTIVE_PACK = {
    "collective": COLLECTIVE,
    "paid_nd": PAID_ND,
}


def test_draft_before_merge_collective_ready():
    c = compose_draft_before_merge_collective_presented_twins(
        draft_gate=DRAFT_GATE,
        collective_pack=COLLECTIVE_PACK,
        operator_ack=True,
    )
    assert c.draft_gate.gate_ready is True
    assert c.collective_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.draft_written is False
    assert c.merge_executed is False
    assert c.live_dispatched is False
    assert c.purchase_executed is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "draft_before_merge_collective_presented_twins_compose_advisory"
    )
    assert "draft_written=false" in (
        format_draft_before_merge_collective_presented_twins_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_draft_before_merge_collective_presented_twins(
        draft_gate=DRAFT_GATE,
        collective_pack=COLLECTIVE_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.merge_executed is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_draft_before_merge_collective_presented_twins(
        draft_gate={**DRAFT_GATE, "session_id": "sess-other"},
        collective_pack=COLLECTIVE_PACK,
        operator_ack=True,
    )
    assert c.pack_ready is False
    assert c.merge_executed is False
    assert c.live_dispatched is False


def test_promote_stage_still_never_merges():
    c = compose_draft_before_merge_collective_presented_twins(
        draft_gate={
            **DRAFT_GATE,
            "stage": "promote_full_merge",
            "full_merge_ack": True,
        },
        collective_pack=COLLECTIVE_PACK,
        operator_ack=True,
    )
    assert c.draft_gate.merge_executed is False
    assert c.merge_executed is False
    assert c.draft_written is False
    assert c.production_router_verdict == "REJECT"


def test_require_operator_ack_type():
    with pytest.raises(DraftBeforeMergeCollectivePresentedTwinsComposeError):
        compose_draft_before_merge_collective_presented_twins(
            draft_gate=DRAFT_GATE,
            collective_pack=COLLECTIVE_PACK,
            operator_ack="yes",  # type: ignore[arg-type]
        )
