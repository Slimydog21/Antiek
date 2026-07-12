"""Pure tests for marketplace free over competition DR settings pack."""

from __future__ import annotations

from substrate.marketplace_free_competition_dr_settings_bench_mo_compose import (
    compose_marketplace_free_competition_dr_settings_bench_mo,
    format_marketplace_free_competition_dr_settings_bench_mo_summary,
)
from tests.test_competition_dr_settings_add_model_bench_source_mo_compose import (
    COMPETITION,
    SETTINGS_PACK,
)

MARKET = {
    "title": "Scaling Laws Book",
    "account_id": "acct-1",
    "free_copy_available": True,
    "free_html_projection_sha": "sha-free-html",
    "purchase_ack": False,
    "port_requested": True,
}

COMPETITION_PACK = {
    "competition": COMPETITION,
    "settings_pack": SETTINGS_PACK,
}


def test_marketplace_free_competition_ready():
    c = compose_marketplace_free_competition_dr_settings_bench_mo(
        market=MARKET,
        competition_pack=COMPETITION_PACK,
        operator_ack=True,
    )
    assert c.market.port_ready is True
    assert c.market.purchase_executed is False
    assert c.market.hosted is False
    assert c.competition_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.pdf_view_authorized is False
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.backlog_mutated is False
    assert c.inventory_mutated is False
    assert c.secrets_stored is False
    assert c.live_router_authorized is False
    assert c.suite_rewritten is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "marketplace_free_competition_dr_settings_bench_mo_compose_advisory"
    )
    assert "purchase_executed=false" in (
        format_marketplace_free_competition_dr_settings_bench_mo_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_marketplace_free_competition_dr_settings_bench_mo(
        market=MARKET,
        competition_pack=COMPETITION_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.live_dispatch_authorized is False
    assert c.inventory_mutated is False
    assert c.production_router_verdict == "REJECT"


def test_no_free_sha_blocks_port():
    c = compose_marketplace_free_competition_dr_settings_bench_mo(
        market={
            **MARKET,
            "free_html_projection_sha": None,
            "free_copy_available": True,
        },
        competition_pack=COMPETITION_PACK,
        operator_ack=True,
    )
    assert c.market.port_ready is False
    assert c.pack_ready is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.production_router_verdict == "REJECT"


def test_would_exceed_blocks():
    c = compose_marketplace_free_competition_dr_settings_bench_mo(
        market=MARKET,
        competition_pack={
            "competition": {**COMPETITION, "would_exceed": True},
            "settings_pack": SETTINGS_PACK,
        },
        operator_ack=True,
    )
    assert c.competition_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.live_dispatch_authorized is False
    assert c.production_router_verdict == "REJECT"
