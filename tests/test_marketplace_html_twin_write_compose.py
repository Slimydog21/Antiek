"""Pure tests for marketplace HTML twin write compose."""

from __future__ import annotations

from substrate.marketplace_html_twin_write_compose import (
    compose_marketplace_html_twin_write,
    format_marketplace_html_twin_write_summary,
)


def test_free_html_write_ready():
    c = compose_marketplace_html_twin_write(
        session_id="sess-1",
        asset_id="book-1",
        draft_id="draft-1",
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
            },
            {
                "source_id": "i1",
                "body": "Power-law scaling holds in compute-optimal regimes",
                "kind": "insight",
            },
        ],
        mark_for_prompt_context=True,
    )
    assert c.market_twin.session_ready is True
    assert c.write_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.purchase_executed is False
    assert c.charge_executed is False
    assert c.hosted is False
    assert c.pdf_view_authorized is False
    assert c.twin_written is False
    assert c.draft_written is False
    assert c.analysis_written is False
    assert c.merge_executed is False
    assert c.authority == "marketplace_html_twin_write_compose_advisory"
    assert "pdf_view_authorized=false" in format_marketplace_html_twin_write_summary(
        c
    )


def test_budget_block():
    c = compose_marketplace_html_twin_write(
        session_id="s",
        asset_id="b",
        draft_id="d",
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
    assert c.market_twin.session_ready is False
    assert c.pack_ready is False
    assert c.charge_executed is False


def test_operator_ack_false():
    c = compose_marketplace_html_twin_write(
        session_id="sess-1",
        asset_id="book-1",
        draft_id="draft-1",
        title="Scaling Laws",
        account_id="acct-1",
        free_copy_available=True,
        free_html_projection_sha="sha-free",
        port_requested=True,
        purchase_ack=False,
        list_price_usd=10,
        approved_spend_usd=20,
        remaining_budget_usd=50,
        operator_ack=False,
        view_requested=True,
    )
    assert c.pack_ready is False
    assert c.draft_written is False


def test_caller_slices():
    c = compose_marketplace_html_twin_write(
        session_id="sess-1",
        asset_id="book-1",
        draft_id="draft-1",
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
        twin_slices=[
            {
                "parent_asset_id": "book-1",
                "insights": ["A", "B"],
                "questions": ["Q?"],
            }
        ],
        chase_slots=[
            {
                "slot_id": "s1",
                "question_id": "q1",
                "parent_asset_id": "book-1",
                "status": "completed",
                "findings": ["f1"],
            },
            {
                "slot_id": "s2",
                "question_id": "q2",
                "parent_asset_id": "book-1",
                "status": "completed",
                "findings": ["f2"],
            },
        ],
        analysis_kind="full_analysis",
    )
    assert c.write_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.merge_executed is False
