"""Pure tests for marketplace free over settings ND twin presentation pack."""

from __future__ import annotations

from substrate.marketplace_free_settings_add_model_nd_shadow_twin_compose import (
    compose_marketplace_free_settings_add_model_nd_shadow_twin,
    format_marketplace_free_settings_add_model_nd_shadow_twin_summary,
)
from tests.test_settings_add_model_nd_shadow_twin_presentation_compose import (
    ND_PACK,
    SETTINGS,
)

MARKET = {
    "title": "Scaling Laws Book",
    "account_id": "acct-1",
    "free_copy_available": True,
    "free_html_projection_sha": "sha-free-html",
    "purchase_ack": False,
    "port_requested": True,
}

SETTINGS_PACK = {
    "settings": SETTINGS,
    "nd_pack": ND_PACK,
}


def test_marketplace_free_settings_nd_twin_ready():
    c = compose_marketplace_free_settings_add_model_nd_shadow_twin(
        market=MARKET,
        settings_pack=SETTINGS_PACK,
        operator_ack=True,
    )
    assert c.market.port_ready is True
    assert c.settings_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.pdf_primary is False
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "marketplace_free_settings_add_model_nd_shadow_twin_compose_advisory"
    )
    assert "purchase_executed=false" in (
        format_marketplace_free_settings_add_model_nd_shadow_twin_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_marketplace_free_settings_add_model_nd_shadow_twin(
        market=MARKET,
        settings_pack=SETTINGS_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.production_router_verdict == "REJECT"


def test_no_free_copy_blocks_port():
    c = compose_marketplace_free_settings_add_model_nd_shadow_twin(
        market={
            **MARKET,
            "free_copy_available": False,
            "free_html_projection_sha": None,
        },
        settings_pack=SETTINGS_PACK,
        operator_ack=True,
    )
    assert c.market.port_ready is False
    assert c.pack_ready is False
    assert c.purchase_executed is False
    assert c.hosted is False


def test_purchase_ack_still_never_purchases():
    c = compose_marketplace_free_settings_add_model_nd_shadow_twin(
        market={
            **MARKET,
            "free_copy_available": False,
            "free_html_projection_sha": None,
            "purchase_ack": True,
            "list_price_usd": 10,
            "approved_spend_usd": 20,
            "remaining_budget_usd": 50,
        },
        settings_pack=SETTINGS_PACK,
        operator_ack=True,
    )
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"
