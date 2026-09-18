"""Phase-2 wall: evidence prefers Xiaomi + compact first-call budget."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from interfaces.research.api import evidence_retriever as er
from substrate.dispatch.router import reset_provider_registry, register_provider
from substrate.schemas import ActionType, Event, EvidenceRetrieveRequestedPayload


def _event(sub_q: str = "What evidence supports X?") -> Event:
    return Event(
        event_id="evt-ev-wall",
        investigation_id="inv-ev-wall",
        action_type=ActionType.EVIDENCE_RETRIEVE_REQUESTED,
        payload=EvidenceRetrieveRequestedPayload(
            sub_question=sub_q,
            category="technology_risk",
            evidence_type_required="quantitative",
            top_k=5,
            chunks_block="[c1] Four score and seven years ago...",
            subgraph_block="(no subgraph)",
        ),
        emitted_at="2026-09-18T00:00:00Z",
        schema_version=1,
        param_version="test",
    )


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_provider_registry()
    yield
    reset_provider_registry()


def test_evidence_output_budget_is_8192():
    assert er.EVIDENCE_RETRIEVER_OUTPUT_MAX_TOKENS == 8192


def test_dispatch_once_prefers_xiaomi_when_registered(monkeypatch):
    """Xiaomi override is passed so phase-2 wall tracks the faster flash path."""
    seen: dict = {}

    class _Xiaomi:
        name = "xiaomi"

        def call(self, *, model, prompt, max_tokens, temperature):
            raise AssertionError("should not call via provider.call in this stub")

        def normalize_usage(self, raw_usage):
            from substrate.dispatch.base import NormalizedUsage

            return NormalizedUsage(0, 0, 0)

    register_provider(_Xiaomi())

    def fake_dispatch(prompt, role, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(
            text=json.dumps(
                {
                    "sub_question": "What evidence supports X?",
                    "answer": "Short.",
                    "supporting_claims": [],
                    "evidentiary_gaps": [],
                    "insufficient_evidence": True,
                }
            ),
            provider="xiaomi",
            model="mimo-v2.5-pro",
            finish_reason="stop",
        )

    monkeypatch.setattr(er, "dispatch", fake_dispatch)
    monkeypatch.setattr(
        "interfaces.research.api.research_owner_dispatch.dispatch_loop_one",
        lambda *a, **k: None,
    )
    import interfaces.research.api.research_owner_dispatch as rod

    monkeypatch.setattr(rod, "dispatch_loop_one", lambda *a, **k: None)

    text, policy, finish = er._dispatch_once(
        "prompt",
        _event(),
        sub_question="What evidence supports X?",
        semantic_call_id="phase2:0:abcd",
        attempt=0,
        max_tokens=er.EVIDENCE_RETRIEVER_OUTPUT_MAX_TOKENS,
    )
    assert finish == "stop"
    assert policy == "xiaomi/mimo-v2.5-pro"
    assert seen.get("provider_override") == "xiaomi"
    assert seen.get("model_override") == "mimo-v2.5-pro"
    assert seen.get("max_tokens") == 8192


def test_dispatch_once_skips_xiaomi_override_when_unregistered(monkeypatch):
    seen: dict = {}

    def fake_dispatch(prompt, role, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(
            text="{}",
            provider="deepseek",
            model="deepseek-v4-pro",
            finish_reason="stop",
        )

    monkeypatch.setattr(er, "dispatch", fake_dispatch)
    import interfaces.research.api.research_owner_dispatch as rod

    monkeypatch.setattr(rod, "dispatch_loop_one", lambda *a, **k: None)

    er._dispatch_once(
        "prompt",
        _event(),
        sub_question="What evidence supports X?",
        semantic_call_id=None,
        attempt=0,
        max_tokens=8192,
    )
    assert "provider_override" not in seen
    assert seen.get("max_tokens") == 8192


def test_prompt_has_phase2_hard_limit():
    from roles.evidence_retriever.prompt import EVIDENCE_RETRIEVER_USER_TEMPLATE

    assert "HARD LIMIT (phase-2 wall)" in EVIDENCE_RETRIEVER_USER_TEMPLATE
