"""Inline-autocomplete API dispatch tests (CK-3 cursor-for-knowledge)."""

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


class _MockZaiProvider:
    """Stand-in for the ``zai`` provider (GLM-5.2). The flash tier routes
    autocomplete → zai, so a single registered stub services the role."""

    name = "zai"

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
            raw_usage={"input_tokens": 9, "output_tokens": 5},
            finish_reason="stop",
            latency_ms=4,
            request_id="req-complete",
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
    tmpdir = tempfile.mkdtemp(prefix="complete-api-test-")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", os.path.join(tmpdir, "t.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("ANTIEK_OPERATOR_EMAIL", raising=False)
    # PIN unkeyed-ness rather than inherit it: on a box with real provider
    # keys exported, anything that (re)registers providers from env would
    # turn the unkeyed-503 test into a LIVE model call. Mirrors the key list
    # in test_thought_partner.py + substrate/dispatch/providers/bootstrap.py.
    for key_env in (
        "ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY",
        "HERMES_API_KEY",
        "OPENROUTER_API_KEY",
        "XIAOMI_API_KEY",
        "Z_AI_API_KEY",
    ):
        monkeypatch.delenv(key_env, raising=False)
    from interfaces.research.api.app import create_app

    app = create_app(register_wrestling=False, register_providers=False, cors_origins=[])
    return TestClient(app)


def test_complete_unkeyed_returns_503(client):
    response = client.post("/complete", json={"prefix": "The key insight is"})

    assert response.status_code == 503
    assert "complete_unavailable" in response.json()["detail"]


def test_complete_keyed_returns_continuation_verbatim(client):
    reply = " the single-source-of-truth principle."
    provider = _MockZaiProvider(reply)
    register_provider(provider)

    response = client.post(
        "/complete",
        json={"prefix": "The key insight is", "document_context": None},
    )

    assert response.status_code == 200, response.text
    assert response.json()["text"] == reply
    # Non-vacuous: the model reply is returned verbatim AND the dispatched
    # prompt embeds the prefix + the autocomplete directive, routed to the
    # claude-less GLM-5.2 driver on the flash tier with the default budget.
    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert "The key insight is" in call["prompt"]
    assert "CONTINUATION:" in call["prompt"]
    assert call["model"] == "glm-5.2"
    assert call["max_tokens"] == 128  # CompleteRequest default


def test_complete_forwards_client_max_tokens_and_context(client):
    provider = _MockZaiProvider("continuation")
    register_provider(provider)

    response = client.post(
        "/complete",
        json={
            "prefix": "She argued that",
            "document_context": "Title: On Rigor",
            "max_tokens": 32,
        },
    )

    assert response.status_code == 200, response.text
    call = provider.calls[0]
    assert call["max_tokens"] == 32
    assert "On Rigor" in call["prompt"]


def test_complete_empty_prefix_returns_400(client):
    register_provider(_MockZaiProvider("continuation"))

    response = client.post("/complete", json={"prefix": "   "})

    assert response.status_code == 400
    assert response.json()["detail"] == "prefix must not be empty"


def test_complete_rejects_unbounded_client_inputs(client):
    """Cost-amplification guard (defense-in-depth): ``max_tokens`` and
    ``document_context`` are bounded server-side so a caller cannot trigger
    an unbounded generation or ship a multi-MB prompt. Out-of-range values
    are rejected with 422 before dispatch is ever called."""
    register_provider(_MockZaiProvider("continuation"))

    over_tokens = client.post(
        "/complete", json={"prefix": "x", "max_tokens": 100_000},
    )
    assert over_tokens.status_code == 422

    over_context = client.post(
        "/complete",
        json={"prefix": "x", "document_context": "z" * 8001},
    )
    assert over_context.status_code == 422
