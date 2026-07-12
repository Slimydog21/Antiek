"""Pure tests for model decision over twin search HTML-native marketplace pack."""

from __future__ import annotations

from substrate.model_decision_twin_search_html_native_marketplace_compose import (
    compose_model_decision_twin_search_html_native_marketplace,
    format_model_decision_twin_search_html_native_marketplace_summary,
)
from tests.test_twin_search_html_native_recursive_twin_marketplace_compose import (
    HTML_PACK,
    SEARCH_TWIN_RECORDS,
)

DECISION = {
    "selected_model_id": "gpt-5.5",
    "models": [
        {
            "model_id": "gpt-5.5",
            "tier": "frontier",
            "projected_cost_usd_high": 2,
            "projected_cost_usd_low": 1,
        },
        {
            "model_id": "composer-2.5",
            "tier": "workhorse",
            "projected_cost_usd_high": 0.5,
        },
    ],
    "daily_cap_usd": 50,
    "spent_usd": 10,
    "projected_cost_usd_high": 2,
    "projected_cost_usd_low": 1,
    "focus_task": "deep_research",
    "pending_add_model_ids": ["mimo-v2"],
}

TWIN_SEARCH_PACK = {
    "search_query": "scaling noise",
    "twin_records": SEARCH_TWIN_RECORDS,
    "html_pack": HTML_PACK,
}


def test_model_decision_twin_search_ready():
    c = compose_model_decision_twin_search_html_native_marketplace(
        decision=DECISION,
        twin_search_pack=TWIN_SEARCH_PACK,
        operator_ack=True,
    )
    assert c.decision.decision_ready is True
    assert c.decision.would_exceed is False
    assert c.twin_search_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.live_meter_read is False
    assert c.remote_index_queried is False
    assert c.pdf_primary is False
    assert c.twin_written is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.inventory_mutated is False
    assert c.suite_rewritten is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "model_decision_twin_search_html_native_marketplace_compose_advisory"
    )
    assert "live_router_authorized=false" in (
        format_model_decision_twin_search_html_native_marketplace_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_model_decision_twin_search_html_native_marketplace(
        decision=DECISION,
        twin_search_pack=TWIN_SEARCH_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.remote_index_queried is False
    assert c.production_router_verdict == "REJECT"


def test_would_exceed_blocks():
    c = compose_model_decision_twin_search_html_native_marketplace(
        decision={
            **DECISION,
            "projected_cost_usd_high": 100,
            "daily_cap_usd": 50,
            "spent_usd": 10,
        },
        twin_search_pack=TWIN_SEARCH_PACK,
        operator_ack=True,
    )
    assert c.decision.would_exceed is True
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.remote_index_queried is False
    assert c.production_router_verdict == "REJECT"


def test_zero_hits_blocks():
    c = compose_model_decision_twin_search_html_native_marketplace(
        decision=DECISION,
        twin_search_pack={
            **TWIN_SEARCH_PACK,
            "search_query": "zzzznonexistenttoken",
        },
        operator_ack=True,
    )
    assert c.twin_search_pack.hit_count == 0
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.remote_index_queried is False
    assert c.production_router_verdict == "REJECT"
