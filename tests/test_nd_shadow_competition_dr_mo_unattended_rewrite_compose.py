"""Pure tests for ND shadow REJECT residual over competition DR MO rewrite."""

from __future__ import annotations

from substrate.nd_shadow_competition_dr_mo_unattended_rewrite_compose import (
    compose_nd_shadow_competition_dr_mo_unattended_rewrite,
    format_nd_shadow_competition_dr_mo_unattended_rewrite_summary,
)
from tests.test_competition_dr_mo_unattended_source_attach_rewrite_compose import (
    COMPETITION,
    MO_PACK,
)

ND_SHADOW = {
    "selected_model_id": "gpt-5.5",
    "nd_recommended_model_id": "claude-opus",
    "kill_switch_on": True,
    "confidence": 0.72,
    "task": "deep_research",
    "inventory_model_ids": ["gpt-5.5", "claude-opus", "mimo"],
}

COMPETITION_PACK = {
    "competition": COMPETITION,
    "mo_pack": MO_PACK,
}


def test_nd_shadow_reject_competition_ready():
    c = compose_nd_shadow_competition_dr_mo_unattended_rewrite(
        nd_shadow=ND_SHADOW,
        competition_pack=COMPETITION_PACK,
        operator_ack=True,
    )
    assert c.nd_shadow.production_router_verdict == "REJECT"
    assert c.nd_shadow.live_router_authorized is False
    assert c.competition_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.live_router_authorized is False
    assert c.twin_written is False
    assert c.purchase_executed is False
    assert c.charge_executed is False
    assert c.suite_rewritten is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "nd_shadow_competition_dr_mo_unattended_rewrite_compose_advisory"
    )
    assert "live_router_authorized=false" in (
        format_nd_shadow_competition_dr_mo_unattended_rewrite_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_nd_shadow_competition_dr_mo_unattended_rewrite(
        nd_shadow=ND_SHADOW,
        competition_pack=COMPETITION_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_would_exceed_blocks():
    c = compose_nd_shadow_competition_dr_mo_unattended_rewrite(
        nd_shadow=ND_SHADOW,
        competition_pack={
            "competition": {**COMPETITION, "would_exceed": True},
            "mo_pack": MO_PACK,
        },
        operator_ack=True,
    )
    assert c.competition_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_kill_switch_on_still_ready_when_competition_ready():
    c = compose_nd_shadow_competition_dr_mo_unattended_rewrite(
        nd_shadow={**ND_SHADOW, "kill_switch_on": True},
        competition_pack=COMPETITION_PACK,
        operator_ack=True,
    )
    assert c.nd_shadow.shadow_visible is False
    assert c.nd_shadow.production_router_verdict == "REJECT"
    assert c.live_router_authorized is False
    assert c.competition_pack.pack_ready is True
    assert c.pack_ready is True
