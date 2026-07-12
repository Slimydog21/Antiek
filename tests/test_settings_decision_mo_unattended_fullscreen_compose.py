"""Pure tests for settings decision + MO unattended fullscreen pack."""

from __future__ import annotations

import pytest

from substrate.settings_decision_mo_unattended_fullscreen_compose import (
    SettingsDecisionMoUnattendedFullscreenComposeError,
    compose_settings_decision_mo_unattended_fullscreen,
    format_settings_decision_mo_unattended_fullscreen_summary,
)
from tests.test_mo_unattended_fullscreen_draft_collective_compose import (
    FULLSCREEN_PACK,
    MO,
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

MO_PACK = {
    "mo": MO,
    "fullscreen_pack": FULLSCREEN_PACK,
}


def test_settings_decision_mo_ready():
    c = compose_settings_decision_mo_unattended_fullscreen(
        decision=DECISION,
        mo_pack=MO_PACK,
        operator_ack=True,
    )
    assert c.decision.decision_ready is True
    assert c.mo_pack.pack_ready is True
    assert c.pack_ready is True
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.live_meter_read is False
    assert c.live_execution_authorized is False
    assert c.purchase_executed is False
    assert c.production_router_verdict == "REJECT"
    assert (
        c.authority
        == "settings_decision_mo_unattended_fullscreen_compose_advisory"
    )
    assert "live_router_authorized=false" in (
        format_settings_decision_mo_unattended_fullscreen_summary(c)
    )


def test_operator_ack_false_blocks():
    c = compose_settings_decision_mo_unattended_fullscreen(
        decision=DECISION,
        mo_pack=MO_PACK,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.live_execution_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_would_exceed_blocks_pack():
    c = compose_settings_decision_mo_unattended_fullscreen(
        decision={
            **DECISION,
            "spent_usd": 49,
            "projected_cost_usd_high": 5,
            "projected_cost_usd_low": 3,
        },
        mo_pack=MO_PACK,
        operator_ack=True,
    )
    assert c.decision.would_exceed is True
    assert c.pack_ready is False
    assert c.live_router_authorized is False
    assert c.live_execution_authorized is False


def test_mo_spend_consent_false_blocks():
    c = compose_settings_decision_mo_unattended_fullscreen(
        decision=DECISION,
        mo_pack={
            **MO_PACK,
            "mo": {**MO, "spend_consent": False},
        },
        operator_ack=True,
    )
    assert c.mo_pack.pack_ready is False
    assert c.pack_ready is False
    assert c.live_execution_authorized is False


def test_require_operator_ack_type():
    with pytest.raises(SettingsDecisionMoUnattendedFullscreenComposeError):
        compose_settings_decision_mo_unattended_fullscreen(
            decision=DECISION,
            mo_pack=MO_PACK,
            operator_ack="yes",  # type: ignore[arg-type]
        )
