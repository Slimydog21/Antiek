"""Pure tests for paid purchase HTML view session compose."""

from __future__ import annotations

from substrate.paid_purchase_html_view_session_compose import (
    compose_paid_purchase_html_view_session,
    format_paid_purchase_html_view_session_summary,
)


def test_free_path_package():
    c = compose_paid_purchase_html_view_session(
        session_id="sess-1",
        asset_id="book-1",
        title="Scaling Laws",
        account_id="acct-1",
        free_copy_available=True,
        free_html_projection_sha="sha-free",
        port_requested=True,
        purchase_ack=False,
        list_price_usd=10,
        approved_spend_usd=20,
        remaining_budget_usd=50,
        operator_ack=True,
        view_requested=True,
        twin_bound=True,
    )
    assert c.purchase_gate.gate_ready is True
    assert c.view is not None
    assert c.view.html_view_ready is True
    assert c.session_package_ready is True
    assert c.purchase_executed is False
    assert c.charge_executed is False
    assert c.hosted is False
    assert c.pdf_view_authorized is False
    assert c.store_mutated is False
    assert "pdf_view_authorized=false" in format_paid_purchase_html_view_session_summary(
        c
    )


def test_paid_path_package():
    c = compose_paid_purchase_html_view_session(
        session_id="sess-2",
        asset_id="book-2",
        title="Deep Learning",
        account_id="acct-1",
        free_copy_available=False,
        purchase_html_projection_sha="sha-paid",
        port_requested=True,
        purchase_ack=True,
        list_price_usd=15,
        approved_spend_usd=20,
        remaining_budget_usd=100,
        operator_ack=True,
        view_requested=True,
    )
    assert c.purchase_gate.purchase_ready is True
    assert c.session_package_ready is True
    assert c.charge_executed is False
    assert c.to_dict()["purchase_executed"] is False


def test_budget_block():
    c = compose_paid_purchase_html_view_session(
        session_id="s",
        asset_id="b",
        title="Expensive",
        account_id="a",
        free_copy_available=False,
        purchase_html_projection_sha="sha",
        port_requested=True,
        purchase_ack=True,
        list_price_usd=50,
        approved_spend_usd=60,
        remaining_budget_usd=5,
        operator_ack=True,
        view_requested=True,
    )
    assert c.purchase_gate.purchase_ready is False
    assert c.session_package_ready is False


def test_pdf_claim_blocks_view():
    c = compose_paid_purchase_html_view_session(
        session_id="s",
        asset_id="b",
        title="T",
        account_id="a",
        free_copy_available=True,
        free_html_projection_sha="sha",
        port_requested=True,
        purchase_ack=False,
        list_price_usd=None,
        approved_spend_usd=None,
        remaining_budget_usd=None,
        operator_ack=True,
        view_requested=True,
        claimed_format="pdf",
    )
    assert c.view is not None
    assert c.view.html_view_ready is False
    assert c.session_package_ready is False
    assert c.pdf_view_authorized is False
