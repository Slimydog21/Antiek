"""Pure tests for twin search residual over model decision HTML-native settings pack."""

from __future__ import annotations

from substrate.twin_search_model_decision_html_native_settings_marketplace_compose import (
    compose_twin_search_model_decision_html_native_settings_marketplace,
    format_twin_search_model_decision_html_native_settings_marketplace_summary,
)
from tests.test_model_decision_html_native_settings_marketplace_free_competition_dr_nd_compose import (
    DECISION,
    HTML_NATIVE_PACK,
)

TWIN_RECORDS = [
    {
        "twin_id": "twin-book-1",
        "parent_asset_id": "book-1",
        "insights": [
            "scaling laws hold under noise in compute-optimal regimes"
        ],
        "questions": [
            "Where does scaling break under distribution shift?"
        ],
        "source_label": "book-1-twin",
    },
    {
        "twin_id": "twin-arxiv-1",
        "parent_asset_id": "book-1",
        "insights": ["Scaling Laws under Noise"],
        "questions": ["How does arxiv residual inform Antiek DR?"],
        "source_label": "arxiv",
    },
]

MODEL_DECISION_PACK = {
    "decision": DECISION,
    "html_native_pack": HTML_NATIVE_PACK,
}


def test_twin_search_model_decision_ready():
    c = compose_twin_search_model_decision_html_native_settings_marketplace(
        search_query="scaling noise",
        twin_records=TWIN_RECORDS,
        model_decision_pack=MODEL_DECISION_PACK,
        operator_ack=True,
    )
    assert c.hit_count >= 1
    assert c.model_decision_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.remote_index_queried is False
    assert c.pdf_primary is False
    assert c.twin_written is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.secrets_stored is False
    assert c.live_router_authorized is False
    assert c.live_meter_read is False
    assert c.inventory_mutated is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "twin_search_model_decision_html_native_settings_marketplace_compose_advisory"
    )
    assert "remote_index_queried=false" in (
        format_twin_search_model_decision_html_native_settings_marketplace_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_twin_search_model_decision_html_native_settings_marketplace(
        search_query="scaling noise",
        twin_records=TWIN_RECORDS,
        model_decision_pack=MODEL_DECISION_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.remote_index_queried is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"


def test_zero_hits_blocks():
    c = compose_twin_search_model_decision_html_native_settings_marketplace(
        search_query="zzzznonexistenttoken",
        twin_records=TWIN_RECORDS,
        model_decision_pack=MODEL_DECISION_PACK,
        operator_ack=True,
    )
    assert c.hit_count == 0
    assert c.pack_ready is False
    assert c.remote_index_queried is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"


def test_would_exceed_nested_blocks():
    c = compose_twin_search_model_decision_html_native_settings_marketplace(
        search_query="scaling noise",
        twin_records=TWIN_RECORDS,
        model_decision_pack={
            **MODEL_DECISION_PACK,
            "decision": {
                **DECISION,
                "projected_cost_usd_high": 100,
                "daily_cap_usd": 50,
                "spent_usd": 10,
            },
        },
        operator_ack=True,
    )
    assert c.model_decision_pack.decision.would_exceed is True
    assert c.pack_ready is False
    assert c.remote_index_queried is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"
