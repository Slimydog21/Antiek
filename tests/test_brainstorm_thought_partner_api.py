"""Tests for the structured Brainstorm thought-partner endpoint."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from substrate.dispatch.router import DispatchResult, ProviderError


def _client() -> TestClient:
    return TestClient(create_app(register_wrestling=False, register_providers=False))


def _payload(**overrides):
    payload = {
        "user_prompt": "Synthesize these notes into a sharper direction.",
        "selected_notes": [
            {"note_id": "n-1", "note_text": "Retrieval must preserve provenance."},
            {"note_id": "n-2", "note_text": "Memory should retain friction."},
        ],
        "investigation_id": "inv-brainstorm",
    }
    payload.update(overrides)
    return payload


def _dispatch_result(text: str) -> DispatchResult:
    return DispatchResult(
        text=text,
        usage=None,  # type: ignore[arg-type]
        cost_usd=0.0,
        latency_ms=1,
        provider="cassette",
        model="thought-v1",
        tier="pro",
        finish_reason="stop",
        fallback_chain_index=0,
        event_id="evt-dispatch",
    )


def test_brainstorm_thought_partner_parses_structured_synthesis(monkeypatch):
    seen: dict[str, str] = {}

    def fake_dispatch(prompt, role, *, investigation_id, **kwargs):
        seen["prompt"] = prompt
        seen["role"] = role
        seen["investigation_id"] = investigation_id
        return _dispatch_result(json.dumps({
            "shape": "synthesis",
            "challenges": [],
            "synthesis_text": "The notes converge on provenance-preserving memory.",
            "extensions": [],
        }))

    monkeypatch.setattr("substrate.dispatch.router.dispatch", fake_dispatch)
    resp = _client().post("/brainstorm/thought-partner", json=_payload())

    assert resp.status_code == 200
    body = resp.json()
    assert seen["role"] == "thought_partner"
    assert seen["investigation_id"] == "inv-brainstorm"
    assert "NOTE n-1" in seen["prompt"]
    assert body["shape"] == "synthesis"
    assert body["text"] == "The notes converge on provenance-preserving memory."
    assert body["synthesis_text"] == body["text"]
    assert body["policy_id"] == "cassette/thought-v1"


def test_brainstorm_thought_partner_filters_fabricated_challenge_notes(monkeypatch):
    def fake_dispatch(prompt, role, *, investigation_id, **kwargs):
        return _dispatch_result(json.dumps({
            "shape": "challenge",
            "challenges": [
                {
                    "condition": "If provenance is lost during replay, the memory thesis fails.",
                    "note_ids": ["n-1", "n-made-up"],
                }
            ],
            "synthesis_text": "",
            "extensions": [],
        }))

    monkeypatch.setattr("substrate.dispatch.router.dispatch", fake_dispatch)
    resp = _client().post("/brainstorm/thought-partner", json=_payload())

    assert resp.status_code == 200
    body = resp.json()
    assert body["shape"] == "challenge"
    assert body["challenges"][0]["note_ids"] == ["n-1"]
    assert "n-made-up" not in body["text"]


def test_brainstorm_thought_partner_rejects_empty_inputs():
    client = _client()
    assert client.post(
        "/brainstorm/thought-partner",
        json=_payload(user_prompt=" "),
    ).status_code == 400
    assert client.post(
        "/brainstorm/thought-partner",
        json=_payload(selected_notes=[]),
    ).status_code == 400


def test_brainstorm_thought_partner_no_provider_is_honest_503(monkeypatch):
    def fake_dispatch(prompt, role, *, investigation_id, **kwargs):
        raise ProviderError(
            "no provider configured",
            provider="missing",
            model="thought-v1",
            latency_ms=0,
        )

    monkeypatch.setattr("substrate.dispatch.router.dispatch", fake_dispatch)
    resp = _client().post("/brainstorm/thought-partner", json=_payload())

    assert resp.status_code == 503
    assert "dispatch_unavailable" in resp.json()["detail"]
