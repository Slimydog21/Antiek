"""Thought-partner API dispatch tests (AGH SPR-01)."""

from __future__ import annotations

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
    assert "thought_partner_unavailable" in response.json()["detail"]


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
    assert body["shape"] == "challenge"


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
    assert set(body) == {"shape", "text"}
    assert isinstance(body["shape"], str)
    assert isinstance(body["text"], str)
    assert body["shape"] in {"challenge", "synthesis", "extension"}
