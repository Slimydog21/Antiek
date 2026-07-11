"""Hermetic tests for workstation record prompt context bridge."""

from __future__ import annotations

import pytest

from substrate.workstation_record_prompt_context_bridge import (
    WorkstationRecordPromptContextBridgeError,
    bridge_workstation_record_prompt_context,
)


def test_bridges_without_inject() -> None:
    e = bridge_workstation_record_prompt_context(
        session_id="sess-1",
        user_prompt="What are the open questions on scaling?",
        items=[
            {
                "record_id": "r1",
                "kind": "insight",
                "text": "scaling holds under noise",
                "weight": 0.9,
            },
            {
                "record_id": "r2",
                "kind": "question",
                "text": "what about multimodal?",
                "weight": 0.5,
            },
        ],
        placement="prefix",
    )
    assert e.prompts_injected is False
    assert e.record_persisted is False
    assert e.to_dict()["prompts_injected"] is False
    assert e.to_dict()["record_persisted"] is False
    assert e.bridge_ready is True
    assert e.context_line_count == 2
    assert "scaling holds" in e.proposed_prompt
    assert "open questions on scaling" in e.proposed_prompt
    assert e.authority == "workstation_record_prompt_context_bridge_advisory"


def test_empty_pack_and_suffix() -> None:
    e = bridge_workstation_record_prompt_context(
        session_id="s",
        user_prompt="Hello",
        items=[],
        placement="suffix",
    )
    assert e.context_line_count == 0
    assert e.proposed_prompt == "Hello"
    assert e.prompts_injected is False
    assert any("no invent context" in n for n in e.notes)


def test_model_decision_attach() -> None:
    e = bridge_workstation_record_prompt_context(
        session_id="s",
        user_prompt="Analyze",
        items=[
            {
                "record_id": "r1",
                "kind": "finding",
                "text": "A holds",
                "weight": 1,
            }
        ],
        model_decision={
            "selected_model_id": "flash-1",
            "models": [
                {
                    "model_id": "flash-1",
                    "tier": "flash",
                    "projected_cost_usd_high": 0.5,
                    "projected_cost_usd_low": 0.1,
                }
            ],
            "daily_cap_usd": 10,
            "spent_usd": 1,
        },
    )
    assert e.model_decision is not None
    assert e.model_decision.selected_model_id == "flash-1"
    assert e.prompts_injected is False


def test_rejects_blank_prompt() -> None:
    with pytest.raises(
        WorkstationRecordPromptContextBridgeError, match="user_prompt"
    ):
        bridge_workstation_record_prompt_context(
            session_id="s",
            user_prompt="  ",
            items=[],
        )
