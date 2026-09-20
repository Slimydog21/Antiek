"""Prompt telemetry projection from trajectory (event-log SoT)."""

from __future__ import annotations

from interfaces.research.api.prompt_telemetry import build_prompt_telemetry


def test_build_prompt_telemetry_extracts_question_and_calls():
    rows = [
        {
            "event_id": "e0",
            "action_type": "investigation.start_requested",
            "emitted_at": "2026-09-18T10:00:00+00:00",
            "payload": {"question": "What is liberty?"},
        },
        {
            "event_id": "e1",
            "action_type": "dispatch.call",
            "emitted_at": "2026-09-18T10:00:05+00:00",
            "payload": {
                "target_role": "decomposer",
                "provider": "deepseek",
                "model": "deepseek-chat",
                "tier": "pro",
                "finish_reason": "stop",
                "latency_ms": 1200,
                "cost_usd": 0.002,
                "prompt_hash": "abc123",
                "input_tokens": 100,
                "output_tokens": 50,
            },
        },
        {
            "event_id": "e2",
            "action_type": "note.emerged",
            "payload": {},
        },
    ]
    out = build_prompt_telemetry("inv-1", rows)
    assert out.investigation_id == "inv-1"
    assert out.question == "What is liberty?"
    assert out.call_count == 1
    assert out.total_cost_usd == 0.002
    assert out.total_latency_ms == 1200
    assert out.prompt_bodies_stored is False
    call = out.calls[0]
    assert call.role == "decomposer"
    assert call.provider == "deepseek"
    assert call.finish_reason == "stop"
    assert call.prompt_hash == "abc123"


def test_build_prompt_telemetry_empty_rows():
    out = build_prompt_telemetry("inv-empty", [])
    assert out.call_count == 0
    assert out.question is None
    assert out.calls == []
