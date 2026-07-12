"""Pure tests for ND shadow REJECT over twin presentation competition DR source-attach."""

from __future__ import annotations

from substrate.nd_shadow_twin_presentation_competition_dr_source_attach_compose import (
    compose_nd_shadow_twin_presentation_competition_dr_source_attach,
    format_nd_shadow_twin_presentation_competition_dr_source_attach_summary,
)
from tests.test_recursive_twin_presentation_competition_dr_source_attach_compose import (
    COMPETITION_PACK,
    PRESENTATION,
    TWIN,
)

ND_SHADOW = {
    "selected_model_id": "gpt-5.5",
    "nd_recommended_model_id": "claude-opus",
    "kill_switch_on": True,
    "confidence": 0.72,
    "task": "deep_research",
    "inventory_model_ids": ["gpt-5.5", "claude-opus", "mimo"],
}

TWIN_PRESENTATION = {
    "twin": TWIN,
    "presentation": PRESENTATION,
    "competition_pack": COMPETITION_PACK,
}


def test_nd_shadow_twin_presentation_source_attach_ready():
    c = compose_nd_shadow_twin_presentation_competition_dr_source_attach(
        nd_shadow=ND_SHADOW,
        twin_presentation=TWIN_PRESENTATION,
        operator_ack=True,
    )
    assert c.nd_shadow.production_router_verdict == "REJECT"
    assert c.nd_shadow.live_router_authorized is False
    assert c.twin_presentation.pack_ready is True
    assert c.pack_ready is True
    assert c.live_router_authorized is False
    assert c.twin_written is False
    assert c.merge_executed is False
    assert c.purchase_executed is False
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.hosted is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "nd_shadow_twin_presentation_competition_dr_source_attach_compose_advisory"
    )
    assert "REJECT" in format_nd_shadow_twin_presentation_competition_dr_source_attach_summary(
        c
    )


def test_operator_ack_false_blocks():
    c = compose_nd_shadow_twin_presentation_competition_dr_source_attach(
        nd_shadow=ND_SHADOW,
        twin_presentation=TWIN_PRESENTATION,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"
    assert c.twin_written is False


def test_open_requested_false_blocks():
    c = compose_nd_shadow_twin_presentation_competition_dr_source_attach(
        nd_shadow=ND_SHADOW,
        twin_presentation={
            **TWIN_PRESENTATION,
            "presentation": {**PRESENTATION, "open_requested": False},
        },
        operator_ack=True,
    )
    assert c.twin_presentation.pack_ready is False
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_parent_mismatch_blocks():
    c = compose_nd_shadow_twin_presentation_competition_dr_source_attach(
        nd_shadow=ND_SHADOW,
        twin_presentation={
            **TWIN_PRESENTATION,
            "twin": {**TWIN, "parent_asset_id": "book-other"},
        },
        operator_ack=True,
    )
    assert c.twin_presentation.pack_ready is False
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.purchase_executed is False
