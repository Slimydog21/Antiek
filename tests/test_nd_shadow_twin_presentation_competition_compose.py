"""Pure tests for ND shadow REJECT on twin presentation competition pack."""

from __future__ import annotations

import pytest

from substrate.nd_shadow_twin_presentation_competition_compose import (
    NdShadowTwinPresentationCompetitionComposeError,
    compose_nd_shadow_twin_presentation_competition,
    format_nd_shadow_twin_presentation_competition_summary,
)
from tests.test_recursive_twin_presentation_competition_dr_compose import (
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


def test_nd_shadow_twin_presentation_ready():
    c = compose_nd_shadow_twin_presentation_competition(
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
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "nd_shadow_twin_presentation_competition_compose_advisory"
    )
    assert "live_router_authorized=false" in (
        format_nd_shadow_twin_presentation_competition_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_nd_shadow_twin_presentation_competition(
        nd_shadow=ND_SHADOW,
        twin_presentation=TWIN_PRESENTATION,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"
    assert c.twin_written is False


def test_open_requested_false_blocks():
    c = compose_nd_shadow_twin_presentation_competition(
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


def test_kill_switch_off_still_reject():
    c = compose_nd_shadow_twin_presentation_competition(
        nd_shadow={**ND_SHADOW, "kill_switch_on": False},
        twin_presentation=TWIN_PRESENTATION,
        operator_ack=True,
    )
    assert c.nd_shadow.production_router_verdict == "REJECT"
    assert c.nd_shadow.live_router_authorized is False
    assert c.live_router_authorized is False
    assert c.pack_ready is True
    assert c.production_router_verdict == "REJECT"


def test_require_operator_ack_type():
    with pytest.raises(NdShadowTwinPresentationCompetitionComposeError):
        compose_nd_shadow_twin_presentation_competition(
            nd_shadow=ND_SHADOW,
            twin_presentation=TWIN_PRESENTATION,
            operator_ack="yes",  # type: ignore[arg-type]
        )
