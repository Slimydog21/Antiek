"""Pure tests for draft-before-merge over collective multiselect floating DR MO weekly src write pack."""

from __future__ import annotations

import sys

if sys.getrecursionlimit() < 10000:
    sys.setrecursionlimit(10000)

from substrate.draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    compose_draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack,
    format_draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_summary,
)
from tests.test_collective_multiselect_floating_dr_workstation_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose import (
    FLOATING_PACK,
    MULTISELECT,
)

DRAFT_GATE = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "parent_excerpt": "<p>Parent body on scaling laws</p>",
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

COLLECTIVE_PACK = {
    "multiselect": MULTISELECT,
    "floating_pack": FLOATING_PACK,
}


def test_draft_before_merge_collective_multiselect_ready():
    c = compose_draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
        draft_gate=DRAFT_GATE,
        collective_pack=COLLECTIVE_PACK,
        operator_ack=True,
    )
    assert c.draft_gate.gate_ready is True
    assert c.collective_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.draft_written is False
    assert c.merge_executed is False
    assert c.live_dispatched is False
    assert c.pack_dispatched is False
    assert c.analysis_written is False
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.remote_index_queried is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_compose_advisory"
    )
    assert "merge_executed=false" in (
        format_draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack_summary(
            c
        )
    )


def test_operator_ack_false_blocks():
    c = compose_draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
        draft_gate=DRAFT_GATE,
        collective_pack=COLLECTIVE_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.merge_executed is False
    assert c.live_dispatched is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
        draft_gate={**DRAFT_GATE, "session_id": "sess-other"},
        collective_pack=COLLECTIVE_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.merge_executed is False
    assert c.live_dispatched is False
    assert c.production_router_verdict == "REJECT"


def test_parent_mismatch_blocks():
    sources = [
        {**s, "parent_asset_id": "book-other"} for s in DRAFT_GATE["sources"]
    ]
    c = compose_draft_before_merge_collective_floating_dr_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_mo_weekly_src_write_pack(
        draft_gate={
            **DRAFT_GATE,
            "parent_asset_id": "book-other",
            "sources": sources,
        },
        collective_pack=COLLECTIVE_PACK,
        operator_ack=True,
    )
    assert c.parent_aligned is False
    assert c.pack_ready is False
    assert c.draft_written is False
    assert c.merge_executed is False
    assert c.live_dispatched is False
    assert c.production_router_verdict == "REJECT"
