"""Pure tests for collective presented twins + paid ND pack."""

from __future__ import annotations

import pytest

from substrate.collective_presented_twins_paid_nd_compose import (
    CollectivePresentedTwinsPaidNdComposeError,
    compose_collective_presented_twins_paid_nd,
    format_collective_presented_twins_paid_nd_summary,
)
from tests.test_paid_purchase_nd_shadow_twin_presentation_compose import (
    ND_TWIN,
    PURCHASE_FREE,
)

COLLECTIVE = {
    "session_id": "sess-1",
    "parent_asset_id": "book-1",
    "members": [
        {
            "instance_id": "inst-a",
            "parent_asset_id": "book-1",
            "status": "open",
            "highlight": "scaling laws claim",
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
    "cohesive_prompt": (
        "Synthesize presented twin instances A and B as one unit"
    ),
}

PAID_ND = {
    "purchase": PURCHASE_FREE,
    "nd_twin": ND_TWIN,
}


def test_collective_paid_nd_ready():
    c = compose_collective_presented_twins_paid_nd(
        collective=COLLECTIVE,
        paid_nd=PAID_ND,
        operator_ack=True,
    )
    assert c.collective.pack_ready is True
    assert c.paid_nd.pack_ready is True
    assert c.pack_ready is True
    assert c.live_dispatched is False
    assert c.merge_executed is False
    assert c.analysis_written is False
    assert c.purchase_executed is False
    assert c.live_router_authorized is False
    assert c.twin_written is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority == "collective_presented_twins_paid_nd_compose_advisory"
    )
    assert "live_dispatched=false" in (
        format_collective_presented_twins_paid_nd_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_collective_presented_twins_paid_nd(
        collective=COLLECTIVE,
        paid_nd=PAID_ND,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_dispatched is False
    assert c.purchase_executed is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_collective_presented_twins_paid_nd(
        collective={**COLLECTIVE, "session_id": "sess-other"},
        paid_nd=PAID_ND,
        operator_ack=True,
    )
    assert c.pack_ready is False
    assert c.merge_executed is False
    assert c.live_dispatched is False


def test_parent_mismatch_blocks():
    c = compose_collective_presented_twins_paid_nd(
        collective={
            **COLLECTIVE,
            "parent_asset_id": "book-other",
            "members": [
                {**m, "parent_asset_id": "book-other"}
                for m in COLLECTIVE["members"]
            ],
        },
        paid_nd=PAID_ND,
        operator_ack=True,
    )
    assert c.pack_ready is False
    assert c.analysis_written is False
    assert c.purchase_executed is False


def test_require_operator_ack_type():
    with pytest.raises(CollectivePresentedTwinsPaidNdComposeError):
        compose_collective_presented_twins_paid_nd(
            collective=COLLECTIVE,
            paid_nd=PAID_ND,
            operator_ack="yes",  # type: ignore[arg-type]
        )
