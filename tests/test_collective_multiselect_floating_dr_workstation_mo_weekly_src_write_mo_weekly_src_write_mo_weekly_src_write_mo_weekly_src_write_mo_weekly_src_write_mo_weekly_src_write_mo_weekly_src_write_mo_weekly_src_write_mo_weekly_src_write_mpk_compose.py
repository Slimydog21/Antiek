"""Pure tests for collective multiselect over floating DR workstation MO weekly src write pack."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from substrate.collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk_compose import (
    compose_collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk,
    format_collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk_summary,
)
from tests.test_floating_dr_workstation_record_model_decision_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    HIGHLIGHT_LAUNCH,
    RECORD_PACK,
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
    "cohesive_prompt": "Synthesize A and B as one unit",
    "extra_context": ["operator note"],
}

FLOATING_PACK = {
    "highlight_launch": HIGHLIGHT_LAUNCH,
    "record_pack": RECORD_PACK,
}


def test_collective_multiselect_floating_dr_ready():
    c = compose_collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk(
        multiselect=MULTISELECT,
        floating_pack=FLOATING_PACK,
        operator_ack=True,
    )
    assert c.multiselect.pack_ready is True
    assert c.floating_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.live_dispatched is False
    assert c.pack_dispatched is False
    assert c.merge_executed is False
    assert c.analysis_written is False
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk_compose_advisory"
    )
    assert "live_dispatched=false" in (
        format_collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk(
        multiselect=MULTISELECT,
        floating_pack=FLOATING_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.pack_dispatched is False
    assert c.analysis_written is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk(
        multiselect={**MULTISELECT, "session_id": "sess-other"},
        floating_pack=FLOATING_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.pack_dispatched is False
    assert c.production_router_verdict == "REJECT"


def test_parent_mismatch_blocks():
    members = [
        {**m, "parent_asset_id": "book-other"} for m in MULTISELECT["members"]
    ]
    c = compose_collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mpk(
        multiselect={
            **MULTISELECT,
            "parent_asset_id": "book-other",
            "members": members,
        },
        floating_pack=FLOATING_PACK,
        operator_ack=True,
    )
    assert c.parent_aligned is False
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.pack_dispatched is False
    assert c.production_router_verdict == "REJECT"
