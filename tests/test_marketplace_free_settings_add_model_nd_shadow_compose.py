"""Pure tests for marketplace free residual over settings add-model ND shadow."""

from __future__ import annotations

from substrate.marketplace_free_settings_add_model_nd_shadow_compose import (
    compose_marketplace_free_settings_add_model_nd_shadow,
    format_marketplace_free_settings_add_model_nd_shadow_summary,
)
from tests.test_settings_add_model_nd_shadow_competition_dr_mo_compose import (
    ND_PACK,
    SETTINGS,
)
from tests.test_competition_dr_mo_unattended_source_attach_rewrite_compose import (
    COMPETITION,
    MO_PACK,
)
from tests.test_nd_shadow_competition_dr_mo_unattended_rewrite_compose import (
    ND_SHADOW,
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


def test_marketplace_free_settings_ready():
    c = compose_marketplace_free_settings_add_model_nd_shadow(
        market=MARKET,
        settings_pack=SETTINGS_PACK,
        operator_ack=True,
    )
    assert c.market.port_ready is True
    assert "prefer_free" in c.market.path
    assert c.settings_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "marketplace_free_settings_add_model_nd_shadow_compose_advisory"
    )
    assert "purchase_executed=false" in (
        format_marketplace_free_settings_add_model_nd_shadow_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_marketplace_free_settings_add_model_nd_shadow(
        market=MARKET,
        settings_pack=SETTINGS_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.production_router_verdict == "REJECT"


def test_unknown_free_blocks_port():
    c = compose_marketplace_free_settings_add_model_nd_shadow(
        market={
            **MARKET,
            "free_copy_available": None,
            "free_html_projection_sha": None,
            "purchase_ack": False,
        },
        settings_pack=SETTINGS_PACK,
        operator_ack=True,
    )
    assert c.market.port_ready is False
    assert c.pack_ready is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.production_router_verdict == "REJECT"


def test_would_exceed_blocks():
    c = compose_marketplace_free_settings_add_model_nd_shadow(
        market=MARKET,
        settings_pack={
            "settings": SETTINGS,
            "nd_pack": {
                "nd_shadow": ND_SHADOW,
                "competition_pack": {
                    "competition": {**COMPETITION, "would_exceed": True},
                    "mo_pack": MO_PACK,
                },
            },
        },
        operator_ack=True,
    )
    assert c.settings_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.production_router_verdict == "REJECT"
