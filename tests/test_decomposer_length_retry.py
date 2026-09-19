"""Decomposer first-call budget + length-retry safety (Mini dogfood)."""

from __future__ import annotations

import json
from types import SimpleNamespace

from interfaces.research.api import decomposer as dec
from substrate.schemas import ActionType, DecomposeQuestionRequestedPayload, Event


def _event() -> Event:
    return Event(
        event_id="evt-1",
        investigation_id="inv-length-retry",
        action_type=ActionType.DECOMPOSE_QUESTION_REQUESTED,
        payload=DecomposeQuestionRequestedPayload(
            question="What is citrus grafting?",
            context="",
        ),
        emitted_at="2026-09-18T00:00:00Z",
        schema_version=1,
        param_version="test",
    )


def _well_formed_decomp() -> dict:
    return {
        "investigation_id": "inv-length-retry",
        "decomposition": [
            {
                "sub_question": "What primary evidence shows citrus grafting is real?",
                "category": "technology_risk",
                "rationale": "Independent verification is needed to defend the thesis.",
                "evidence_type_required": "quantitative",
            },
            {
                "sub_question": "What is the addressable market size for grafting tools?",
                "category": "market_sizing",
                "rationale": "Magnitude determines whether the thesis is worth pursuing.",
                "evidence_type_required": "quantitative",
            },
            {
                "sub_question": "What execution risks have manifested in comparable cases?",
                "category": "team_and_execution",
                "rationale": "Prior art bounds the credibility of execution claims.",
                "evidence_type_required": "qualitative",
            },
            {
                "sub_question": "What regulatory exposure does grafting face?",
                "category": "regulatory_exposure",
                "rationale": "Regulatory blocks invalidate the thesis regardless of merit.",
                "evidence_type_required": "mixed",
            },
        ],
        "keywords": [
            {"term": f"keyword_{i}", "synonyms": [f"alt_{i}"]} for i in range(8)
        ],
    }


def test_first_call_uses_raised_output_budget(monkeypatch):
    """Happy path: first call at DECOMPOSER_OUTPUT_MAX_TOKENS finishes stop."""
    calls: list[int | None] = []
    good = json.dumps(_well_formed_decomp())

    def fake_dispatch(
        prompt,
        role,
        *,
        investigation_id,
        parent_event_id=None,
        max_tokens=None,
        **kw,
    ):
        calls.append(max_tokens)
        return SimpleNamespace(
            text=good,
            provider="deepseek",
            model="deepseek-v4-pro",
            finish_reason="stop",
        )

    monkeypatch.setattr(dec, "dispatch", fake_dispatch)
    import interfaces.research.api.research_owner_dispatch as rod

    monkeypatch.setattr(rod, "dispatch_loop_one", lambda *a, **k: None)

    parsed, policy = dec._dispatch_and_parse("prompt", _event(), label="initial")
    assert parsed is not None
    assert len(parsed.decomposition) == 4
    assert calls == [dec.DECOMPOSER_OUTPUT_MAX_TOKENS]
    assert policy == "deepseek/deepseek-v4-pro"


def test_dispatch_and_parse_retries_on_length(monkeypatch):
    """Safety: if first call still returns length, retry once at same budget."""
    calls: list[int | None] = []
    good = json.dumps(_well_formed_decomp())

    def fake_dispatch(
        prompt,
        role,
        *,
        investigation_id,
        parent_event_id=None,
        max_tokens=None,
        **kw,
    ):
        calls.append(max_tokens)
        if len(calls) == 1:
            return SimpleNamespace(
                text="{truncated",
                provider="deepseek",
                model="deepseek-v4-pro",
                finish_reason="length",
            )
        return SimpleNamespace(
            text=good,
            provider="deepseek",
            model="deepseek-v4-pro",
            finish_reason="stop",
        )

    monkeypatch.setattr(dec, "dispatch", fake_dispatch)
    import interfaces.research.api.research_owner_dispatch as rod

    monkeypatch.setattr(rod, "dispatch_loop_one", lambda *a, **k: None)

    parsed, policy = dec._dispatch_and_parse("prompt", _event(), label="initial")
    assert parsed is not None
    assert len(parsed.decomposition) == 4
    budget = dec.DECOMPOSER_OUTPUT_MAX_TOKENS
    assert calls == [budget, budget]
    assert policy == "deepseek/deepseek-v4-pro"


def test_pro_tier_default_matches_decomposer_budget():
    from pathlib import Path

    from substrate.dispatch.router import DispatchConfig

    cfg = DispatchConfig.from_yaml(
        Path(__file__).resolve().parents[1]
        / "substrate"
        / "dispatch"
        / "config.yaml"
    )
    assert cfg.tiers["pro"].max_tokens == dec.DECOMPOSER_OUTPUT_MAX_TOKENS
