"""Pure tests for settings add-model over ND shadow twin presentation pack."""

from __future__ import annotations

from substrate.settings_add_model_nd_shadow_twin_presentation_compose import (
    compose_settings_add_model_nd_shadow_twin_presentation,
    format_settings_add_model_nd_shadow_twin_presentation_summary,
)
from tests.test_nd_shadow_twin_presentation_competition_dr_source_attach_compose import (
    ND_SHADOW,
    TWIN_PRESENTATION,
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
    "twin_presentation": TWIN_PRESENTATION,
}


def test_settings_add_model_nd_twin_presentation_ready():
    c = compose_settings_add_model_nd_shadow_twin_presentation(
        settings=SETTINGS,
        nd_pack=ND_PACK,
        operator_ack=True,
    )
    assert c.settings.pack_ready is True
    assert c.nd_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"
    assert c.twin_written is False
    assert c.merge_executed is False
    assert c.purchase_executed is False
    assert (
        c.authority
        == "settings_add_model_nd_shadow_twin_presentation_compose_advisory"
    )
    assert "secrets_stored=false" in (
        format_settings_add_model_nd_shadow_twin_presentation_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_settings_add_model_nd_shadow_twin_presentation(
        settings=SETTINGS,
        nd_pack=ND_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_open_requested_false_blocks_nd_pack():
    c = compose_settings_add_model_nd_shadow_twin_presentation(
        settings=SETTINGS,
        nd_pack={
            **ND_PACK,
            "twin_presentation": {
                **TWIN_PRESENTATION,
                "presentation": {
                    **TWIN_PRESENTATION["presentation"],
                    "open_requested": False,
                },
            },
        },
        operator_ack=True,
    )
    assert c.nd_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.secrets_stored is False
    assert c.live_router_authorized is False


def test_preview_action_still_pure():
    c = compose_settings_add_model_nd_shadow_twin_presentation(
        settings={**SETTINGS, "action": "preview"},
        nd_pack=ND_PACK,
        operator_ack=True,
    )
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.production_router_verdict == "REJECT"
    assert c.live_router_authorized is False
