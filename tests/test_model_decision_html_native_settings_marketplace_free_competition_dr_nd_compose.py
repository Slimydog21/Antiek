"""Pure tests for model decision over HTML-native settings marketplace free competition pack."""

from __future__ import annotations

from substrate.model_decision_html_native_settings_marketplace_free_competition_dr_nd_compose import (
    compose_model_decision_html_native_settings_marketplace_free_competition_dr_nd,
    format_model_decision_html_native_settings_marketplace_free_competition_dr_nd_summary,
)
from tests.test_html_native_settings_marketplace_free_competition_dr_nd_compose import (
    HTML_VIEW,
    SETTINGS_PACK,
)

DECISION = {
    "selected_model_id": "gpt-5.5",
    "models": [
        {
            "model_id": "gpt-5.5",
            "tier": "frontier",
            "projected_cost_usd_high": 2,
            "projected_cost_usd_low": 1,
        },
        {
            "model_id": "composer-2.5",
            "tier": "workhorse",
            "projected_cost_usd_high": 0.5,
        },
    ],
    "daily_cap_usd": 50,
    "spent_usd": 10,
    "projected_cost_usd_high": 2,
    "projected_cost_usd_low": 1,
    "focus_task": "deep_research",
    "pending_add_model_ids": ["mimo-v2"],
}

HTML_NATIVE_PACK = {
    "html_view": HTML_VIEW,
    "settings_pack": SETTINGS_PACK,
}


def test_model_decision_html_native_settings_ready():
    c = compose_model_decision_html_native_settings_marketplace_free_competition_dr_nd(
        decision=DECISION,
        html_native_pack=HTML_NATIVE_PACK,
        operator_ack=True,
    )
    assert c.decision.decision_ready is True
    assert c.decision.would_exceed is False
    assert c.html_native_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.focus_task == "deep_research"
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.live_meter_read is False
    assert c.pdf_primary is False
    assert c.pdf_view_authorized is False
    assert c.purchase_executed is False
    assert c.hosted is False
    assert c.inventory_mutated is False
    assert c.remote_index_queried is False
    assert c.suite_rewritten is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "model_decision_html_native_settings_marketplace_free_competition_dr_nd_compose_advisory"
    )
    assert "live_router_authorized=false" in (
        format_model_decision_html_native_settings_marketplace_free_competition_dr_nd_summary(
            c
        )
    )


def test_operator_ack_false_blocks():
    c = compose_model_decision_html_native_settings_marketplace_free_competition_dr_nd(
        decision=DECISION,
        html_native_pack=HTML_NATIVE_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"


def test_would_exceed_blocks():
    c = compose_model_decision_html_native_settings_marketplace_free_competition_dr_nd(
        decision={
            **DECISION,
            "projected_cost_usd_high": 100,
            "daily_cap_usd": 50,
            "spent_usd": 10,
        },
        html_native_pack=HTML_NATIVE_PACK,
        operator_ack=True,
    )
    assert c.decision.would_exceed is True
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"


def test_session_mismatch_blocks():
    c = compose_model_decision_html_native_settings_marketplace_free_competition_dr_nd(
        decision=DECISION,
        html_native_pack={
            **HTML_NATIVE_PACK,
            "html_view": {**HTML_VIEW, "session_id": "sess-other"},
        },
        operator_ack=True,
    )
    assert c.html_native_pack.session_aligned is False
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.pdf_primary is False
    assert c.production_router_verdict == "REJECT"
