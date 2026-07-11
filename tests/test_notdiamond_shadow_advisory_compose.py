"""Pure tests for NotDiamond shadow advisory compose."""

from __future__ import annotations

import pytest

from substrate.notdiamond_shadow_advisory_compose import (
    NotDiamondShadowAdvisoryComposeError,
    compose_notdiamond_shadow_advisory,
    format_notdiamond_shadow_advisory_summary,
)


def test_reject_and_never_authorize():
    c = compose_notdiamond_shadow_advisory(
        selected_model_id="gpt-5",
        nd_recommended_model_id="claude-opus",
        kill_switch_on=False,
        confidence=0.72,
        task="deep_research",
        inventory_model_ids=["gpt-5", "claude-opus", "mimo"],
    )
    assert c.production_router_verdict == "REJECT"
    assert c.live_router_authorized is False
    assert c.shadow_visible is True
    assert c.differs_from_selected is True
    assert c.suggested_model_id == "claude-opus"
    assert c.to_dict()["live_router_authorized"] is False
    assert c.to_dict()["production_router_verdict"] == "REJECT"
    assert "REJECT" in format_notdiamond_shadow_advisory_summary(c)


def test_kill_switch_suppresses():
    c = compose_notdiamond_shadow_advisory(
        selected_model_id="gpt-5",
        nd_recommended_model_id="claude-opus",
        kill_switch_on=True,
        inventory_model_ids=["gpt-5", "claude-opus"],
    )
    assert c.shadow_visible is False
    assert c.differs_from_selected is None
    assert c.suggested_model_id is None
    assert c.live_router_authorized is False
    assert c.production_router_verdict == "REJECT"


def test_null_rec_no_invent():
    c = compose_notdiamond_shadow_advisory(
        selected_model_id="gpt-5",
        nd_recommended_model_id=None,
        kill_switch_on=False,
    )
    assert c.shadow_visible is False
    assert c.suggested_model_id is None


def test_inventory_fail_closed():
    c = compose_notdiamond_shadow_advisory(
        selected_model_id="gpt-5",
        nd_recommended_model_id="unknown-model",
        kill_switch_on=False,
        inventory_model_ids=["gpt-5", "claude-opus"],
    )
    assert c.shadow_visible is False


def test_rejects_secretish_and_non_bool_kill():
    with pytest.raises(NotDiamondShadowAdvisoryComposeError, match="secret|model id"):
        compose_notdiamond_shadow_advisory(
            selected_model_id="gpt-5",
            nd_recommended_model_id="sk-abc123secret",
            kill_switch_on=False,
        )
    with pytest.raises(NotDiamondShadowAdvisoryComposeError, match="kill_switch_on"):
        compose_notdiamond_shadow_advisory(
            selected_model_id="gpt-5",
            nd_recommended_model_id="x",
            kill_switch_on="yes",  # type: ignore[arg-type]
        )
