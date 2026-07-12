"""Pure tests for recursive twin over marketplace free competition pack."""

from __future__ import annotations

from substrate.recursive_twin_marketplace_free_competition_dr_compose import (
    compose_recursive_twin_marketplace_free_competition_dr,
    format_recursive_twin_marketplace_free_competition_dr_summary,
)
from tests.test_marketplace_free_competition_dr_settings_bench_mo_compose import (
    COMPETITION_PACK,
    MARKET,
)

TWIN = {
    "parent_asset_id": "book-1",
    "source_excerpt": (
        "<p>Scaling laws hold under noise in compute-optimal regimes.</p>"
    ),
    "focus_questions": ["Where does it break?", "What residual gaps?"],
    "existing_twin_asset_id": "twin-book-1",
}

MARKET_PACK = {
    "market": MARKET,
    "competition_pack": COMPETITION_PACK,
}


def test_recursive_twin_marketplace_ready():
    c = compose_recursive_twin_marketplace_free_competition_dr(
        twin=TWIN,
        market_pack=MARKET_PACK,
        operator_ack=True,
    )
    assert c.twin.twin_propose_ready is True
    assert c.twin.twin_written is False
    assert c.market_pack.pack_ready is True
    assert c.parent_aligned is True
    assert c.pack_ready is True
    assert c.twin_written is False
    assert c.prompts_injected is False
    assert c.live_dispatch_authorized is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.remote_fetched is False
    assert c.inventory_mutated is False
    assert c.secrets_stored is False
    assert c.live_router_authorized is False
    assert c.suite_rewritten is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "recursive_twin_marketplace_free_competition_dr_compose_advisory"
    )
    assert "twin_written=false" in (
        format_recursive_twin_marketplace_free_competition_dr_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_recursive_twin_marketplace_free_competition_dr(
        twin=TWIN,
        market_pack=MARKET_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.twin_written is False
    assert c.prompts_injected is False
    assert c.live_dispatch_authorized is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.production_router_verdict == "REJECT"


def test_parent_mismatch_blocks():
    c = compose_recursive_twin_marketplace_free_competition_dr(
        twin={**TWIN, "parent_asset_id": "book-other"},
        market_pack=MARKET_PACK,
        operator_ack=True,
    )
    assert c.parent_aligned is False
    assert c.pack_ready is False
    assert c.twin_written is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.production_router_verdict == "REJECT"


def test_would_exceed_blocks():
    c = compose_recursive_twin_marketplace_free_competition_dr(
        twin=TWIN,
        market_pack={
            "market": MARKET,
            "competition_pack": {
                "competition": {
                    **COMPETITION_PACK["competition"],
                    "would_exceed": True,
                },
                "settings_pack": COMPETITION_PACK["settings_pack"],
            },
        },
        operator_ack=True,
    )
    assert c.market_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.twin_written is False
    assert c.live_dispatch_authorized is False
    assert c.purchase_executed is False
    assert c.production_router_verdict == "REJECT"
