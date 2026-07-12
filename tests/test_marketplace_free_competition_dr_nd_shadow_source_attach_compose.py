"""Pure tests for marketplace free over competition DR ND shadow source-attach."""

from __future__ import annotations

from substrate.marketplace_free_competition_dr_nd_shadow_source_attach_compose import (
    compose_marketplace_free_competition_dr_nd_shadow_source_attach,
    format_marketplace_free_competition_dr_nd_shadow_source_attach_summary,
)
from tests.test_competition_dr_nd_shadow_source_attach_weekly_learn_compose import (
    COMPETITION,
    ND_PACK,
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
    "nd_pack": ND_PACK,
}


def test_marketplace_free_competition_dr_nd_shadow_ready():
    c = compose_marketplace_free_competition_dr_nd_shadow_source_attach(
        market=MARKET,
        competition_pack=COMPETITION_PACK,
        operator_ack=True,
    )
    assert c.market.port_ready is True
    assert c.competition_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.pdf_view_authorized is False
    assert c.pdf_primary is False
    assert c.live_dispatch_authorized is False
    assert c.remote_fetched is False
    assert c.backlog_mutated is False
    assert c.live_router_authorized is False
    assert c.twin_written is False
    assert c.merge_executed is False
    assert c.draft_written is False
    assert c.secrets_stored is False
    assert c.remote_index_queried is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.competition_pack.nd_pack.nd_shadow.production_router_verdict == "REJECT"
    )
    assert (
        c.authority
        == "marketplace_free_competition_dr_nd_shadow_source_attach_compose_advisory"
    )
    assert "purchase_executed=false" in (
        format_marketplace_free_competition_dr_nd_shadow_source_attach_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_marketplace_free_competition_dr_nd_shadow_source_attach(
        market=MARKET,
        competition_pack=COMPETITION_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.live_dispatch_authorized is False
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_no_free_copy_without_purchase_blocks_port():
    c = compose_marketplace_free_competition_dr_nd_shadow_source_attach(
        market={
            **MARKET,
            "free_copy_available": False,
            "free_html_projection_sha": None,
            "purchase_ack": False,
            "port_requested": True,
        },
        competition_pack=COMPETITION_PACK,
        operator_ack=True,
    )
    assert c.market.port_ready is False
    assert c.pack_ready is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.production_router_verdict == "REJECT"


def test_would_exceed_blocks_competition_pack():
    c = compose_marketplace_free_competition_dr_nd_shadow_source_attach(
        market=MARKET,
        competition_pack={
            **COMPETITION_PACK,
            "competition": {**COMPETITION, "would_exceed": True},
        },
        operator_ack=True,
    )
    assert c.competition_pack.competition.pack_ready is False
    assert c.competition_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.live_dispatch_authorized is False
    assert c.production_router_verdict == "REJECT"
