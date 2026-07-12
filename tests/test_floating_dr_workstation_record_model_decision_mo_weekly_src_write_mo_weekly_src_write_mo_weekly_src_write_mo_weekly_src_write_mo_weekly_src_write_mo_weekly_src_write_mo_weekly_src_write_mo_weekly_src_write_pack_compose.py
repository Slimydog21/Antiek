"""Pure tests for floating DR over workstation record model decision MO weekly src write pack."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

import pytest

from substrate.floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    FloatingDrWorkstationRecordModelDecisionMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError,
    compose_floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack,
    format_floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_summary,
)
from tests.test_workstation_record_model_decision_twin_search_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    DECISION_PACK,
    ITEMS,
)

HIGHLIGHT_LAUNCH = {
    "parent_asset_id": "book-1",
    "highlight": "scaling laws under noise",
    "gated": False,
    "preferred_view_mode": "floating",
    "would_exceed": False,
    "selected_model_id": "gpt-5.5",
    "source_families": ["arxiv", "substack"],
}

RECORD_PACK = {
    "session_id": "sess-1",
    "items": ITEMS,
    "decision_pack": DECISION_PACK,
}


def test_floating_dr_workstation_record_ready():
    c = compose_floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
        highlight_launch=HIGHLIGHT_LAUNCH,
        record_pack=RECORD_PACK,
        operator_ack=True,
    )
    assert c.highlight_launch.launch_ready is True
    assert c.highlight_launch.live_dispatched is False
    assert c.highlight_launch.merge_executed is False
    assert c.record_pack.pack_ready is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.live_dispatched is False
    assert c.merge_executed is False
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_advisory"
    )
    assert "live_dispatched=false" in (
        format_floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
        highlight_launch=HIGHLIGHT_LAUNCH,
        record_pack=RECORD_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.merge_executed is False
    assert c.record_persisted is False
    assert c.production_router_verdict == "REJECT"


def test_parent_mismatch_blocks():
    c = compose_floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
        highlight_launch={**HIGHLIGHT_LAUNCH, "parent_asset_id": "book-other"},
        record_pack=RECORD_PACK,
        operator_ack=True,
    )
    assert c.parent_aligned is False
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.merge_executed is False
    assert c.production_router_verdict == "REJECT"


def test_gated_highlight_fail_closed():
    with pytest.raises(
        FloatingDrWorkstationRecordModelDecisionMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackComposeError, match="gated"
    ):
        compose_floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
            highlight_launch={**HIGHLIGHT_LAUNCH, "gated": True},
            record_pack=RECORD_PACK,
            operator_ack=True,
        )
