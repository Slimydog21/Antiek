"""Pure tests for draft-before-merge residual over MO price-ceiling recursive twin pack."""

from __future__ import annotations

from substrate.draft_before_merge_mo_price_ceiling_recursive_twin_compose import (
    compose_draft_before_merge_mo_price_ceiling_recursive_twin,
    format_draft_before_merge_mo_price_ceiling_recursive_twin_summary,
)
from tests.test_mo_price_ceiling_recursive_twin_note_taker_twin_search_compose import (
    MO,
    TWIN_PACK,
)

DRAFT_GATE = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "parent_excerpt": "<p>Scaling Laws parent body</p>",
    "sources": [
        {
            "instance_id": "float-1",
            "parent_asset_id": "book-1",
            "status": "completed",
            "highlight": "scaling laws under noise",
            "findings": ["evidence A holds under noise"],
        },
    ],
    "stage": "draft_only",
}

MO_PACK = {
    "mo": MO,
    "twin_pack": TWIN_PACK,
}


def test_draft_before_merge_mo_price_ready():
    c = compose_draft_before_merge_mo_price_ceiling_recursive_twin(
        draft_gate=DRAFT_GATE,
        mo_pack=MO_PACK,
        operator_ack=True,
    )
    assert c.draft_gate.gate_ready is True
    assert c.mo_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.draft_written is False
    assert c.merge_executed is False
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.twin_written is False
    assert c.remote_index_queried is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "draft_before_merge_mo_price_ceiling_recursive_twin_compose_advisory"
    )
    assert "draft_written=false" in (
        format_draft_before_merge_mo_price_ceiling_recursive_twin_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_draft_before_merge_mo_price_ceiling_recursive_twin(
        draft_gate=DRAFT_GATE,
        mo_pack=MO_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.merge_executed is False
    assert c.live_execution_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_draft_before_merge_mo_price_ceiling_recursive_twin(
        draft_gate={**DRAFT_GATE, "session_id": "sess-other"},
        mo_pack=MO_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.production_router_verdict == "REJECT"


def test_below_ceiling_nested_blocks():
    c = compose_draft_before_merge_mo_price_ceiling_recursive_twin(
        draft_gate=DRAFT_GATE,
        mo_pack={
            **MO_PACK,
            "mo": {
                **MO,
                "approved_ceiling_usd": 1,
                "below_recommend_override": False,
            },
        },
        operator_ack=True,
    )
    assert c.mo_pack.mo.ceiling_approved is False
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.merge_executed is False
    assert c.live_execution_authorized is False
    assert c.production_router_verdict == "REJECT"
