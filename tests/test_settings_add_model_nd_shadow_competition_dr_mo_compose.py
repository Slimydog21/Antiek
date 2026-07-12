"""Pure tests for settings add-model residual over ND shadow competition DR MO."""

from __future__ import annotations

from substrate.settings_add_model_nd_shadow_competition_dr_mo_compose import (
    compose_settings_add_model_nd_shadow_competition_dr_mo,
    format_settings_add_model_nd_shadow_competition_dr_mo_summary,
)
from tests.test_nd_shadow_competition_dr_mo_unattended_rewrite_compose import (
    COMPETITION_PACK,
    ND_SHADOW,
)
from tests.test_competition_dr_mo_unattended_source_attach_rewrite_compose import (
    COMPETITION,
    MO_PACK,
)

SETTINGS = {
    "models": [
        {"model_id": "gpt-5.5", "provider": "openai"},
        {"model_id": "grok-4.5", "provider": "xai"},
    ],
    "pending_add_model_ids": ["mimo-v2", "composer-2.5"],
    "action": "propose_add",
    "daily_cap_usd": 50,
    "spent_usd": 10,
    "selected_model_id": "gpt-5.5",
    "projected_cost_usd_high": 2,
    "projected_cost_usd_low": 1,
}

ND_PACK = {
    "nd_shadow": ND_SHADOW,
    "competition_pack": COMPETITION_PACK,
}


def test_settings_nd_shadow_ready():
    c = compose_settings_add_model_nd_shadow_competition_dr_mo(
        settings=SETTINGS,
        nd_pack=ND_PACK,
        operator_ack=True,
    )
    assert c.settings.pack_ready is True
    assert c.settings.proposed_new_count >= 1
    assert c.nd_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "settings_add_model_nd_shadow_competition_dr_mo_compose_advisory"
    )
    assert "secrets_stored=false" in (
        format_settings_add_model_nd_shadow_competition_dr_mo_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_settings_add_model_nd_shadow_competition_dr_mo(
        settings=SETTINGS,
        nd_pack=ND_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.production_router_verdict == "REJECT"


def test_would_exceed_blocks():
    c = compose_settings_add_model_nd_shadow_competition_dr_mo(
        settings=SETTINGS,
        nd_pack={
            "nd_shadow": ND_SHADOW,
            "competition_pack": {
                "competition": {**COMPETITION, "would_exceed": True},
                "mo_pack": MO_PACK,
            },
        },
        operator_ack=True,
    )
    assert c.nd_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.production_router_verdict == "REJECT"


def test_preview_empty_pending_ready():
    c = compose_settings_add_model_nd_shadow_competition_dr_mo(
        settings={**SETTINGS, "action": "preview", "pending_add_model_ids": []},
        nd_pack=ND_PACK,
        operator_ack=True,
    )
    assert c.settings.pack_ready is True
    assert c.nd_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.inventory_mutated is False
    assert c.secrets_stored is False
