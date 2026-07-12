"""Pure tests for workstation records over model decision twin search MO weekly src write pack."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from substrate.workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    compose_workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack,
    format_workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_summary,
)
from tests.test_model_decision_twin_search_html_native_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    DECISION,
    TWIN_SEARCH_PACK,
)

ITEMS = [
    {
        "record_id": "r1",
        "kind": "insight",
        "text": "scaling holds under noise in compute-optimal regimes",
        "asset_id": "book-1",
        "weight": 0.9,
    },
    {
        "record_id": "r2",
        "kind": "question",
        "text": "Where does scaling break under distribution shift?",
        "asset_id": "book-1",
        "weight": 0.7,
    },
]

DECISION_PACK = {
    "decision": DECISION,
    "twin_search_pack": TWIN_SEARCH_PACK,
}


def test_workstation_records_model_decision_ready():
    c = compose_workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
        session_id="sess-1",
        items=ITEMS,
        decision_pack=DECISION_PACK,
        operator_ack=True,
    )
    assert c.records.pack_ready is True
    assert c.records.item_count == 2
    assert c.decision_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.pack_ready is True
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.remote_index_queried is False
    assert c.twin_written is False
    assert c.purchase_executed is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_advisory"
    )
    assert "record_persisted=false" in (
        format_workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
        session_id="sess-1",
        items=ITEMS,
        decision_pack=DECISION_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
        session_id="sess-other",
        items=ITEMS,
        decision_pack=DECISION_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert c.production_router_verdict == "REJECT"


def test_empty_records_blocks():
    c = compose_workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
        session_id="sess-1",
        items=[],
        decision_pack=DECISION_PACK,
        operator_ack=True,
    )
    assert c.records.pack_ready is False
    assert c.pack_ready is False
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert c.decision_pack.pack_ready is True
    assert c.production_router_verdict == "REJECT"
