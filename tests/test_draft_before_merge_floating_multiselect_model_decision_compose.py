"""Pure tests for draft-before-merge over floating multi-select model decision pack."""

from __future__ import annotations

from substrate.draft_before_merge_floating_multiselect_model_decision_compose import (
    compose_draft_before_merge_floating_multiselect_model_decision,
    format_draft_before_merge_floating_multiselect_model_decision_summary,
)
from tests.test_floating_multiselect_model_decision_twin_search_free_settings_compose import (
    DECISION_PACK,
    MULTISELECT,
)

DRAFT_GATE = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "parent_excerpt": "<p>Parent scaling laws body</p>",
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

MULTI_PACK = {
    "multiselect": MULTISELECT,
    "decision_pack": DECISION_PACK,
}


def test_draft_before_merge_floating_multiselect_ready():
    c = compose_draft_before_merge_floating_multiselect_model_decision(
        draft_gate=DRAFT_GATE,
        multi_pack=MULTI_PACK,
        operator_ack=True,
    )
    assert c.draft_gate.gate_ready is True
    assert c.multi_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.draft_written is False
    assert c.merge_executed is False
    assert c.live_dispatched is False
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.remote_index_queried is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "draft_before_merge_floating_multiselect_model_decision_compose_advisory"
    )
    assert "merge_executed=false" in (
        format_draft_before_merge_floating_multiselect_model_decision_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_draft_before_merge_floating_multiselect_model_decision(
        draft_gate=DRAFT_GATE,
        multi_pack=MULTI_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.merge_executed is False
    assert c.live_dispatched is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_draft_before_merge_floating_multiselect_model_decision(
        draft_gate={**DRAFT_GATE, "session_id": "sess-other"},
        multi_pack=MULTI_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.merge_executed is False
    assert c.production_router_verdict == "REJECT"


def test_would_exceed_blocks():
    from tests.test_floating_multiselect_model_decision_twin_search_free_settings_compose import (
        DECISION,
    )

    c = compose_draft_before_merge_floating_multiselect_model_decision(
        draft_gate=DRAFT_GATE,
        multi_pack={
            **MULTI_PACK,
            "decision_pack": {
                **DECISION_PACK,
                "decision": {
                    **DECISION,
                    "projected_cost_usd_high": 100,
                    "daily_cap_usd": 50,
                    "spent_usd": 10,
                },
            },
        },
        operator_ack=True,
    )
    assert c.multi_pack.decision_pack.decision.would_exceed is True
    assert c.multi_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.merge_executed is False
    assert c.production_router_verdict == "REJECT"
