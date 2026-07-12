"""Pure tests for settings add-model over marketplace free competition DR ND."""

from __future__ import annotations

from substrate.settings_add_model_marketplace_free_competition_dr_nd_compose import (
    compose_settings_add_model_marketplace_free_competition_dr_nd,
    format_settings_add_model_marketplace_free_competition_dr_nd_summary,
)
from tests.test_marketplace_free_competition_dr_nd_shadow_source_attach_compose import (
    COMPETITION_PACK,
    MARKET,
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

MARKET_PACK = {
    "market": MARKET,
    "competition_pack": COMPETITION_PACK,
}


def test_settings_add_model_marketplace_free_competition_ready():
    c = compose_settings_add_model_marketplace_free_competition_dr_nd(
        settings=SETTINGS,
        market_pack=MARKET_PACK,
        operator_ack=True,
    )
    assert c.settings.pack_ready is True
    assert c.market_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.pdf_primary is False
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.live_router_authorized is False
    assert c.twin_written is False
    assert c.merge_executed is False
    assert c.draft_written is False
    assert c.remote_index_queried is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.market_pack.competition_pack.nd_pack.nd_shadow.production_router_verdict
        == "REJECT"
    )
    assert (
        c.authority
        == "settings_add_model_marketplace_free_competition_dr_nd_compose_advisory"
    )
    assert "secrets_stored=false" in (
        format_settings_add_model_marketplace_free_competition_dr_nd_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_settings_add_model_marketplace_free_competition_dr_nd(
        settings=SETTINGS,
        market_pack=MARKET_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.purchase_executed is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_no_free_copy_blocks_market_pack():
    c = compose_settings_add_model_marketplace_free_competition_dr_nd(
        settings=SETTINGS,
        market_pack={
            **MARKET_PACK,
            "market": {
                **MARKET,
                "free_copy_available": False,
                "free_html_projection_sha": None,
                "purchase_ack": False,
                "port_requested": True,
            },
        },
        operator_ack=True,
    )
    assert c.market_pack.market.port_ready is False
    assert c.market_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.purchase_executed is False
    assert c.production_router_verdict == "REJECT"


def test_propose_add_no_new_ids_blocks_settings():
    c = compose_settings_add_model_marketplace_free_competition_dr_nd(
        settings={
            **SETTINGS,
            "pending_add_model_ids": ["gpt-5.5"],
            "action": "propose_add",
        },
        market_pack=MARKET_PACK,
        operator_ack=True,
    )
    assert c.settings.pack_ready is False
    assert c.pack_ready is False
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.purchase_executed is False
    assert c.production_router_verdict == "REJECT"
