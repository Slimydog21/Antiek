"""Pure tests for recursive twin note-taker over twin search model decision pack."""

from __future__ import annotations

from substrate.recursive_twin_note_taker_twin_search_model_decision_compose import (
    compose_recursive_twin_note_taker_twin_search_model_decision,
    format_recursive_twin_note_taker_twin_search_model_decision_summary,
)
from tests.test_twin_search_model_decision_html_native_settings_marketplace_compose import (
    MODEL_DECISION_PACK,
    TWIN_RECORDS,
)

TWIN = {
    "parent_asset_id": "book-1",
    "source_excerpt": (
        "<p>Scaling laws hold under noise in compute-optimal regimes.</p>"
    ),
    "focus_questions": [
        "Where does scaling break under distribution shift?",
    ],
    "existing_twin_asset_id": "twin-book-1",
}

TWIN_SEARCH_PACK = {
    "search_query": "scaling noise",
    "twin_records": TWIN_RECORDS,
    "model_decision_pack": MODEL_DECISION_PACK,
}


def test_recursive_twin_note_taker_twin_search_ready():
    c = compose_recursive_twin_note_taker_twin_search_model_decision(
        twin=TWIN,
        twin_search_pack=TWIN_SEARCH_PACK,
        operator_ack=True,
    )
    assert c.twin.twin_propose_ready is True
    assert c.twin_search_pack.pack_ready is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.twin_written is False
    assert c.prompts_injected is False
    assert c.live_dispatch_authorized is False
    assert c.remote_index_queried is False
    assert c.pdf_primary is False
    assert c.purchase_executed is False
    assert c.secrets_stored is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "recursive_twin_note_taker_twin_search_model_decision_compose_advisory"
    )
    assert "twin_written=false" in (
        format_recursive_twin_note_taker_twin_search_model_decision_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_recursive_twin_note_taker_twin_search_model_decision(
        twin=TWIN,
        twin_search_pack=TWIN_SEARCH_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.twin_written is False
    assert c.remote_index_queried is False
    assert c.production_router_verdict == "REJECT"


def test_parent_misalignment_blocks():
    c = compose_recursive_twin_note_taker_twin_search_model_decision(
        twin={**TWIN, "parent_asset_id": "other-book"},
        twin_search_pack=TWIN_SEARCH_PACK,
        operator_ack=True,
    )
    assert c.parent_aligned is False
    assert c.pack_ready is False
    assert c.twin_written is False
    assert c.production_router_verdict == "REJECT"


def test_zero_hits_nested_blocks():
    c = compose_recursive_twin_note_taker_twin_search_model_decision(
        twin=TWIN,
        twin_search_pack={
            **TWIN_SEARCH_PACK,
            "search_query": "zzzznonexistenttoken",
        },
        operator_ack=True,
    )
    assert c.twin_search_pack.hit_count == 0
    assert c.pack_ready is False
    assert c.twin_written is False
    assert c.remote_index_queried is False
    assert c.production_router_verdict == "REJECT"
