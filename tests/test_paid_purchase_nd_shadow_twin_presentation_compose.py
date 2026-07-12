"""Pure tests for paid-purchase free-first + ND twin presentation pack."""

from __future__ import annotations

import pytest

from substrate.paid_purchase_nd_shadow_twin_presentation_compose import (
    PaidPurchaseNdShadowTwinPresentationComposeError,
    compose_paid_purchase_nd_shadow_twin_presentation,
    format_paid_purchase_nd_shadow_twin_presentation_summary,
)
from tests.test_nd_shadow_twin_presentation_competition_compose import (
    ND_SHADOW,
    TWIN_PRESENTATION,
)

PURCHASE_FREE = {
    "title": "Scaling Laws Book",
    "account_id": "acct-1",
    "free_copy_available": True,
    "free_html_projection_sha": "sha-free-html",
    "purchase_ack": False,
    "port_requested": True,
    "list_price_usd": 10,
    "approved_spend_usd": 20,
    "remaining_budget_usd": 50,
}

ND_TWIN = {
    "nd_shadow": ND_SHADOW,
    "twin_presentation": TWIN_PRESENTATION,
}


def test_free_first_nd_twin_ready():
    c = compose_paid_purchase_nd_shadow_twin_presentation(
        purchase=PURCHASE_FREE,
        nd_twin=ND_TWIN,
        operator_ack=True,
    )
    assert c.purchase.gate_ready is True
    assert c.purchase.purchase_executed is False
    assert c.nd_twin.pack_ready is True
    assert c.pack_ready is True
    assert c.purchase_executed is False
    assert c.charge_executed is False
    assert c.hosted is False
    assert c.live_router_authorized is False
    assert c.twin_written is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "paid_purchase_nd_shadow_twin_presentation_compose_advisory"
    )
    assert "purchase_executed=false" in (
        format_paid_purchase_nd_shadow_twin_presentation_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_paid_purchase_nd_shadow_twin_presentation(
        purchase=PURCHASE_FREE,
        nd_twin=ND_TWIN,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.purchase_executed is False
    assert c.production_router_verdict == "REJECT"


def test_paid_path_never_executes():
    c = compose_paid_purchase_nd_shadow_twin_presentation(
        purchase={
            **PURCHASE_FREE,
            "free_copy_available": False,
            "free_html_projection_sha": None,
            "purchase_html_projection_sha": "sha-paid-html",
            "purchase_ack": True,
            "list_price_usd": 12,
            "approved_spend_usd": 20,
            "remaining_budget_usd": 50,
        },
        nd_twin=ND_TWIN,
        operator_ack=True,
    )
    assert c.purchase.purchase_ready is True
    assert c.purchase.purchase_executed is False
    assert c.charge_executed is False
    assert c.hosted is False
    assert c.production_router_verdict == "REJECT"


def test_require_operator_ack_type():
    with pytest.raises(PaidPurchaseNdShadowTwinPresentationComposeError):
        compose_paid_purchase_nd_shadow_twin_presentation(
            purchase=PURCHASE_FREE,
            nd_twin=ND_TWIN,
            operator_ack="yes",  # type: ignore[arg-type]
        )
