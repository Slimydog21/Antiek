"""Evidence retriever: length retry + self-repair (Mini dogfood)."""

from __future__ import annotations

import json

from interfaces.research.api import evidence_retriever as er
from substrate.schemas import ActionType, Event, EvidenceRetrieveRequestedPayload


def _event(sub_q: str = "What evidence supports X?") -> Event:
    return Event(
        event_id="evt-ev-1",
        investigation_id="inv-ev-length",
        action_type=ActionType.EVIDENCE_RETRIEVE_REQUESTED,
        payload=EvidenceRetrieveRequestedPayload(
            sub_question=sub_q,
            category="technology_risk",
            evidence_type_required="quantitative",
            top_k=5,
            chunks_block="",
            subgraph_block="",
        ),
        emitted_at="2026-09-18T00:00:00Z",
        schema_version=1,
        param_version="test",
    )


def _good(sub_q: str) -> str:
    return json.dumps(
        {
            "sub_question": sub_q,
            "answer": "X is supported by tier-1 sources.",
            "supporting_claims": [
                {
                    "claim": "X holds",
                    "evidence_type": "direct",
                    "chunk_ids": ["chk-1"],
                    "confidence": "moderate",
                    "confidence_basis": "two independent sources",
                    "edge_ids": [],
                    "source_tier_min": 1,
                }
            ],
            "evidentiary_gaps": [],
            "insufficient_evidence": False,
        }
    )


def test_dispatch_and_parse_retries_on_length(monkeypatch):
    calls: list[int | None] = []
    sub_q = "What evidence supports X?"
    good = _good(sub_q)

    def fake_once(prompt, event, *, sub_question, semantic_call_id, attempt, max_tokens=None):
        calls.append(max_tokens)
        if max_tokens is None and len(calls) == 1:
            return "{truncated", "deepseek/deepseek-chat", "length"
        return good, "deepseek/deepseek-chat", "stop"

    monkeypatch.setattr(er, "_dispatch_once", fake_once)
    parsed, policy = er._dispatch_and_parse(
        "prompt",
        _event(sub_q),
        sub_question=sub_q,
        canonical_chunk_ids=("chk-1",),
    )
    assert parsed is not None
    assert parsed.answer.startswith("X is supported")
    assert calls == [None, 16384]
    assert policy == "deepseek/deepseek-chat"


def test_dispatch_and_parse_self_repairs_on_bad_json(monkeypatch):
    calls: list[str] = []
    sub_q = "What evidence supports X?"
    good = _good(sub_q)

    def fake_once(prompt, event, *, sub_question, semantic_call_id, attempt, max_tokens=None):
        calls.append(prompt[:80])
        if "structural contract" in prompt:
            return good, "stub-evidence/stub-flash-model", "stop"
        return "totally not JSON", "stub-evidence/stub-flash-model", "stop"

    monkeypatch.setattr(er, "_dispatch_once", fake_once)
    parsed, policy = er._dispatch_and_parse(
        "PROMPT_BODY",
        _event(sub_q),
        sub_question=sub_q,
        canonical_chunk_ids=("chk-1",),
    )
    assert parsed is not None
    assert len(calls) == 2
    assert "structural contract" in calls[1]
    assert policy == "stub-evidence/stub-flash-model"
