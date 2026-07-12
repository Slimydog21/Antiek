"""Pure tests for floating multi-select over model decision free settings pack."""

from __future__ import annotations

from substrate.floating_multiselect_model_decision_twin_search_free_settings_compose import (
    compose_floating_multiselect_model_decision_twin_search_free_settings,
    format_floating_multiselect_model_decision_twin_search_free_settings_summary,
)
from tests.test_model_decision_twin_search_html_native_marketplace_free_settings_compose import (
    DECISION,
    TWIN_SEARCH_PACK,
)

MULTISELECT = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "members": [
        {
            "instance_id": "inst-a",
            "parent_asset_id": "book-1",
            "status": "open",
            "highlight": "scaling laws claim",
            "prior_prompt": "What evidence supports the claim?",
            "context": ["card-a"],
        },
        {
            "instance_id": "inst-b",
            "parent_asset_id": "book-1",
            "status": "completed",
            "highlight": "counter-evidence",
            "findings": ["finding-b1"],
        },
    ],
    "selected_instance_ids": ["inst-a", "inst-b"],
    "pack_mode": "cohesive_prompt",
    "cohesive_prompt": "Synthesize A and B as one unit over twin search + budget",
}

DECISION_PACK = {
    "decision": DECISION,
    "twin_search_pack": TWIN_SEARCH_PACK,
}


def test_floating_multiselect_model_decision_ready():
    c = compose_floating_multiselect_model_decision_twin_search_free_settings(
        multiselect=MULTISELECT,
        decision_pack=DECISION_PACK,
        operator_ack=True,
    )
    assert c.multiselect.pack_ready is True
    assert c.decision_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.live_dispatched is False
    assert c.pack_dispatched is False
    assert c.merge_executed is False
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.remote_index_queried is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "floating_multiselect_model_decision_twin_search_free_settings_compose_advisory"
    )
    assert "live_dispatched=false" in (
        format_floating_multiselect_model_decision_twin_search_free_settings_summary(
            c
        )
    )


def test_operator_ack_false_blocks():
    c = compose_floating_multiselect_model_decision_twin_search_free_settings(
        multiselect=MULTISELECT,
        decision_pack=DECISION_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_floating_multiselect_model_decision_twin_search_free_settings(
        multiselect={**MULTISELECT, "session_id": "sess-other"},
        decision_pack=DECISION_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_would_exceed_blocks():
    c = compose_floating_multiselect_model_decision_twin_search_free_settings(
        multiselect=MULTISELECT,
        decision_pack={
            **DECISION_PACK,
            "decision": {
                **DECISION,
                "projected_cost_usd_high": 100,
                "daily_cap_usd": 50,
                "spent_usd": 10,
            },
        },
        operator_ack=True,
    )
    assert c.decision_pack.decision.would_exceed is True
    assert c.decision_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"
