"""Pure tests for collective multiselect residual over floating DR draft-before-merge pack."""

from __future__ import annotations

import pytest

from substrate.collective_multiselect_floating_dr_draft_before_merge_compose import (
    CollectiveMultiselectFloatingDrDraftBeforeMergeComposeError,
    compose_collective_multiselect_floating_dr_draft_before_merge,
    format_collective_multiselect_floating_dr_draft_before_merge_summary,
)
from tests.test_floating_dr_draft_before_merge_mo_price_ceiling_compose import (
    DRAFT_PACK,
    HIGHLIGHT_SURFACE,
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

FLOATING_DR_PACK = {
    "highlight_surface": HIGHLIGHT_SURFACE,
    "draft_pack": DRAFT_PACK,
}


def test_collective_multiselect_floating_dr_ready():
    c = compose_collective_multiselect_floating_dr_draft_before_merge(
        multiselect=MULTISELECT,
        floating_dr_pack=FLOATING_DR_PACK,
        operator_ack=True,
    )
    assert c.multiselect.pack_ready is True
    assert c.floating_dr_pack.pack_ready is True
    assert c.session_aligned is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.live_dispatched is False
    assert c.pack_dispatched is False
    assert c.merge_executed is False
    assert c.analysis_written is False
    assert c.twin_written is False
    assert c.draft_written is False
    assert c.live_execution_authorized is False
    assert c.charge_executed is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "collective_multiselect_floating_dr_draft_before_merge_compose_advisory"
    )
    assert "pack_dispatched=false" in (
        format_collective_multiselect_floating_dr_draft_before_merge_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_collective_multiselect_floating_dr_draft_before_merge(
        multiselect=MULTISELECT,
        floating_dr_pack=FLOATING_DR_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.pack_dispatched is False
    assert c.analysis_written is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_collective_multiselect_floating_dr_draft_before_merge(
        multiselect={**MULTISELECT, "session_id": "sess-other"},
        floating_dr_pack=FLOATING_DR_PACK,
        operator_ack=True,
    )
    assert c.session_aligned is False
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.production_router_verdict == "REJECT"


def test_single_selection_fails_closed():
    with pytest.raises(
        CollectiveMultiselectFloatingDrDraftBeforeMergeComposeError
    ) as ei:
        compose_collective_multiselect_floating_dr_draft_before_merge(
            multiselect={
                **MULTISELECT,
                "selected_instance_ids": ["inst-a"],
            },
            floating_dr_pack=FLOATING_DR_PACK,
            operator_ack=True,
        )
    assert "at least 2" in str(ei.value).lower() or "selected" in str(ei.value).lower()
