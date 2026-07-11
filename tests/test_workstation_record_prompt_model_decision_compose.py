"""Pure tests for workstation record→prompt→model decision compose."""

from __future__ import annotations

import pytest

from substrate.workstation_record_prompt_model_decision_compose import (
    WorkstationRecordPromptModelDecisionComposeError,
    compose_workstation_record_prompt_model_decision,
    format_workstation_record_prompt_model_decision_summary,
)

MODELS = [
    {
        "model_id": "gpt-5",
        "tier": "frontier",
        "projected_cost_usd_high": 2,
        "projected_cost_usd_low": 1,
    },
    {
        "model_id": "composer-2.5",
        "tier": "workhorse",
        "projected_cost_usd_high": 0.5,
    },
]
RECORDS = [
    {
        "record_id": "r1",
        "kind": "insight",
        "body": "scaling holds under noise",
        "source_ref": "paper-1",
    },
    {
        "record_id": "r2",
        "kind": "question",
        "body": "What is the failure mode?",
    },
]


def test_pack_ready():
    c = compose_workstation_record_prompt_model_decision(
        session_id="sess-1",
        parent_asset_id="paper-1",
        records=RECORDS,
        user_prompt="Summarize open questions",
        selected_model_id="gpt-5",
        models=MODELS,
        daily_cap_usd=100,
        spent_usd=40,
        projected_cost_usd_high=2,
        projected_cost_usd_low=1,
        operator_ack=True,
    )
    assert c.pack_ready is True
    assert c.records.record_ready is True
    assert c.bridge.bridge_ready is True
    assert c.decision.decision_ready is True
    assert "Workstation recursive context" in c.proposed_prompt
    assert "Summarize open questions" in c.proposed_prompt
    assert c.usage_percent == 40.0
    assert c.would_exceed is False
    assert c.record_persisted is False
    assert c.prompts_injected is False
    assert c.live_router_authorized is False
    assert c.secrets_stored is False
    assert c.live_meter_read is False
    s = format_workstation_record_prompt_model_decision_summary(c)
    assert "prompts_injected=false" in s
    assert c.to_dict()["live_router_authorized"] is False


def test_would_exceed():
    c = compose_workstation_record_prompt_model_decision(
        session_id="s",
        parent_asset_id="p",
        records=RECORDS,
        user_prompt="Go deep",
        selected_model_id="gpt-5",
        models=MODELS,
        daily_cap_usd=10,
        spent_usd=9,
        projected_cost_usd_high=5,
        operator_ack=True,
    )
    assert c.would_exceed is True
    assert c.prompts_injected is False


def test_ack_false():
    c = compose_workstation_record_prompt_model_decision(
        session_id="s",
        parent_asset_id="p",
        records=RECORDS,
        user_prompt="Go",
        selected_model_id="gpt-5",
        models=MODELS,
        daily_cap_usd=100,
        spent_usd=10,
        operator_ack=False,
    )
    assert c.records.record_ready is False
    assert c.pack_ready is False


def test_maps_claim_data():
    c = compose_workstation_record_prompt_model_decision(
        session_id="s",
        parent_asset_id="p",
        records=[
            {"record_id": "c1", "kind": "claim", "body": "X implies Y"},
            {"record_id": "d1", "kind": "data", "body": "n=42"},
        ],
        user_prompt="Assess",
        selected_model_id="composer-2.5",
        models=MODELS,
        daily_cap_usd=50,
        spent_usd=5,
        projected_cost_usd_high=0.5,
        operator_ack=True,
    )
    assert c.pack_ready is True
    assert "X implies Y" in c.bridge.proposed_prompt
    assert "n=42" in c.bridge.proposed_prompt


def test_unknown_model():
    with pytest.raises(
        WorkstationRecordPromptModelDecisionComposeError, match="not found"
    ):
        compose_workstation_record_prompt_model_decision(
            session_id="s",
            parent_asset_id="p",
            records=RECORDS,
            user_prompt="Go",
            selected_model_id="nope",
            models=MODELS,
            daily_cap_usd=10,
            spent_usd=1,
            operator_ack=True,
        )
