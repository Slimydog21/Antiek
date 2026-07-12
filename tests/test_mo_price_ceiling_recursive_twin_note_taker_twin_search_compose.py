"""Pure tests for MO price-ceiling residual over recursive twin note-taker twin search pack."""

from __future__ import annotations

from substrate.mo_price_ceiling_recursive_twin_note_taker_twin_search_compose import (
    compose_mo_price_ceiling_recursive_twin_note_taker_twin_search,
    format_mo_price_ceiling_recursive_twin_note_taker_twin_search_summary,
)
from tests.test_recursive_twin_note_taker_twin_search_model_decision_compose import (
    TWIN,
    TWIN_SEARCH_PACK,
)

MO = {
    "operator_id": "op-1",
    "work_minutes": 120,
    "goals": [
        {"goal_id": "g1", "title": "Map scaling literature"},
        {"goal_id": "g2", "title": "Synthesize open problems"},
    ],
    "usd_per_hour": 25,
    # ≥ recommended: rate * hours * sqrt(goals) ≈ 25 * 2 * 1.414 ≈ 70.71
    "approved_ceiling_usd": 500,
    "price_ceiling_ack": True,
    "unattended_ack": True,
    "spend_consent": True,
    "stage": "unattended_pack",
}

TWIN_PACK = {
    "twin": TWIN,
    "twin_search_pack": TWIN_SEARCH_PACK,
}


def test_mo_price_ceiling_recursive_twin_ready():
    c = compose_mo_price_ceiling_recursive_twin_note_taker_twin_search(
        mo=MO,
        twin_pack=TWIN_PACK,
        operator_ack=True,
    )
    assert c.mo.pack_ready is True
    assert c.mo.ceiling_approved is True
    assert c.mo.live_execution_authorized is False
    assert c.mo.charge_executed is False
    assert c.twin_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.twin_written is False
    assert c.remote_index_queried is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "mo_price_ceiling_recursive_twin_note_taker_twin_search_compose_advisory"
    )
    assert "live_execution_authorized=false" in (
        format_mo_price_ceiling_recursive_twin_note_taker_twin_search_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_mo_price_ceiling_recursive_twin_note_taker_twin_search(
        mo=MO,
        twin_pack=TWIN_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.twin_written is False
    assert c.production_router_verdict == "REJECT"


def test_below_recommended_ceiling_blocks():
    c = compose_mo_price_ceiling_recursive_twin_note_taker_twin_search(
        mo={
            **MO,
            "approved_ceiling_usd": 1,
            "below_recommend_override": False,
        },
        twin_pack=TWIN_PACK,
        operator_ack=True,
    )
    assert c.mo.ceiling_approved is False
    assert c.mo.pack_ready is False
    assert c.pack_ready is False
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.production_router_verdict == "REJECT"


def test_zero_hits_nested_blocks():
    c = compose_mo_price_ceiling_recursive_twin_note_taker_twin_search(
        mo=MO,
        twin_pack={
            **TWIN_PACK,
            "twin_search_pack": {
                **TWIN_SEARCH_PACK,
                "search_query": "zzzznonexistenttoken",
            },
        },
        operator_ack=True,
    )
    assert c.twin_pack.twin_search_pack.hit_count == 0
    assert c.pack_ready is False
    assert c.live_execution_authorized is False
    assert c.twin_written is False
    assert c.remote_index_queried is False
    assert c.production_router_verdict == "REJECT"
