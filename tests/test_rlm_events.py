"""Tests for RLM typed event envelope helpers."""

from __future__ import annotations

import asyncio

from orchestration.rlm.events import RLMEventEmitter, make_rlm_event
from substrate.schemas.events import (
    Event,
    RLMSessionStartedPayload,
    RLMSubCallDispatchedPayload,
)


def test_make_rlm_event_uses_payload_action_type_and_metadata():
    payload = RLMSessionStartedPayload(
        session_id="rlm-abc",
        root_role="wrestler",
        document_id_ref="doc-1",
        threshold_tokens=64_000,
        estimated_tokens=128_000,
        max_iterations=8,
        cost_cap_usd=5.0,
    )

    event = make_rlm_event(
        investigation_id="inv-1",
        payload=payload,
        document_id="doc-1",
        param_version="test-rlm",
    )

    assert event.event_id.startswith("evt-")
    assert event.investigation_id == "inv-1"
    assert event.action_type == "rlm.session_started"
    assert event.payload is payload
    assert event.param_version == "test-rlm"
    assert event.document_id == "doc-1"
    rebuilt = Event.model_validate_json(event.model_dump_json())
    assert isinstance(rebuilt.payload, RLMSessionStartedPayload)


def test_rlm_event_emitter_broadcasts_typed_events():
    seen: list[Event] = []

    async def broadcast(event: Event) -> None:
        seen.append(event)

    emitter = RLMEventEmitter(
        broadcast,
        investigation_id="inv-2",
        document_id="doc-2",
        param_version="test-rlm",
    )
    payload = RLMSubCallDispatchedPayload(
        session_id="rlm-abc",
        target_role="grounder",
        tier="flash",
        prompt_count=5,
    )

    event = asyncio.run(emitter.emit(payload))

    assert seen == [event]
    assert event.action_type == "rlm.sub_call_dispatched"
    assert event.payload is payload
    assert event.investigation_id == "inv-2"
    assert event.document_id == "doc-2"
