"""Pure tests for marketplace free-before-buy HTML port compose."""

from __future__ import annotations

from substrate.marketplace_free_before_buy_html_port_compose import (
    compose_marketplace_free_before_buy_html_port,
)


def test_prefer_free_html():
    c = compose_marketplace_free_before_buy_html_port(
        title="Deep Learning",
        account_id="acct-1",
        free_copy_available=True,
        free_html_projection_sha="sha-free-1",
        purchase_ack=False,
        port_requested=True,
    )
    assert c.path == "prefer_free_html"
    assert c.port_ready is True
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.pdf_view_authorized is False
    assert c.to_dict()["purchase_executed"] is False


def test_blocked_unknown_free():
    c = compose_marketplace_free_before_buy_html_port(
        title="Book",
        account_id="a",
        free_copy_available=None,
        purchase_ack=True,
        port_requested=True,
        purchase_html_projection_sha="sha-p",
    )
    assert c.path == "blocked_unknown_free"
    assert c.port_ready is False


def test_purchase_path():
    no_ack = compose_marketplace_free_before_buy_html_port(
        title="Book",
        account_id="a",
        free_copy_available=False,
        purchase_ack=False,
        port_requested=True,
        purchase_html_projection_sha="sha-p",
    )
    assert no_ack.path == "incomplete"
    ready = compose_marketplace_free_before_buy_html_port(
        title="Book",
        account_id="a",
        free_copy_available=False,
        purchase_ack=True,
        port_requested=True,
        purchase_html_projection_sha="sha-p",
    )
    assert ready.path == "purchase_then_port"
    assert ready.port_ready is True
    assert ready.purchase_executed is False
