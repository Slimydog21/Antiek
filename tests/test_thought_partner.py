"""Thought-partner API dispatch tests (AGH SPR-01)."""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any

import pytest
from fastapi.testclient import TestClient

from substrate.dispatch import (
    NormalizedUsage,
    RawProviderResponse,
    register_provider,
    reset_provider_registry,
)
from roles.thought_partner import (
    VALID_SHAPES,
    compose_thought_partner_prompt,
    parse_thought_partner_response,
)


class _MockHermesProvider:
    name = "hermes"

    def __init__(self, reply_text: str):
        self.reply_text = reply_text
        self.calls: list[dict[str, Any]] = []

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        self.calls.append({
            "model": model,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
        })
        return RawProviderResponse(
            text=self.reply_text,
            raw_usage={"input_tokens": 12, "output_tokens": 8},
            finish_reason="stop",
            latency_ms=7,
            request_id="req-thought-partner",
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        return NormalizedUsage(
            input_tokens=int(raw_usage.get("input_tokens", 0)),
            output_tokens=int(raw_usage.get("output_tokens", 0)),
        )


@pytest.fixture(autouse=True)
def _isolate_provider_registry():
    reset_provider_registry()
    yield
    reset_provider_registry()


@pytest.fixture
def client(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="thought-partner-api-test-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    # PIN unkeyed-ness rather than inherit it: on a developer/agent box
    # with real provider keys exported, anything that (re)registers
    # providers from env would turn the unkeyed-503 test into a LIVE
    # model call that returns 200 (caught by cross-CLI review on PR
    # #106 — the runner's OPENROUTER_API_KEY made the test fail 200!=503).
    # The full key list mirrors substrate/dispatch/providers/bootstrap.py.
    for key_env in (
        "ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY",
        "HERMES_API_KEY",
        "OPENROUTER_API_KEY",
        "XIAOMI_API_KEY",
    ):
        monkeypatch.delenv(key_env, raising=False)
    from interfaces.research.api.app import create_app

    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return TestClient(app)


def test_thought_partner_unkeyed_returns_503(client):
    response = client.post(
        "/thought-partner",
        json={
            "investigation_id": "__sidecar__",
            "prompt": "x",
            "system_context": "",
        },
    )

    assert response.status_code == 503
    assert "dispatch_unavailable" in response.json()["detail"]


def test_thought_partner_keyed_returns_model_reply_verbatim(client):
    reply = (
        '{"shape":"challenge","challenges":[{"condition":"marker condition",'
        '"note_ids":["n-1"]}],"synthesis_text":"","extensions":[]}'
        "\n\n@@actions\n"
        '[{"kind":"toast","level":"info","message":"distinctive marker"}]\n'
        "@@end"
    )
    provider = _MockHermesProvider(reply)
    register_provider(provider)

    response = client.post(
        "/thought-partner",
        json={
            "investigation_id": "__sidecar__",
            "prompt": "challenge this",
            "system_context": "workspace marker",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"] == reply
    assert set(body) == {"text", "thread_node_id"}


def test_thought_partner_response_schema_pin(client):
    register_provider(_MockHermesProvider('{"shape":"synthesis","synthesis_text":"ok"}'))

    response = client.post(
        "/thought-partner",
        json={
            "investigation_id": "__sidecar__",
            "prompt": "x",
            "system_context": "",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"text", "thread_node_id"}
    assert isinstance(body["text"], str)


def test_valid_shapes_match_spec():
    assert frozenset({"challenge", "synthesis", "extension"}) == VALID_SHAPES


def test_compose_prompt_includes_selected_notes():
    prompt = compose_thought_partner_prompt(
        user_prompt="What's the falsification condition for these claims?",
        selected_notes=[
            {"note_id": "n-1", "note_text": "Error rates below 10⁻³ at 100Q."},
            {
                "note_id": "n-2",
                "note_text": "Decoherence times suggest physical-limit headroom.",
            },
        ],
    )
    assert "NOTE n-1" in prompt
    assert "NOTE n-2" in prompt
    assert "falsification condition" in prompt
    assert "SECTOR STYLE GUIDE" not in prompt


def test_compose_prompt_includes_style_guide_when_provided():
    prompt = compose_thought_partner_prompt(
        user_prompt="Synthesize",
        selected_notes=[{"note_id": "n-1", "note_text": "Test"}],
        sector_style_guide="Use 'sidelobe' not 'side-lobe'; cite by year.",
    )
    assert "SECTOR STYLE GUIDE" in prompt
    assert "sidelobe" in prompt


def test_parse_challenge_shape():
    response = json.dumps({
        "shape": "challenge",
        "challenges": [
            {
                "condition": "If gate error exceeds 10⁻² at 200Q the threshold thesis fails",
                "note_ids": ["n-1", "n-3"],
            },
        ],
        "synthesis_text": "",
        "extensions": [],
    })
    parsed = parse_thought_partner_response(
        response,
        canonical_note_ids=("n-1", "n-3"),
    )
    assert parsed.shape == "challenge"
    assert len(parsed.challenges) == 1
    assert parsed.challenges[0].condition.startswith("If gate error")
    assert parsed.challenges[0].note_ids == ["n-1", "n-3"]
    assert parsed.synthesis is None
    assert parsed.extensions == []


def test_parse_challenge_filters_fabricated_note_ids():
    response = json.dumps({
        "shape": "challenge",
        "challenges": [
            {
                "condition": "If the benchmark only holds in one lab, the cross-lab thesis fails",
                "note_ids": ["n-1", "n-made-up"],
            },
        ],
        "synthesis_text": "",
        "extensions": [],
    })
    parsed = parse_thought_partner_response(
        response,
        canonical_note_ids=("n-1",),
    )
    assert parsed.shape == "challenge"
    assert parsed.challenges[0].note_ids == ["n-1"]


def test_parse_challenge_drops_fully_fabricated_note_ids_when_canonical_set_supplied():
    response = json.dumps({
        "shape": "challenge",
        "challenges": [
            {
                "condition": "If the benchmark only holds in one lab, the cross-lab thesis fails",
                "note_ids": ["n-made-up"],
            },
        ],
        "synthesis_text": "",
        "extensions": [],
    })
    parsed = parse_thought_partner_response(
        response,
        canonical_note_ids=("n-1",),
    )
    assert parsed.shape == "challenge"
    assert parsed.challenges == []


def test_parse_challenge_drops_note_ids_without_canonical_set():
    response = json.dumps({
        "shape": "challenge",
        "challenges": [
            {
                "condition": "If the benchmark only holds in one lab, the cross-lab thesis fails",
                "note_ids": ["n-made-up"],
            },
        ],
        "synthesis_text": "",
        "extensions": [],
    })
    parsed = parse_thought_partner_response(response)
    assert parsed.shape == "challenge"
    assert parsed.challenges == []


def test_parse_synthesis_shape():
    response = json.dumps({
        "shape": "synthesis",
        "challenges": [],
        "synthesis_text": "The notes converge on a single thesis: error rates have crossed the threshold but the margin is thin and group-dependent.",
        "extensions": [],
    })
    parsed = parse_thought_partner_response(response)
    assert parsed.shape == "synthesis"
    assert parsed.synthesis is not None
    assert "threshold" in parsed.synthesis.text


def test_parse_extension_shape():
    response = json.dumps({
        "shape": "extension",
        "challenges": [],
        "synthesis_text": "",
        "extensions": [
            {
                "sub_question": "How does QuEra's gate-set decomposition compare to Vuletic's when normalized for circuit depth?",
                "tag": "cross_domain",
                "rationale": "The cross-group benchmark would resolve the gap.",
            },
        ],
    })
    parsed = parse_thought_partner_response(response)
    assert parsed.shape == "extension"
    assert len(parsed.extensions) == 1
    assert parsed.extensions[0].tag == "cross_domain"


def test_parse_unknown_shape_coerces_to_synthesis():
    response = json.dumps({
        "shape": "garbage_value",
        "synthesis_text": "Some text",
        "challenges": [],
        "extensions": [],
    })
    parsed = parse_thought_partner_response(response)
    assert parsed.shape == "synthesis"


def test_parse_malformed_json_falls_back_to_raw_synthesis():
    raw = "This is not JSON but it is a valid musing about the problem."
    parsed = parse_thought_partner_response(raw)
    assert parsed.shape == "synthesis"
    assert parsed.synthesis is not None
    assert raw in parsed.synthesis.text


def test_parse_drops_empty_challenge_conditions():
    response = json.dumps({
        "shape": "challenge",
        "challenges": [
            {"condition": "", "note_ids": ["n-1"]},
            {"condition": "valid one", "note_ids": ["n-2"]},
        ],
    })
    parsed = parse_thought_partner_response(response, canonical_note_ids=("n-2",))
    assert len(parsed.challenges) == 1
    assert parsed.challenges[0].condition == "valid one"


def test_parse_drops_empty_extension_sub_questions():
    response = json.dumps({
        "shape": "extension",
        "extensions": [
            {"sub_question": "", "tag": "x"},
            {"sub_question": "valid one"},
        ],
    })
    parsed = parse_thought_partner_response(response)
    assert len(parsed.extensions) == 1
    assert parsed.extensions[0].sub_question == "valid one"
