"""Pure tests for marketplace HTML twin interrogation compose."""

from __future__ import annotations

from substrate.marketplace_html_twin_interrogation_compose import (
    compose_marketplace_html_twin_interrogation,
    format_marketplace_html_twin_interrogation_summary,
)

MODELS = [
    {"model_id": "gpt-5.5", "projected_cost_usd_high": 0.4},
    {"model_id": "grok-4.5", "projected_cost_usd_high": 0.2},
]
QUESTIONS = [
    {
        "question_id": "q1",
        "body": "What is the book's core thesis?",
        "priority": 2,
    },
    {
        "question_id": "q2",
        "body": "Which claims need counter-evidence?",
        "priority": 1,
    },
]


def test_free_html_interrogation_ready():
    c = compose_marketplace_html_twin_interrogation(
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
        include_twin_feed=True,
        include_interrogation=True,
        questions=QUESTIONS,
        chase_mode="swarm_fanout",
        models=MODELS,
        selected_model_id="gpt-5.5",
        daily_cap_usd=25,
        spent_usd=3,
        projected_cost_usd_high=0.4,
        would_exceed=False,
        source_families=["arxiv", "web"],
        user_prompt="Interrogate this hosted HTML book",
    )
    assert c.market_twin.session_ready is True
    assert c.interrogation is not None
    assert c.interrogation.loop_ready is True
    assert c.pack_ready is True
    assert c.purchase_executed is False
    assert c.charge_executed is False
    assert c.hosted is False
    assert c.pdf_view_authorized is False
    assert c.twin_written is False
    assert c.live_dispatched is False
    assert c.prompts_injected is False
    assert c.live_router_authorized is False
    assert "pdf_view_authorized=false" in format_marketplace_html_twin_interrogation_summary(
        c
    )
    assert c.to_dict()["charge_executed"] is False


def test_skip_interrogation():
    c = compose_marketplace_html_twin_interrogation(
        session_id="sess-1",
        asset_id="book-1",
        title="Scaling Laws",
        account_id="acct-1",
        free_copy_available=True,
        free_html_projection_sha="sha-free",
        port_requested=True,
        purchase_ack=False,
        list_price_usd=None,
        approved_spend_usd=None,
        remaining_budget_usd=None,
        operator_ack=True,
        view_requested=True,
        include_interrogation=False,
    )
    assert c.market_twin.session_ready is True
    assert c.interrogation is None
    assert c.pack_ready is True
    assert c.live_dispatched is False


def test_budget_block_market():
    c = compose_marketplace_html_twin_interrogation(
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
        include_interrogation=True,
        questions=QUESTIONS,
        models=MODELS,
        selected_model_id="gpt-5.5",
        daily_cap_usd=20,
        spent_usd=1,
        would_exceed=False,
    )
    assert c.market_twin.session_ready is False
    assert c.interrogation is None
    assert c.pack_ready is False
    assert c.purchase_executed is False


def test_would_exceed_blocks_loop():
    c = compose_marketplace_html_twin_interrogation(
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
        include_interrogation=True,
        questions=[QUESTIONS[0]],
        chase_mode="single_question",
        models=MODELS,
        selected_model_id="gpt-5.5",
        daily_cap_usd=1,
        spent_usd=0.9,
        projected_cost_usd_high=0.5,
        would_exceed=True,
    )
    assert c.market_twin.session_ready is True
    assert c.interrogation is not None
    assert c.interrogation.loop_ready is False
    assert c.pack_ready is False
    assert c.live_dispatched is False


def test_ack_false():
    c = compose_marketplace_html_twin_interrogation(
        session_id="sess-1",
        asset_id="book-1",
        title="Scaling Laws",
        account_id="acct-1",
        free_copy_available=True,
        free_html_projection_sha="sha-free",
        port_requested=True,
        purchase_ack=False,
        list_price_usd=None,
        approved_spend_usd=None,
        remaining_budget_usd=None,
        operator_ack=False,
        view_requested=True,
        include_interrogation=False,
    )
    assert c.pack_ready is False
    assert c.store_mutated is False
