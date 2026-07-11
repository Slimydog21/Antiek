"""Pure tests for marketplace paid purchase gate compose."""

from __future__ import annotations

from substrate.marketplace_paid_purchase_gate_compose import (
    compose_marketplace_paid_purchase_gate,
    format_marketplace_paid_purchase_gate_summary,
)


def test_free_path_gate_ready():
    c = compose_marketplace_paid_purchase_gate(
        title="Scaling Laws",
        account_id="acct-1",
        free_copy_available=True,
        free_html_projection_sha="sha-free-1",
        port_requested=True,
        purchase_ack=False,
        list_price_usd=12,
        approved_spend_usd=20,
        remaining_budget_usd=50,
        operator_ack=True,
    )
    assert c.purchase_ready is False
    assert c.gate_ready is True
    assert c.free_port.path == "prefer_free_html"
    assert c.purchase_executed is False
    assert c.charge_executed is False
    assert c.hosted is False
    assert c.pdf_view_authorized is False
    s = format_marketplace_paid_purchase_gate_summary(c)
    assert "purchase_executed=false" in s
    assert "charge_executed=false" in s


def test_paid_path_ready():
    c = compose_marketplace_paid_purchase_gate(
        title="Deep Learning Book",
        account_id="acct-1",
        free_copy_available=False,
        purchase_html_projection_sha="sha-paid-1",
        port_requested=True,
        purchase_ack=True,
        list_price_usd=15,
        approved_spend_usd=20,
        remaining_budget_usd=100,
        operator_ack=True,
    )
    assert c.purchase_ready is True
    assert c.would_exceed_budget is False
    assert c.gate_ready is True
    assert c.free_port.path == "purchase_then_port"
    assert c.charge_executed is False
    assert c.to_dict()["purchase_executed"] is False


def test_budget_exceed():
    c = compose_marketplace_paid_purchase_gate(
        title="Expensive",
        account_id="acct-1",
        free_copy_available=False,
        purchase_html_projection_sha="sha-x",
        port_requested=True,
        purchase_ack=True,
        list_price_usd=50,
        approved_spend_usd=60,
        remaining_budget_usd=10,
        operator_ack=True,
    )
    assert c.would_exceed_budget is True
    assert c.purchase_ready is False
    assert c.gate_ready is False


def test_approved_below_list():
    c = compose_marketplace_paid_purchase_gate(
        title="T",
        account_id="a",
        free_copy_available=False,
        purchase_ack=True,
        list_price_usd=20,
        approved_spend_usd=10,
        remaining_budget_usd=100,
        port_requested=True,
        purchase_html_projection_sha="sha",
        operator_ack=True,
    )
    assert c.purchase_ready is False


def test_remaining_unknown():
    c = compose_marketplace_paid_purchase_gate(
        title="T",
        account_id="a",
        free_copy_available=False,
        purchase_ack=True,
        list_price_usd=10,
        approved_spend_usd=20,
        remaining_budget_usd=None,
        port_requested=True,
        operator_ack=True,
    )
    assert c.would_exceed_budget is None
    assert c.purchase_ready is False


def test_free_unknown_blocks_paid():
    c = compose_marketplace_paid_purchase_gate(
        title="T",
        account_id="a",
        free_copy_available=None,
        purchase_ack=True,
        list_price_usd=10,
        approved_spend_usd=20,
        remaining_budget_usd=50,
        port_requested=True,
        operator_ack=True,
    )
    assert c.purchase_ready is False
    assert c.free_port.path == "blocked_unknown_free"
