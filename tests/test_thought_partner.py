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


class _MockZaiProvider:
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
        "Z_AI_API_KEY",
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
    provider = _MockZaiProvider(reply)
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
    register_provider(_MockZaiProvider('{"shape":"synthesis","synthesis_text":"ok"}'))

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


def test_thought_partner_retrieves_library_context_into_the_prompt(client, monkeypatch):
    """CK-1 non-vacuity: the endpoint retrieves relevant passages from the
    operator's library and feeds them into the thought-partner prompt — the
    "ask your library" grounding (Cursor's auto-context analog). Proves the
    retrieved context actually REACHES the model, not merely that the model
    replied. Falsifiable: stub the helper to return [] and the distinctive
    passage vanishes from the dispatched prompt."""
    distinctive_passage = "GROUNDING MARKER PASSAGE FROM THE LIBRARY"
    canned_notes = [{
        "note_id": "chunk-42",
        "note_text": distinctive_passage,
        "source_event_ids": ["doc-7"],
        "confidence": 0.91,
    }]
    monkeypatch.setattr(
        "interfaces.research.api.app._retrieve_thought_partner_context",
        lambda prompt, policy_tag, **kw: canned_notes,
    )
    reply = (
        '{"shape":"synthesis","synthesis_text":"grounded reply",'
        '"challenges":[],"extensions":[]}'
    )
    provider = _MockZaiProvider(reply)
    register_provider(provider)

    response = client.post(
        "/thought-partner",
        json={"investigation_id": "__sidecar__", "prompt": "synthesize this"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["text"] == reply
    # The retrieved passage reached the model's prompt — grounding is real.
    assert provider.calls, "the thought_partner role was never dispatched"
    dispatched_prompt = provider.calls[0]["prompt"]
    assert distinctive_passage in dispatched_prompt


def test_thought_partner_policy_tag_threads_the_section_9_gate(client, monkeypatch):
    """CWE-862 (Strix PR #215): the §9.0 retrieval ``policy_tag`` is
    SERVER-DERIVED and fail-closed — a caller MUST NOT be able to select a
    privileged policy (private_research / operator_only) to pull
    personal_reading / restricted passages into the model context. The
    unauthenticated test client resolves to attribution_eligible regardless
    of what it posts in the body. Stubs the retrieval primitives so no real
    DB / embedding model is touched and the tag reaching search() is
    captured."""
    import contextlib

    captured: dict[str, str] = {}

    class _StubEmbedding:
        dimension = 4

        def encode(self, _text: str) -> list[float]:
            return [0.0, 0.0, 0.0, 0.0]

    def _fake_search(con, text, *, model, top_k, policy_tag, **_kw):
        captured["policy_tag"] = policy_tag
        return {"results": []}

    @contextlib.contextmanager
    def _fake_connect_read(_path):
        yield object()

    # Monkeypatch the MODULE object directly: substrate.graph.search is also
    # re-exported as a function from the package __init__, so a dotted-string
    # setattr would target the function, not the module the helper imports.
    # importlib.import_module always resolves the module (an ``import ... as``
    # here binds the re-exported function, not the module).
    import importlib

    search_mod = importlib.import_module("substrate.graph.search")

    monkeypatch.setattr(search_mod, "SentenceTransformerEmbedding", _StubEmbedding)
    monkeypatch.setattr(search_mod, "search", _fake_search)
    monkeypatch.setattr("runtime.db_lock.connect_read", _fake_connect_read)
    monkeypatch.setattr("substrate.graph.default_db_path", lambda: "/dummy")
    register_provider(_MockZaiProvider('{"shape":"synthesis","synthesis_text":"ok"}'))

    # No policy_tag in the body → server-derived attribution_eligible.
    resp = client.post("/thought-partner", json={"prompt": "q"})
    assert resp.status_code == 200, resp.text
    assert captured.get("policy_tag") == "attribution_eligible"

    # A caller CANNOT escalate by posting a privileged policy_tag (CWE-862):
    # the field is ignored; the server still derives attribution_eligible for
    # the unauthenticated test client — never the privileged value.
    for privileged in ("private_research", "operator_only"):
        captured.clear()
        resp = client.post(
            "/thought-partner", json={"prompt": "q", "policy_tag": privileged},
        )
        assert resp.status_code == 200, resp.text
        assert captured.get("policy_tag") == "attribution_eligible", (
            f"client-supplied policy_tag={privileged!r} leaked into the "
            f"retrieval gate (CWE-862)"
        )


def test_thought_partner_request_exposes_no_client_policy_tag_field():
    """CWE-862 regression guard: ThoughtPartnerRequest must NOT expose a
    caller-controllable ``policy_tag`` — the §9.0 gate is server-derived.
    Locks the field's removal so it cannot be silently re-added."""
    from interfaces.research.api.app import ThoughtPartnerRequest

    assert "policy_tag" not in ThoughtPartnerRequest.model_fields
