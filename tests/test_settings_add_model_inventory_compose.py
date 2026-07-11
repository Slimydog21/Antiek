"""Pure tests for settings add-model inventory compose."""

from __future__ import annotations

import pytest

from substrate.settings_add_model_inventory_compose import (
    SettingsAddModelInventoryComposeError,
    compose_settings_add_model_inventory,
    format_settings_add_model_inventory_summary,
)


def test_preview():
    c = compose_settings_add_model_inventory(
        models=[
            {"model_id": "gpt-5.5", "provider": "openai"},
            {"model_id": "grok-4.5", "provider": "xai"},
        ],
        pending_add_model_ids=["mimo-v2"],
        action="preview",
        daily_cap_usd=25,
        spent_usd=4,
        selected_model_id="gpt-5.5",
        operator_ack=True,
    )
    assert c.inventory.inventory_count == 2
    assert c.inventory.pending_add_count == 1
    assert c.proposed_new_count == 1
    assert list(c.proposed_new_model_ids) == ["mimo-v2"]
    assert c.pack_ready is True
    assert c.secrets_stored is False
    assert c.inventory_mutated is False
    assert c.live_router_authorized is False
    assert "inventory_mutated=false" in format_settings_add_model_inventory_summary(
        c
    )


def test_propose_add():
    c = compose_settings_add_model_inventory(
        models=[{"model_id": "gpt-5.5"}],
        pending_add_model_ids=["claude-opus", "mimo-v2"],
        action="propose_add",
        daily_cap_usd=10,
        spent_usd=1,
        operator_ack=True,
    )
    assert c.proposed_new_count == 2
    assert c.pack_ready is True
    assert c.decision_tree is not None
    assert c.inventory_mutated is False


def test_duplicates_not_ready():
    c = compose_settings_add_model_inventory(
        models=[{"model_id": "gpt-5.5"}],
        pending_add_model_ids=["gpt-5.5"],
        action="propose_add",
        daily_cap_usd=10,
        spent_usd=0,
        operator_ack=True,
    )
    assert c.proposed_new_count == 0
    assert c.pack_ready is False


def test_secret_rejected():
    with pytest.raises(
        SettingsAddModelInventoryComposeError, match="secret material"
    ):
        compose_settings_add_model_inventory(
            models=[{"model_id": "gpt-5.5"}],
            pending_add_model_ids=["sk-abc123secret"],
            action="preview",
            daily_cap_usd=10,
            spent_usd=0,
            operator_ack=True,
        )


def test_ack_false():
    c = compose_settings_add_model_inventory(
        models=[{"model_id": "gpt-5.5"}],
        pending_add_model_ids=["mimo-v2"],
        action="propose_add",
        daily_cap_usd=10,
        spent_usd=0,
        operator_ack=False,
    )
    assert c.pack_ready is False
    assert c.live_router_authorized is False
