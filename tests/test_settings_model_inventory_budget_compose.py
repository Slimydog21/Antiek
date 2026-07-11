"""Pure tests for settings model inventory budget compose."""

from __future__ import annotations

import pytest

from substrate.settings_model_inventory_budget_compose import (
    SettingsModelInventoryBudgetComposeError,
    compose_settings_model_inventory_budget,
)


def test_inventory_and_bar():
    c = compose_settings_model_inventory_budget(
        models=[
            {"model_id": "gpt-5", "tier": "frontier", "provider": "openai"},
            {"model_id": "claude-opus", "provider": "anthropic"},
        ],
        pending_add_model_ids=["mimo-pro"],
        daily_cap_usd=50,
        spent_usd=12.5,
        selected_model_id="gpt-5",
    )
    assert c.inventory_count == 2
    assert c.pending_add_count == 1
    assert c.selected_in_inventory is True
    assert c.bar.remaining_usd == 37.5
    assert c.secrets_stored is False
    assert c.live_router_authorized is False
    assert c.to_dict()["secrets_stored"] is False


def test_rejects_secret_and_null_remaining():
    with pytest.raises(
        SettingsModelInventoryBudgetComposeError, match="secret|model id"
    ):
        compose_settings_model_inventory_budget(
            models=[{"model_id": "sk-abc123secret"}],
            daily_cap_usd=10,
            spent_usd=1,
        )
    unk = compose_settings_model_inventory_budget(
        models=[{"model_id": "gpt-5"}],
        daily_cap_usd=None,
        spent_usd=None,
    )
    assert unk.bar.remaining_usd is None
