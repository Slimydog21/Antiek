"""Pure tests for marketplace HTML view + twin session compose."""

from __future__ import annotations

from substrate.marketplace_html_view_twin_session_compose import (
    compose_marketplace_html_view_twin_session,
    format_marketplace_html_view_twin_session_summary,
)


def test_free_path():
    c = compose_marketplace_html_view_twin_session(
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
        twin_findings=[
            {
                "source_id": "q1",
                "body": "What is the core thesis?",
                "kind": "question",
            }
        ],
        mark_for_prompt_context=True,
    )
    assert c.market_view.session_package_ready is True
    assert c.twin_feed is not None and c.twin_feed.feed_ready is True
    assert c.session_ready is True
    assert c.purchase_executed is False
    assert c.charge_executed is False
    assert c.hosted is False
    assert c.pdf_view_authorized is False
    assert c.twin_written is False
    assert c.record_persisted is False
    assert c.store_mutated is False
    assert "pdf_view_authorized=false" in format_marketplace_html_view_twin_session_summary(
        c
    )
    assert c.to_dict()["charge_executed"] is False


def test_paid_path():
    c = compose_marketplace_html_view_twin_session(
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
    assert c.market_view.purchase_gate.purchase_ready is True
    assert c.session_ready is True
    assert c.charge_executed is False


def test_budget_block():
    c = compose_marketplace_html_view_twin_session(
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
    assert c.market_view.session_package_ready is False
    assert c.session_ready is False


def test_skip_twin():
    c = compose_marketplace_html_view_twin_session(
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
        include_twin_feed=False,
    )
    assert c.twin_feed is None
    assert c.session_ready is True


def test_pdf_blocks():
    c = compose_marketplace_html_view_twin_session(
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
    assert c.market_view.session_package_ready is False
    assert c.session_ready is False
    assert c.pdf_view_authorized is False
